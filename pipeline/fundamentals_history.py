"""
Fundamentals history — quarterly snapshots of key financial metrics per stock.

Two sources:
  1. Backfill from quarterly_trends JSON already in the fundamentals table
     (up to 8 quarters, already fetched from yfinance quarterly statements)
  2. Annual income statement history from yfinance (up to 4 fiscal years)

Table: fundamentals_history
  symbol, period_end, period_type (Q/A), revenue, gross_margin, operating_margin,
  net_margin, fcf, roic, pe_forward, peg_ratio, fetched_at

Run once to backfill, then called weekly from scheduler to add the latest quarter.
"""
import json
import time
from datetime import datetime
from typing import Optional

import yfinance as yf
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)


def _safe(val) -> Optional[float]:
    try:
        f = float(val)
        return None if (f != f or abs(f) > 1e15) else f
    except Exception:
        return None


def create_table(engine):
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fundamentals_history (
                id           SERIAL PRIMARY KEY,
                symbol       VARCHAR(10)  NOT NULL,
                period_end   DATE         NOT NULL,
                period_type  CHAR(1)      NOT NULL,  -- 'Q' or 'A'
                revenue      NUMERIC(20,0),
                gross_margin NUMERIC(10,4),
                op_margin    NUMERIC(10,4),
                net_margin   NUMERIC(10,4),
                fcf          NUMERIC(20,0),
                roic         NUMERIC(10,4),
                fetched_at   TIMESTAMP DEFAULT NOW(),
                UNIQUE (symbol, period_end, period_type)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_fh_symbol_date "
            "ON fundamentals_history (symbol, period_end DESC)"
        ))
        conn.commit()
    print("✅ fundamentals_history table ready")


def _upsert(conn, rows: list[dict]):
    if not rows:
        return 0
    conn.execute(text("""
        INSERT INTO fundamentals_history
            (symbol, period_end, period_type, revenue, gross_margin,
             op_margin, net_margin, fcf, roic, fetched_at)
        VALUES
            (:symbol, :period_end, :period_type, :revenue, :gross_margin,
             :op_margin, :net_margin, :fcf, :roic, NOW())
        ON CONFLICT (symbol, period_end, period_type) DO UPDATE SET
            revenue      = EXCLUDED.revenue,
            gross_margin = EXCLUDED.gross_margin,
            op_margin    = EXCLUDED.op_margin,
            net_margin   = EXCLUDED.net_margin,
            fcf          = EXCLUDED.fcf,
            roic         = EXCLUDED.roic,
            fetched_at   = NOW()
    """), rows)
    return len(rows)


def backfill_from_existing_quarterly_trends(engine):
    """
    Parse quarterly_trends JSON already stored in fundamentals table.
    Gives up to 8 quarters per stock with zero extra API calls.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT symbol, quarterly_trends FROM fundamentals "
            "WHERE quarterly_trends IS NOT NULL"
        )).fetchall()

    inserted = 0
    skipped  = 0

    with engine.connect() as conn:
        for symbol, trends_json in rows:
            try:
                trends = json.loads(trends_json)
                dates   = trends.get("dates", [])
                revenue = trends.get("revenue", [])
                gm      = trends.get("gross_margin", [])
                om      = trends.get("operating_margin", [])
                net_inc = trends.get("net_income", [])
                fcf     = trends.get("fcf", [])

                batch = []
                for i, d in enumerate(dates):
                    rev_v  = _safe(revenue[i]) if i < len(revenue) else None
                    gm_v   = _safe(gm[i])      if i < len(gm)      else None
                    om_v   = _safe(om[i])       if i < len(om)      else None
                    ni_v   = _safe(net_inc[i])  if i < len(net_inc) else None
                    fcf_v  = _safe(fcf[i])      if i < len(fcf)     else None
                    nm_v   = round(ni_v / rev_v, 4) if ni_v and rev_v else None

                    batch.append({
                        "symbol":       symbol,
                        "period_end":   d[:10],
                        "period_type":  "Q",
                        "revenue":      int(rev_v) if rev_v else None,
                        "gross_margin": gm_v,
                        "op_margin":    om_v,
                        "net_margin":   nm_v,
                        "fcf":          int(fcf_v) if fcf_v else None,
                        "roic":         None,  # not in quarterly_trends; filled by annual pass
                    })

                inserted += _upsert(conn, batch)
            except Exception as e:
                skipped += 1
                print(f"  {symbol}: parse error — {e}")

        conn.commit()

    print(f"  Quarterly backfill: {inserted} rows inserted, {skipped} errors")
    return inserted


def backfill_annual_from_yfinance(engine, symbols: list[str]):
    """
    Fetch up to 4 years of annual financials from yfinance for each symbol.
    Adds annual snapshots (period_type='A') and fills in ROIC.
    """
    inserted = 0
    errors   = 0

    for i, sym in enumerate(symbols, 1):
        try:
            ticker = yf.Ticker(sym)
            fin  = ticker.income_stmt    # annual, newest-first columns
            cf   = ticker.cashflow
            info = ticker.info or {}

            if fin is None or fin.empty:
                continue

            def row_sum(df, *names):
                for n in names:
                    matches = [c for c in df.index if n.lower() in c.lower()]
                    if matches:
                        return df.loc[matches[0]]
                return None

            rev_s  = row_sum(fin, "Total Revenue", "Revenue")
            gp_s   = row_sum(fin, "Gross Profit")
            op_s   = row_sum(fin, "Operating Income", "EBIT")
            ni_s   = row_sum(fin, "Net Income")

            op_cf_s = row_sum(cf, "Operating Cash Flow", "Cash From Operations") if cf is not None and not cf.empty else None
            capex_s = row_sum(cf, "Capital Expenditure", "Purchase Of PPE")     if cf is not None and not cf.empty else None

            # Balance sheet — for period-specific ROIC (equity + debt per fiscal year)
            bs = ticker.balance_sheet
            eq_s   = row_sum(bs, "Stockholders Equity", "Total Equity", "Common Stock Equity") if bs is not None and not bs.empty else None
            dbt_s  = row_sum(bs, "Total Debt", "Long Term Debt")                               if bs is not None and not bs.empty else None

            batch = []
            for col in fin.columns:
                try:
                    period_end = str(col)[:10]
                    rev  = _safe(rev_s[col])  if rev_s  is not None else None
                    gp   = _safe(gp_s[col])   if gp_s   is not None else None
                    op   = _safe(op_s[col])    if op_s   is not None else None
                    ni   = _safe(ni_s[col])    if ni_s   is not None else None

                    op_cf = _safe(op_cf_s[col]) if op_cf_s is not None else None
                    capex = _safe(capex_s[col]) if capex_s is not None else None
                    fcf   = (op_cf - abs(capex)) if op_cf is not None and capex is not None else None

                    gm_v = round(gp / rev, 4)  if gp  and rev else None
                    om_v = round(op / rev, 4)   if op  and rev else None
                    nm_v = round(ni / rev, 4)   if ni  and rev else None

                    # Period-specific ROIC: net income / (equity + debt) for that fiscal year.
                    # Balance sheet columns may not align exactly — match by nearest date.
                    roic_v = None
                    if ni and eq_s is not None and dbt_s is not None:
                        bs_col = col if col in eq_s.index else None
                        if bs_col is None and hasattr(eq_s, 'index'):
                            # find closest balance sheet date within 180 days
                            import pandas as pd
                            try:
                                target = pd.Timestamp(col)
                                diffs  = [(abs((pd.Timestamp(c) - target).days), c)
                                          for c in eq_s.index if hasattr(c, 'year')]
                                if diffs:
                                    closest_days, bs_col = min(diffs)
                                    if closest_days > 180:
                                        bs_col = None
                            except Exception:
                                bs_col = None
                        if bs_col is not None:
                            eq_v  = _safe(eq_s[bs_col])
                            dbt_v = _safe(dbt_s[bs_col]) or 0.0
                            invested = (eq_v + dbt_v) if eq_v is not None else None
                            if invested and invested > 0:
                                roic_v = round(ni / invested, 4)

                    batch.append({
                        "symbol":       sym,
                        "period_end":   period_end,
                        "period_type":  "A",
                        "revenue":      int(rev) if rev else None,
                        "gross_margin": gm_v,
                        "op_margin":    om_v,
                        "net_margin":   nm_v,
                        "fcf":          int(fcf) if fcf else None,
                        "roic":         roic_v,
                    })
                except Exception:
                    continue

            with engine.connect() as conn:
                inserted += _upsert(conn, batch)
                conn.commit()

            if i % 50 == 0:
                print(f"  [{i}/{len(symbols)}] {sym} — {len(batch)} annual rows")
            time.sleep(0.3)

        except Exception as e:
            errors += 1
            if i % 50 == 0 or errors < 5:
                print(f"  {sym}: error — {e}")

    print(f"  Annual backfill: {inserted} rows inserted, {errors} errors")
    return inserted


def run_history_backfill(engine):
    """Full backfill: quarterly from existing JSON + annual from yfinance."""
    from pathlib import Path

    tickers_path = Path(__file__).parent.parent / "config" / "tickers.txt"
    with open(tickers_path) as f:
        symbols = [line.strip().upper() for line in f if line.strip()]

    print("=" * 60)
    print("FUNDAMENTALS HISTORY BACKFILL")
    print("=" * 60)

    create_table(engine)

    print("\nStep 1: Quarterly data from existing fundamentals JSON...")
    backfill_from_existing_quarterly_trends(engine)

    print(f"\nStep 2: Annual data from yfinance ({len(symbols)} symbols)...")
    backfill_annual_from_yfinance(engine, symbols)

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM fundamentals_history")).scalar()
        syms  = conn.execute(text("SELECT COUNT(DISTINCT symbol) FROM fundamentals_history")).scalar()
        oldest = conn.execute(text("SELECT MIN(period_end) FROM fundamentals_history")).scalar()

    print(f"\n✅ Done: {total:,} rows, {syms} symbols, oldest period: {oldest}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(override=True)
    from pipeline.hidden_gem_scorer import get_engine
    engine = get_engine()
    run_history_backfill(engine)
