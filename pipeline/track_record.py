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


# v2 era cutover (user decision 2026-07-22): the v1 lots are ARCHIVED — never
# deleted, excluded from the active scorecard — and a fresh heads-up table
# starts with the first v2-scored snapshot. Same honesty rules.
V2_START = date(2026, 7, 23)
# v2d era (user 2026-08-14): DAILY $100 accumulation, one symmetric
# 2-day rule — each session: if the last TWO readings are Strong Buy,
# buy $100 at that session's close (every day, while it stays SB); if
# the last two are below Buy, sell ALL open lots at that close;
# otherwise hold. Twin mirrors every lot to the cent on identical
# dates. Each lot is an independent $100 — proceeds are NEVER
# reinvested (a ledger of equal-sized decisions, not a compounding
# account; user-ratified 2026-08-14). "We can only ever buy randomly
# or consistently. Consistently is more honest." The weekly-lot era
# ('v2') is frozen at 2026-08-13 closes; v1 is the original archive.
ERA = "v2d"
DAILY_LOT = 100.0


def run_daily_lot_lifecycle(engine) -> dict:
    """Entries and exits under the v2d rules, executed at the freshest
    close. Runs ONLY in the after-close run (after that session's closes
    are ingested) — the daily 6:00 run's freshest close is the SIGNAL
    close, and filling there would be look-ahead.
    Signal day T = the most recent trading-day snapshot BEFORE the
    freshest close date C; confirmation day = the one before T."""
    create_table(engine)
    opened = closed = 0
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE track_lots ADD COLUMN IF NOT EXISTS signal_date DATE"))
        # Uniqueness must be per-era: the old (lot_date, symbol) constraint
        # made v2d backfill rows silently collide with archived weekly lots
        # on the same date (PTC 2026-08-10).
        conn.execute(text("""
            ALTER TABLE track_lots
            DROP CONSTRAINT IF EXISTS track_lots_lot_date_symbol_key"""))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS track_lots_date_sym_era
            ON track_lots (lot_date, symbol, era)"""))
        C = conn.execute(text(
            "SELECT MAX(date) FROM eod_prices WHERE symbol = 'SPY'")).scalar()
        if C is None:
            return {"opened": 0, "closed": 0}
        tdays = [r[0] for r in conn.execute(text("""
            SELECT DISTINCT lh.date FROM leaderboard_history lh
            JOIN eod_prices p ON p.symbol = 'SPY' AND p.date = lh.date
            WHERE lh.date < :c ORDER BY lh.date DESC LIMIT 2"""), {"c": C})]
        if len(tdays) < 2:
            return {"opened": 0, "closed": 0}
        T, T1 = tdays[0], tdays[1]
        spy_c = conn.execute(text(
            "SELECT close FROM eod_prices WHERE symbol='SPY' AND date=:c"),
            {"c": C}).scalar()
        rows = conn.execute(text("""
            WITH t AS (SELECT symbol, COALESCE(assessed_tier, tier) ft, gem_score
                       FROM leaderboard_history WHERE date = :t),
                 t1 AS (SELECT symbol, COALESCE(assessed_tier, tier) ft
                        FROM leaderboard_history WHERE date = :t1)
            SELECT t.symbol, t.ft, t1.ft, t.gem_score, px.close
            FROM t JOIN t1 USING (symbol)
            LEFT JOIN eod_prices px ON px.symbol = t.symbol AND px.date = :c
        """), {"t": T, "t1": T1, "c": C}).fetchall()
        open_syms = {r[0] for r in conn.execute(text("""
            SELECT DISTINCT symbol FROM track_lots
            WHERE era = :e AND exit_date IS NULL
              AND NOT COALESCE(voided, FALSE)"""), {"e": ERA})}
        for sym, ft, ft1, gem, px_c in rows:
            if px_c is None or spy_c is None:
                continue
            # Daily accumulation: buy EVERY session the 2-day condition
            # holds — open lots do not block new ones. The per-day unique
            # index (lot_date, symbol, era) blocks double-buys on reruns.
            if ft == 'Strong Buy' and ft1 == 'Strong Buy':
                conn.execute(text("""
                    INSERT INTO track_lots
                        (lot_date, symbol, tier, gem_score, is_entry, entry_price,
                         spy_price, amount, benchmark, era, signal_date)
                    VALUES (:d, :s, 'Strong Buy', :g, TRUE, :px, :spy, :amt,
                            'SPY', :e, :sig)
                    ON CONFLICT (lot_date, symbol, era) DO NOTHING
                """), {"d": C, "s": sym, "g": gem, "px": px_c, "spy": spy_c,
                       "amt": DAILY_LOT, "e": ERA, "sig": T})
                opened += 1
            elif sym in open_syms and ft not in ('Strong Buy', 'Buy') \
                    and ft1 not in ('Strong Buy', 'Buy'):
                conn.execute(text("""
                    UPDATE track_lots
                    SET exit_date = :d, exit_price = :px, spy_exit_price = :spy,
                        exit_reason = '2 consecutive readings below Buy (signal ' || :sig || ')'
                    WHERE symbol = :s AND era = :e AND exit_date IS NULL
                      AND NOT COALESCE(voided, FALSE)
                """), {"d": C, "px": px_c, "spy": spy_c, "s": sym,
                       "e": ERA, "sig": str(T)})
                closed += 1
    if opened or closed:
        print(f"✓ v2d lifecycle: opened {opened}, closed {closed} at {C} closes")
    return {"opened": opened, "closed": closed}

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
        conn.execute(text(
            "ALTER TABLE track_lots ADD COLUMN IF NOT EXISTS qual_promoted BOOLEAN DEFAULT FALSE"))
        conn.execute(text(
            "ALTER TABLE track_lots ADD COLUMN IF NOT EXISTS era VARCHAR(4) DEFAULT 'v1'"))
        # One-time: anything opened before the v2 cutover belongs to the v1 era
        conn.execute(text(
            "UPDATE track_lots SET era = 'v1' WHERE era IS NULL OR lot_date < :d"),
            {"d": V2_START})
    _ensure_benchmark_prices(engine)

    with engine.connect() as conn:
        # First snapshot date of each ISO week in the archive
        # v2 era: lots open only from v2-scored snapshots
        week_dates = [r[0] for r in conn.execute(text("""
            SELECT MIN(date) FROM leaderboard_history
            WHERE date >= :v2
            GROUP BY EXTRACT(ISOYEAR FROM date), EXTRACT(WEEK FROM date)
            ORDER BY 1
        """), {"v2": V2_START}).fetchall()]
        have_lots = {r[0] for r in conn.execute(text(
            "SELECT DISTINCT lot_date FROM track_lots")).fetchall()}

    opened = 0
    for wd in week_dates:
        if wd in have_lots:
            continue
        with engine.connect() as conn:
            picks = conn.execute(text("""
                SELECT symbol, COALESCE(assessed_tier, tier) AS t,
                       COALESCE(gem_adjusted, gem_score),
                       COALESCE(qual_promoted, FALSE)
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
                WHERE date < :d AND date >= :v2
                  AND COALESCE(assessed_tier, tier) = 'Strong Buy'
            """), {"d": wd, "v2": V2_START}).fetchall()}

            rows = []
            for sym, t, score, qual_promoted in picks:
                px = _close_on_or_after(conn, sym, wd)
                bmk = "SPY"
                b_px = bench_px["SPY"]
                if px is None or b_px is None:
                    continue
                rows.append({"d": wd, "s": sym, "t": t, "g": float(score),
                             "e": sym not in prior_sb, "b": bmk, "qp": bool(qual_promoted),
                             "px": float(px), "spy": float(b_px)})
        if rows:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO track_lots
                        (lot_date, symbol, tier, gem_score, is_entry, entry_price,
                         spy_price, benchmark, qual_promoted, era)
                    VALUES (:d, :s, :t, :g, :e, :px, :spy, :b, :qp, '%s')
                    ON CONFLICT (lot_date, symbol) DO NOTHING
                """ %  ERA), rows)
            opened += len(rows)

    if opened:
        print(f"✓ Opened {opened} track-record lots")
    return {"opened": opened}


def get_scorecard(engine, era: str = ERA, as_of=None) -> dict:
    """Mark-to-market every lot of the given era against its SPY twin.
    Default is the active v2 era; pass era='v1' to read the archived record.
    as_of (date) marks lots at that session's closes instead of the newest
    prices — regenerated editions must keep their own day's scoreboard,
    not absorb regeneration-day marks (the 8.7% confusion, 2026-08-11).
    Lots opened after as_of are excluded; exits after as_of count as open."""
    if as_of is None:
        _ensure_benchmark_prices(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH latest AS (
                -- DISTINCT ON over a 10-day window, not a full-history window
                -- ranking: the old form scanned every eod_prices row and the
                -- proxy killed it once the midcap backfill grew the table
                -- (silent scorecard disappearance, 2026-08-03).
                SELECT DISTINCT ON (symbol) symbol, close
                FROM eod_prices
                WHERE date <= COALESCE(:as_of, CURRENT_DATE)
                  AND date > COALESCE(:as_of, CURRENT_DATE) - 10
                ORDER BY symbol, date DESC
            )
            SELECT tl.lot_date, tl.symbol, tl.is_entry, tl.amount,
                   tl.entry_price,
                   CASE WHEN tl.exit_date IS NOT NULL
                             AND tl.exit_date <= COALESCE(:as_of, CURRENT_DATE)
                        THEN tl.exit_price ELSE ls.close END   AS now_price,
                   tl.spy_price,
                   CASE WHEN tl.exit_date IS NOT NULL
                             AND tl.exit_date <= COALESCE(:as_of, CURRENT_DATE)
                        THEN tl.spy_exit_price ELSE lspy.close END AS spy_now,
                   CASE WHEN tl.exit_date <= COALESCE(:as_of, CURRENT_DATE)
                        THEN tl.exit_date END                  AS exit_date
            FROM track_lots tl
            LEFT JOIN latest ls   ON ls.symbol = tl.symbol
            LEFT JOIN latest lspy ON lspy.symbol = COALESCE(tl.benchmark, 'SPY')
            WHERE NOT COALESCE(tl.voided, FALSE)
              AND COALESCE(tl.era, 'v1') = :era
              AND tl.lot_date <= COALESCE(:as_of, CURRENT_DATE)
            ORDER BY tl.lot_date, tl.symbol
        """), {"era": era, "as_of": as_of}).fetchall()

    lots = []
    for d, sym, is_entry, amt, e_px, n_px, e_spy, n_spy, exit_d in rows:
        if n_px is None or n_spy is None:   # no close as of that session
            continue
        amt = float(amt)
        stock_val = amt * float(n_px) / float(e_px)
        spy_val   = amt * float(n_spy) / float(e_spy)
        lots.append({
            "lot_date": d, "symbol": sym, "is_entry": bool(is_entry),
            "invested": amt, "stock_value": round(stock_val, 2),
            "spy_value": round(spy_val, 2),
            "vs_spy_pct": round((stock_val - spy_val) / amt * 100, 2),
            "beat": stock_val > spy_val,
            "closed": exit_d is not None, "exit_date": exit_d,
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
        "open_lots": sum(1 for l in lots if not l["closed"]),
        "closed_lots": sum(1 for l in lots if l["closed"]),
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


def manage_positions(engine) -> dict:
    """Position lifecycle (user rule 2026-08-06): Strong Buy = buy,
    Buy = hold what you have, below Buy = SELL — but only after TWO
    consecutive daily snapshots below Buy (same anti-chop medicine as the
    board exit line; DocuSign-class one-day drift never sells a position).
    The SPY twin is sold the same day so the race stays fair. Closed lots
    keep their locked result on the record forever; a later fresh Strong
    Buy opens a NEW lot (re-entry allowed). Judged on the FINAL tier
    (COALESCE(assessed, raw)) so a bookkeeping stamp-lapse alone cannot
    trigger a sale when the raw tier still says Buy or better."""
    stats = {"checked": 0, "reset": 0, "warned": 0, "sold": 0}
    sold = []
    with engine.begin() as conn:
        snap_date = conn.execute(text(
            "SELECT MAX(date) FROM leaderboard_history")).scalar()
        if snap_date is None:
            return stats
        tiers = dict(conn.execute(text("""
            SELECT symbol, COALESCE(assessed_tier, tier) FROM leaderboard_history
            WHERE date = :d"""), {"d": snap_date}).fetchall())
        lots = conn.execute(text("""
            SELECT id, symbol, entry_price, spy_price, benchmark,
                   COALESCE(below_buy_days, 0), below_buy_last_date
            FROM track_lots
            WHERE COALESCE(era, 'v1') = :era AND NOT COALESCE(voided, FALSE)
              AND exit_date IS NULL
        """), {"era": ERA}).fetchall()
        for lid, sym, e_px, e_spy, bench, days, last_d in lots:
            stats["checked"] += 1
            if last_d == snap_date:
                continue    # this snapshot already counted (idempotent)
            tier = tiers.get(sym)
            if tier in ("Strong Buy", "Buy"):
                if days:
                    conn.execute(text("""UPDATE track_lots
                        SET below_buy_days = 0, below_buy_last_date = :d
                        WHERE id = :i"""), {"d": snap_date, "i": lid})
                    stats["reset"] += 1
                continue
            days += 1
            if days < 2:
                conn.execute(text("""UPDATE track_lots
                    SET below_buy_days = :n, below_buy_last_date = :d
                    WHERE id = :i"""), {"n": days, "d": snap_date, "i": lid})
                stats["warned"] += 1
                continue
            # Two consecutive snapshots below Buy: sell lot + twin today.
            x_px = _close_on_or_after(conn, sym, snap_date)
            x_spy = _close_on_or_after(conn, bench or "SPY", snap_date)
            if not x_px or not x_spy:
                continue    # no price yet — retry next run, counter holds
            reason = (f"held below Buy for 2 consecutive days "
                      f"(now {tier or 'off board'}); sold with its "
                      f"{bench or 'SPY'} twin")
            conn.execute(text("""UPDATE track_lots
                SET exit_date = :d, exit_price = :xp, spy_exit_price = :xs,
                    exit_reason = :r, below_buy_days = :n,
                    below_buy_last_date = :d
                WHERE id = :i"""),
                {"d": snap_date, "xp": x_px, "xs": x_spy, "r": reason,
                 "n": days, "i": lid})
            stats["sold"] += 1
            ret = (float(x_px) / float(e_px) - 1) * 100
            twin = (float(x_spy) / float(e_spy) - 1) * 100
            sold.append({"symbol": sym, "return_pct": round(ret, 2),
                         "twin_pct": round(twin, 2), "reason": reason})
            print(f"  SOLD {sym}: {ret:+.1f}% vs twin {twin:+.1f}% ({reason})")
    stats["sales"] = sold
    print(f"position management: {stats}")
    return stats
