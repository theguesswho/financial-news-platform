"""
Track record — the forward scorecard.

Every Monday: a $1,000 lot in each current Strong Buy (qual-adjusted tier),
paired with a $1,000 SPY twin opened the same day. Buy-and-hold, no sells.
Lots opened when a stock FIRST enters Strong Buy are tagged entry lots —
they isolate whether the signal is fresh when it fires.

Honesty rules:
  - Lots open only from RECORDED leaderboard snapshots (point-in-time picks,
    never reconstructed scores).
  - Entry price = first close ON or AFTER the snapshot date (no same-day
    look-ahead pretence; we buy at the next available close).
  - SPY twin uses the identical date and rule.

Self-healing: the daily scheduler calls open_weekly_lots() every run; it
no-ops unless a Monday snapshot exists without lots.
"""
from datetime import date, timedelta

from sqlalchemy import text


def create_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS track_lots (
                id           SERIAL PRIMARY KEY,
                lot_date     DATE NOT NULL,          -- snapshot date the pick came from
                symbol       VARCHAR(10) NOT NULL,
                tier         VARCHAR(20),
                gem_score    NUMERIC(10,4),
                is_entry     BOOLEAN DEFAULT FALSE,  -- first time this stock hit Strong Buy
                entry_price  NUMERIC(12,4),
                spy_price    NUMERIC(12,4),
                benchmark    VARCHAR(10) DEFAULT 'SPY',
                amount       NUMERIC(10,2) DEFAULT 1000,
                UNIQUE (lot_date, symbol)
            )
        """))


BENCHMARKS = ("SPY",)   # user decision 2026-07-12: SPY is THE benchmark for every lot,
                        # mid-caps included — the bar is "would my money have done
                        # better in the index I actually hold". (benchmark column and
                        # multi-benchmark plumbing retained but inactive.)


def _midcap_symbols() -> set:
    """Union of the midcap chunk files — these lots benchmark against MDY."""
    from pathlib import Path
    out = set()
    cfg = Path(__file__).parent.parent / "config"
    for p in cfg.glob("midcap_chunk*.txt"):
        out |= {l.strip().upper() for l in open(p) if l.strip()}
    return out


def _ensure_benchmark_prices(engine):
    """SPY + MDY closes into eod_prices — needed for twins and valuation."""
    import yfinance as yf
    for etf in BENCHMARKS:
        with engine.connect() as conn:
            last = conn.execute(text(
                "SELECT MAX(date) FROM eod_prices WHERE symbol=:s"), {"s": etf}).scalar()
        start = (last + timedelta(days=1)) if last else date(2026, 6, 1)
        if start > date.today():
            continue
        hist = yf.Ticker(etf).history(start=str(start), auto_adjust=True)
        if hist.empty:
            continue
        rows = [{"s": etf, "d": idx.date(), "o": float(r["Open"]), "h": float(r["High"]),
                 "l": float(r["Low"]), "c": float(r["Close"]), "v": int(r["Volume"])}
                for idx, r in hist.iterrows()]
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO eod_prices (symbol, date, open, high, low, close, volume)
                VALUES (:s, :d, :o, :h, :l, :c, :v)
                ON CONFLICT (symbol, date) DO NOTHING
            """), rows)


def _close_on_or_after(conn, symbol: str, d: date):
    return conn.execute(text("""
        SELECT close FROM eod_prices
        WHERE symbol = :s AND date >= :d ORDER BY date LIMIT 1
    """), {"s": symbol, "d": d}).scalar()


def open_weekly_lots(engine) -> dict:
    """
    For every Monday (or first snapshot of each ISO week) in leaderboard_history
    that has no lots yet: open a $1,000 lot per Strong Buy + its SPY twin.
    Idempotent — safe to call every day.
    """
    create_table(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE track_lots ADD COLUMN IF NOT EXISTS benchmark VARCHAR(10) DEFAULT 'SPY'"))
    _ensure_benchmark_prices(engine)

    with engine.connect() as conn:
        # First snapshot date of each ISO week in the archive
        week_dates = [r[0] for r in conn.execute(text("""
            SELECT MIN(date) FROM leaderboard_history
            GROUP BY EXTRACT(ISOYEAR FROM date), EXTRACT(WEEK FROM date)
            ORDER BY 1
        """)).fetchall()]
        have_lots = {r[0] for r in conn.execute(text(
            "SELECT DISTINCT lot_date FROM track_lots")).fetchall()}

    opened = 0
    for wd in week_dates:
        if wd in have_lots:
            continue
        with engine.connect() as conn:
            picks = conn.execute(text("""
                SELECT symbol, COALESCE(assessed_tier, tier) AS t, gem_score
                FROM leaderboard_history
                WHERE date = :d AND COALESCE(assessed_tier, tier) = 'Strong Buy'
            """), {"d": wd}).fetchall()
            if not picks:
                continue
            bench_px = {b: _close_on_or_after(conn, b, wd) for b in BENCHMARKS}
            if bench_px["SPY"] is None:
                continue
            # Entry lot = symbol was not Strong Buy on any earlier snapshot
            prior_sb = {r[0] for r in conn.execute(text("""
                SELECT DISTINCT symbol FROM leaderboard_history
                WHERE date < :d AND COALESCE(assessed_tier, tier) = 'Strong Buy'
            """), {"d": wd}).fetchall()}

            rows = []
            for sym, t, score in picks:
                px = _close_on_or_after(conn, sym, wd)
                bmk = "SPY"
                b_px = bench_px["SPY"]
                if px is None or b_px is None:
                    continue
                rows.append({"d": wd, "s": sym, "t": t, "g": float(score),
                             "e": sym not in prior_sb, "b": bmk,
                             "px": float(px), "spy": float(b_px)})
        if rows:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO track_lots
                        (lot_date, symbol, tier, gem_score, is_entry, entry_price, spy_price, benchmark)
                    VALUES (:d, :s, :t, :g, :e, :px, :spy, :b)
                    ON CONFLICT (lot_date, symbol) DO NOTHING
                """), rows)
            opened += len(rows)

    if opened:
        print(f"✓ Opened {opened} track-record lots")
    return {"opened": opened}


def get_scorecard(engine) -> dict:
    """Mark-to-market every lot against its SPY twin."""
    _ensure_benchmark_prices(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH latest AS (
                SELECT symbol, close,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) rn
                FROM eod_prices
            )
            SELECT tl.lot_date, tl.symbol, tl.is_entry, tl.amount,
                   tl.entry_price, ls.close AS now_price,
                   tl.spy_price,  lspy.close AS spy_now
            FROM track_lots tl
            JOIN latest ls   ON ls.symbol = tl.symbol AND ls.rn = 1
            JOIN latest lspy ON lspy.symbol = COALESCE(tl.benchmark, 'SPY') AND lspy.rn = 1
            WHERE NOT COALESCE(tl.voided, FALSE)
            ORDER BY tl.lot_date, tl.symbol
        """)).fetchall()

    lots = []
    for d, sym, is_entry, amt, e_px, n_px, e_spy, n_spy in rows:
        amt = float(amt)
        stock_val = amt * float(n_px) / float(e_px)
        spy_val   = amt * float(n_spy) / float(e_spy)
        lots.append({
            "lot_date": d, "symbol": sym, "is_entry": bool(is_entry),
            "invested": amt, "stock_value": round(stock_val, 2),
            "spy_value": round(spy_val, 2),
            "vs_spy_pct": round((stock_val - spy_val) / amt * 100, 2),
            "beat": stock_val > spy_val,
        })

    total_inv  = sum(l["invested"] for l in lots)
    total_stk  = sum(l["stock_value"] for l in lots)
    total_spy  = sum(l["spy_value"] for l in lots)
    entry_lots = [l for l in lots if l["is_entry"]]
    return {
        "lots": lots,
        "total_invested": total_inv,
        "portfolio_value": round(total_stk, 2),
        "spy_value": round(total_spy, 2),
        "portfolio_return_pct": round((total_stk / total_inv - 1) * 100, 2) if total_inv else 0,
        "spy_return_pct": round((total_spy / total_inv - 1) * 100, 2) if total_inv else 0,
        "lots_beating_spy": sum(1 for l in lots if l["beat"]),
        "n_lots": len(lots),
        "entry_lots_beating": sum(1 for l in entry_lots if l["beat"]),
        "n_entry_lots": len(entry_lots),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    open_weekly_lots(eng)
    sc = get_scorecard(eng)
    print(f"\nLots: {sc['n_lots']} | invested {sc['total_invested']:,.0f}")
    print(f"Portfolio: {sc['portfolio_value']:,.0f} ({sc['portfolio_return_pct']:+.2f}%)")
    print(f"SPY twin:  {sc['spy_value']:,.0f} ({sc['spy_return_pct']:+.2f}%)")
    print(f"Lots beating SPY: {sc['lots_beating_spy']}/{sc['n_lots']}"
          f" | entry lots: {sc['entry_lots_beating']}/{sc['n_entry_lots']}")
