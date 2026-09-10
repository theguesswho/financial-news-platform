"""
Growth / quarterly block — FMP-owned (V3 #20, the AECOM growth lesson,
2026-09-06).

The two values that decide the growth penalty (revenue_growth_yoy,
earnings_growth_yoy), fcf_growth_yoy, and the 8-quarter quarterly_trends
JSON (dates, revenue, gross/op margin, net income, FCF) used to come from
Yahoo's quarterly statement tables, which publish a quarter WEEKS after
the filing (ACM: 25 days). FMP — declared owner of "what companies
report" on 2026-08-09 — stamps the quarter on filing day.

Doctrine (DATA_SCORECARD.md section A):
  * FMP quarterly income + cash-flow statements own the block for every
    symbol FMP covers. Yahoo (pipeline/fundamentals.py) writes these
    fields ONLY while fundamentals.growth_source != 'fmp'.
  * Provenance is stored ON THE ROW: growth_source, growth_quarter_end,
    growth_filing_date, growth_fetched_at — and mirrored inside the
    JSON as "_provenance" so the JSON is self-describing.
  * Income and cash-flow rows are aligned BY POSITION, not by date:
    52/53-week filers carry different period stamps on the two
    statements (ACM: income 2026-06-30, cash-flow 2026-07-03, same
    quarter). quarter_end / filing_date are the income statement's.
    filing_date is FMP's fillingDate — a VENDOR STAMP, not the SEC filing
    date: it is the earnings-release date for some filers (NUE 07-27 vs
    10-Q 08-12) and a period-end placeholder for others (MDLN, PNFP).
    Kept for audit; the sentinel keys on quarter_end, never on it.
  * Growth is Q vs the same Q a year earlier, positionally (index -1 vs
    index -5 of the 8-quarter block); both values must be present.
    Denominator is |prior| so a loss-to-smaller-loss reads as growth.

Expected latency (stated, DATA_SCORECARD): the filing evening (step 3d
dirty re-fetch) or the next 06:00 daily sweep at the latest — FMP stamps
fillingDate on the day the statement is filed.

Cost: 2 FMP calls per symbol, zero LLM.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import text

BASE = "https://financialmodelingprep.com/api/v3"
THROTTLE_S = 0.25
QUARTERS = 8
WORKERS = 4

PROVENANCE_COLUMNS_SQL = """
    ALTER TABLE fundamentals
        ADD COLUMN IF NOT EXISTS growth_source      VARCHAR(10),
        ADD COLUMN IF NOT EXISTS growth_quarter_end DATE,
        ADD COLUMN IF NOT EXISTS growth_filing_date DATE,
        ADD COLUMN IF NOT EXISTS growth_fetched_at  TIMESTAMP
"""


def _get(path: str, **params):
    params["apikey"] = os.environ.get("FMP_API_KEY", "")
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(f"{BASE}/{path}?{qs}", timeout=30) as r:
            data = json.loads(r.read())
        return data if isinstance(data, list) else None
    except Exception:
        return None


def _num(v):
    try:
        f = float(v)
        return None if (f != f or abs(f) > 1e15) else f
    except (TypeError, ValueError):
        return None


PROVENANCE_COLUMNS = ("growth_source", "growth_quarter_end",
                      "growth_filing_date", "growth_fetched_at")
DDL_LOCK_TIMEOUT = "5s"


def ensure_columns(engine) -> bool:
    """Add the provenance columns if — and only if — they are missing.

    Returns True when the table already had them (no DDL issued).

    Postgres takes ACCESS EXCLUSIVE for ALTER TABLE even when every
    ADD COLUMN IF NOT EXISTS is a no-op, and a waiting exclusive lock
    blocks every new reader of the table. On 2026-09-09 that ALTER sat
    behind an idle-in-transaction session for 14 hours and took the
    site down with it. So: look first, and when DDL is truly needed
    give it a short lock_timeout so a blocked migration fails loudly
    instead of freezing /board.
    """
    with engine.connect() as conn:
        present = {r[0] for r in conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'fundamentals' AND column_name = ANY(:cols)
        """), {"cols": list(PROVENANCE_COLUMNS)})}
    if present >= set(PROVENANCE_COLUMNS):
        return True
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SET LOCAL lock_timeout = '{DDL_LOCK_TIMEOUT}'"))
            conn.execute(text(PROVENANCE_COLUMNS_SQL))
        print(f"  [growth] added provenance columns "
              f"{sorted(set(PROVENANCE_COLUMNS) - present)}", flush=True)
    except Exception as exc:
        # Do not hang, do not hide: the refresh continues (writes use
        # only columns that exist) and the operator sees why.
        print(f"  [growth] provenance DDL skipped — {str(exc)[:160]}", flush=True)
    return False


def yoy_growth(series: list) -> float | None:
    """Q vs same Q a year earlier, POSITIONAL (index -1 vs -5). Needs at
    least 5 quarters with both endpoints present; prior != 0."""
    if len(series) < 5:
        return None
    curr, prior = series[-1], series[-5]
    if curr is None or prior is None or prior == 0:
        return None
    return round((curr - prior) / abs(prior), 4)


def build_block(income: list, cashflow: list) -> dict | None:
    """Pure: FMP quarterly income + cash-flow (newest-first lists) ->
    quarterly_trends-shaped dict (oldest -> newest) with _provenance.
    Returns None when the income statement is empty."""
    inc = [r for r in (income or []) if isinstance(r, dict) and r.get("date")][:QUARTERS]
    if not inc:
        return None
    cf = [r for r in (cashflow or []) if isinstance(r, dict)][:QUARTERS]
    inc = inc[::-1]                       # oldest -> newest
    cf = cf[::-1]
    # Align by position from the NEWEST end (both lists are newest-first
    # from FMP); a shorter cash-flow list leaves the oldest slots None.
    pad = len(inc) - len(cf)
    cf = ([None] * pad + cf) if pad > 0 else cf[-len(inc):]

    dates, revenue, gm, om, ni, fcf = [], [], [], [], [], []
    for r, c in zip(inc, cf):
        rev = _num(r.get("revenue"))
        gp = _num(r.get("grossProfit"))
        oi = _num(r.get("operatingIncome"))
        dates.append(str(r["date"])[:10])
        revenue.append(rev)
        gm.append(round(gp / rev, 4) if rev and gp is not None else None)
        om.append(round(oi / rev, 4) if rev and oi is not None else None)
        ni.append(_num(r.get("netIncome")))
        fcf.append(_num(c.get("freeCashFlow")) if c else None)

    newest = inc[-1]
    return {
        "dates": dates,
        "revenue": revenue,
        "gross_margin": gm,
        "operating_margin": om,
        "net_income": ni,
        "fcf": fcf,
        "_provenance": {
            "source": "fmp",
            "quarter_end": str(newest["date"])[:10],
            "period": newest.get("period"),
            "filing_date": (newest.get("fillingDate") or "")[:10] or None,
            "accepted_date": newest.get("acceptedDate"),
            "cashflow_quarter_end": str(cf[-1]["date"])[:10] if cf and cf[-1] else None,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }


def fetch_block(sym: str) -> dict | None:
    """_get returns None on a transport failure and [] when FMP has no
    data; a failure gets one retry so a dropped request is not mistaken
    for "FMP has nothing" (LW/MAS, 2026-09-07)."""
    inc = _get(f"income-statement/{sym}", period="quarter", limit=QUARTERS)
    time.sleep(THROTTLE_S)
    if inc is None:
        time.sleep(1.0)
        inc = _get(f"income-statement/{sym}", period="quarter", limit=QUARTERS)
        time.sleep(THROTTLE_S)
    cf = _get(f"cash-flow-statement/{sym}", period="quarter", limit=QUARTERS)
    time.sleep(THROTTLE_S)
    if cf is None:
        time.sleep(1.0)
        cf = _get(f"cash-flow-statement/{sym}", period="quarter", limit=QUARTERS)
        time.sleep(THROTTLE_S)
    return build_block(inc, cf)


def write_block(conn, sym: str, block: dict) -> None:
    """Write growth fields + JSON + provenance for one symbol. Keeps any
    '_'-prefixed stash keys already in quarterly_trends (themes)."""
    existing = conn.execute(text(
        "SELECT quarterly_trends FROM fundamentals WHERE symbol = :s"),
        {"s": sym}).scalar()
    merged = {}
    if existing:
        try:
            merged = {k: v for k, v in json.loads(existing).items()
                      if k.startswith("_") and k != "_provenance"}
        except Exception:
            merged = {}
    merged.update(block)
    prov = block["_provenance"]
    conn.execute(text("""
        UPDATE fundamentals SET
            revenue_growth_yoy  = :rg,
            earnings_growth_yoy = :eg,
            fcf_growth_yoy      = :fg,
            quarterly_trends    = :qt,
            growth_source       = 'fmp',
            growth_quarter_end  = :qe,
            growth_filing_date  = :fd,
            growth_fetched_at   = NOW()
        WHERE symbol = :s
    """), {"s": sym,
           "rg": yoy_growth(block["revenue"]),
           "eg": yoy_growth(block["net_income"]),
           "fg": yoy_growth(block["fcf"]),
           "qt": json.dumps(merged),
           "qe": prov["quarter_end"],
           "fd": prov["filing_date"]})


def refresh_growth_block(engine, symbols=None) -> dict:
    """Re-home the quarterly block onto FMP for `symbols` (default: every
    fundamentals row). A symbol FMP returns nothing for is left untouched
    — its growth_source stays whatever it was, so the Yahoo fetch keeps
    filling it (fallback ONLY when FMP returns nothing)."""
    ensure_columns(engine)
    with engine.connect() as conn:
        if symbols is None:
            symbols = [r[0] for r in conn.execute(
                text("SELECT symbol FROM fundamentals ORDER BY symbol")).fetchall()]
    stats = {"symbols": len(symbols), "written": 0, "empty": []}
    # Fetch in a small pool (FMP round-trips are ~2s each from the
    # scheduler host; serial = ~70 min for the universe, too slow for the
    # 06:00 slot). 4 workers x 2 calls x 0.25s throttle stays well under
    # FMP's per-minute limit. DB writes stay sequential on this thread.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, (sym, block) in enumerate(zip(symbols, pool.map(fetch_block, symbols))):
            if block is None:
                stats["empty"].append(sym)
                continue
            # Railway's proxy drops connections mid-run (seen 2026-09-06 at
            # symbol ~530): one retry on a fresh pool, then record and go on.
            for attempt in (1, 2):
                try:
                    with engine.begin() as conn:
                        write_block(conn, sym, block)
                    stats["written"] += 1
                    break
                except Exception as exc:
                    engine.dispose()
                    if attempt == 2:
                        stats.setdefault("errors", []).append(f"{sym}: {str(exc)[:80]}")
            if (i + 1) % 100 == 0:
                print(f"  growth block {i+1}/{len(symbols)}", flush=True)
    stats["empty_count"] = len(stats["empty"])
    stats["empty"] = stats["empty"][:20]
    stats["error_count"] = len(stats.get("errors", []))
    print(f"growth block done: {stats}")
    return stats


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    syms = [a.upper() for a in sys.argv[1:]] or None
    refresh_growth_block(get_engine(), syms)
