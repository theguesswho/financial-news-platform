"""
Canonical financial-statement data — FMP, one vendor, one definition per
metric (QUALITY_DURABILITY_SPEC P1, user-approved 2026-08-09).

Vendor doctrine: FMP owns what companies report (this module); Yahoo owns
what the market says (prices, PEG-vendor, analyst context); SEC/EarningsCall
own the documents. The in-house ROIC formula (net income / (equity+debt) —
the 436%-ASML generator) is retired by P2; nothing here touches scoring
until then.

Tables:
  fundamentals_annual — up to 15 fiscal years per symbol
  fundamentals_ttm    — trailing-twelve-month snapshot, refreshed weekly +
                        on the dirty-symbol cadence (P2 wiring)

Cost: FMP quota only (~3 calls/symbol backfill, 2/symbol TTM), zero LLM.
"""
import json
import os
import time
import urllib.request

from sqlalchemy import text

BASE = "https://financialmodelingprep.com/api/v3"
THROTTLE_S = 0.25


def _get(path: str, **params) -> list | dict | None:
    params["apikey"] = os.environ.get("FMP_API_KEY", "")
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(f"{BASE}/{path}?{qs}", timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return None


def create_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fundamentals_annual (
                symbol         VARCHAR(10) NOT NULL,
                fiscal_year    DATE NOT NULL,
                revenue        NUMERIC(20,0),
                gross_margin   NUMERIC(10,4),
                op_margin      NUMERIC(10,4),
                net_margin     NUMERIC(10,4),
                fcf            NUMERIC(20,0),
                roic           NUMERIC(10,4),
                roe            NUMERIC(10,4),
                debt_to_equity NUMERIC(12,4),
                fetched_at     TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (symbol, fiscal_year)
            )"""))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fundamentals_ttm (
                symbol         VARCHAR(10) PRIMARY KEY,
                roic           NUMERIC(10,4),
                roe            NUMERIC(10,4),
                gross_margin   NUMERIC(10,4),
                op_margin      NUMERIC(10,4),
                net_margin     NUMERIC(10,4),
                debt_to_equity NUMERIC(12,4),
                fcf_per_share  NUMERIC(14,4),
                fetched_at     TIMESTAMP DEFAULT NOW()
            )"""))


def backfill_symbol(engine, sym: str) -> int:
    """15y annual rows from income-statement + cash-flow + key-metrics.
    Idempotent upsert; returns rows written."""
    inc = _get(f"income-statement/{sym}", period="annual", limit=15) or []
    time.sleep(THROTTLE_S)
    cf = _get(f"cash-flow-statement/{sym}", period="annual", limit=15) or []
    time.sleep(THROTTLE_S)
    km = _get(f"key-metrics/{sym}", period="annual", limit=15) or []
    time.sleep(THROTTLE_S)
    if not isinstance(inc, list) or not inc:
        return 0
    cf_by = {r.get("date"): r for r in cf if isinstance(r, dict)}
    km_by = {r.get("date"): r for r in km if isinstance(r, dict)}
    rows = []
    for r in inc:
        if not isinstance(r, dict) or not r.get("date"):
            continue
        rev = r.get("revenue") or 0
        def m(x):
            return round(x / rev, 4) if rev and x is not None else None
        k = km_by.get(r["date"], {})
        rows.append({
            "s": sym, "fy": r["date"], "rev": rev or None,
            "gm": m(r.get("grossProfit")), "om": m(r.get("operatingIncome")),
            "nm": m(r.get("netIncome")),
            "fcf": (cf_by.get(r["date"], {}) or {}).get("freeCashFlow"),
            "roic": k.get("roic"), "roe": k.get("roe"),
            "dte": k.get("debtToEquity")})
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO fundamentals_annual
                (symbol, fiscal_year, revenue, gross_margin, op_margin,
                 net_margin, fcf, roic, roe, debt_to_equity)
            VALUES (:s, :fy, :rev, :gm, :om, :nm, :fcf, :roic, :roe, :dte)
            ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                revenue=EXCLUDED.revenue, gross_margin=EXCLUDED.gross_margin,
                op_margin=EXCLUDED.op_margin, net_margin=EXCLUDED.net_margin,
                fcf=EXCLUDED.fcf, roic=EXCLUDED.roic, roe=EXCLUDED.roe,
                debt_to_equity=EXCLUDED.debt_to_equity, fetched_at=NOW()
        """), rows)
    return len(rows)


def backfill_universe(engine, symbols=None, skip_existing: bool = True) -> dict:
    """One-time 15y backfill. Resumable: symbols already holding 10+ annual
    rows are skipped unless skip_existing=False."""
    create_tables(engine)
    with engine.connect() as conn:
        if symbols is None:
            symbols = [r[0] for r in conn.execute(
                text("SELECT symbol FROM fundamentals ORDER BY symbol")).fetchall()]
        done = {r[0] for r in conn.execute(text("""
            SELECT symbol FROM fundamentals_annual
            GROUP BY symbol HAVING COUNT(*) >= 10""")).fetchall()} if skip_existing else set()
    todo = [s for s in symbols if s not in done]
    stats = {"symbols": len(todo), "skipped_done": len(symbols) - len(todo),
             "rows": 0, "empty": []}
    for i, sym in enumerate(todo):
        n = backfill_symbol(engine, sym)
        stats["rows"] += n
        if n == 0:
            stats["empty"].append(sym)
        if (i + 1) % 50 == 0:
            print(f"  backfill {i+1}/{len(todo)} ({stats['rows']} rows)", flush=True)
    stats["empty_count"] = len(stats["empty"])
    stats["empty"] = stats["empty"][:20]
    print(f"backfill done: {stats}")
    return stats


def ttm_sweep(engine, symbols=None) -> dict:
    """TTM snapshot for the universe: key-metrics-ttm + ratios-ttm."""
    create_tables(engine)
    with engine.connect() as conn:
        if symbols is None:
            symbols = [r[0] for r in conn.execute(
                text("SELECT symbol FROM fundamentals ORDER BY symbol")).fetchall()]
    stats = {"symbols": len(symbols), "written": 0, "empty": 0}
    for i, sym in enumerate(symbols):
        km = _get(f"key-metrics-ttm/{sym}")
        time.sleep(THROTTLE_S)
        ra = _get(f"ratios-ttm/{sym}")
        time.sleep(THROTTLE_S)
        k = km[0] if isinstance(km, list) and km else {}
        r = ra[0] if isinstance(ra, list) and ra else {}
        if not k and not r:
            stats["empty"] += 1
            continue
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO fundamentals_ttm
                    (symbol, roic, roe, gross_margin, op_margin, net_margin,
                     debt_to_equity, fcf_per_share, fetched_at)
                VALUES (:s, :roic, :roe, :gm, :om, :nm, :dte, :fps, NOW())
                ON CONFLICT (symbol) DO UPDATE SET
                    roic=EXCLUDED.roic, roe=EXCLUDED.roe,
                    gross_margin=EXCLUDED.gross_margin,
                    op_margin=EXCLUDED.op_margin, net_margin=EXCLUDED.net_margin,
                    debt_to_equity=EXCLUDED.debt_to_equity,
                    fcf_per_share=EXCLUDED.fcf_per_share, fetched_at=NOW()
            """), {"s": sym, "roic": k.get("roicTTM"),
                   "roe": r.get("returnOnEquityTTM"),
                   "gm": r.get("grossProfitMarginTTM"),
                   "om": r.get("operatingProfitMarginTTM"),
                   "nm": r.get("netProfitMarginTTM"),
                   "dte": r.get("debtEquityRatioTTM"),
                   "fps": k.get("freeCashFlowPerShareTTM")})
        stats["written"] += 1
        if (i + 1) % 100 == 0:
            print(f"  ttm {i+1}/{len(symbols)}", flush=True)
    print(f"ttm sweep done: {stats}")
    return stats


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    if "--backfill" in sys.argv:
        backfill_universe(get_engine())
    elif "--ttm" in sys.argv:
        ttm_sweep(get_engine())
