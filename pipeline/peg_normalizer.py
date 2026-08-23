"""
Consensus PEG — forward-looking growth denominator (user-specified 2026-07-21).

History of this file: Yahoo's vendor pegRatio divides by recent GAAP trailing
growth (HWM: 69% recovery spike -> PEG 0.8 vs a defensible ~2). A first fix
using trailing internal data failed differently (PODD: +157% GAAP artifact
with no history -> PEG 0.13 while the honest number was ~1.5). Lesson:
ANY trailing-GAAP denominator is unfixable. Analyst consensus EPS is
adjusted (one-offs stripped), forward-anchored, and covered 12/12 in testing
including 1-analyst mid-caps.

Formula (exact user spec):
    g0  = current-year consensus EPS vs year-ago ACTUAL EPS
    g1  = next-year consensus EPS  vs current-year consensus
    growth    = average(g0, g1)          [fall back to whichever exists]
    peg_ratio = pe_forward / (growth * 100),  NULL if growth <= 0

Source: yfinance earnings_estimate table ('growth' column of the 0y / +1y
rows). Analyst count stored in peg_analysts — a 2-analyst PEG deserves less
trust than a 25-analyst one. Vendor value kept in peg_vendor for audit.
On fetch failure the existing stored PEG is KEPT, never nulled by transience.

Validation examples at build time:
    PODD (20.4 fwd PE): (30.3 + 24.3)/2 = 27.3%  -> 0.75   (was 0.13)
    HWM  (45.0 fwd PE): (~25 + 19.5)/2  ~ 22%    -> ~2.0   (matches public)
"""
import time

from sqlalchemy import text


def _consensus_growth(symbol: str):
    """Return (avg_growth, n_analysts) from Yahoo's estimate table, or (None, None)."""
    import yfinance as yf
    try:
        ee = yf.Ticker(symbol).earnings_estimate
        if ee is None or ee.empty:
            return None, None
        legs = []
        n = None
        for period in ("0y", "+1y"):
            if period in ee.index:
                g = ee.loc[period, "growth"]
                if g is not None and g == g:          # not NaN
                    legs.append(float(g))
                na = ee.loc[period, "numberOfAnalysts"]
                if na == na and (n is None or na < n):
                    n = int(na)
        if not legs:
            return None, n
        return sum(legs) / len(legs), n
    except Exception:
        return None, None


def recompute_pegs(engine, max_age_days: int = 3) -> dict:
    """
    Fill consensus PEG for symbols where Yahoo publishes NO vendor PEG
    (user decision 2026-07-22: vendor primary, consensus two-leg fallback).
    Symbols with a vendor PEG get peg_ratio directly from the fundamentals
    fetch and are skipped here.
    """
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS peg_vendor NUMERIC(12,2)"))
        conn.execute(text(
            "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS peg_analysts INTEGER"))
        conn.execute(text(
            "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS peg_updated TIMESTAMP"))
        conn.execute(text(
            "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS peg_source VARCHAR(10)"))

    with engine.connect() as conn:
        # Two trigger classes (amended 2026-08-23, the CRUS lesson;
        # re-amended same day per external review — vendor stays primary
        # EXCEPT conflict-class values):
        #   1. no usable vendor PEG (the original 2026-07-22 fallback) —
        #      subject to the staleness gate as before;
        #   2. CONFLICT-CLASS vendor PEG, tested on peg_VENDOR (the
        #      audit copy — peg_ratio may already be nulled/consensus):
        #      implied consensus growth (fwd_pe/peg_vendor, %) under
        #      3%/yr while DELIVERED earnings growth exceeds 15%
        #      (CRUS 9.35 -> 1.4% implied vs +26.6%). NO staleness gate:
        #      eligible on the SAME run — a same-day vendor write must
        #      not buy junk three days of display. On consensus fetch
        #      failure the junk vendor value is NEVER restored into
        #      peg_ratio: it goes/stays blank (peg_vendor keeps the
        #      audit copy).
        funds = conn.execute(text("""
            SELECT symbol, pe_forward, peg_ratio, peg_vendor,
                   (peg_vendor > 0 AND pe_forward > 0
                    AND (pe_forward / peg_vendor) < 3
                    AND earnings_growth_yoy > 0.15) AS is_conflict
            FROM fundamentals
            WHERE (
                    ((peg_vendor IS NULL OR peg_vendor <= 0 OR peg_vendor >= 99)
                     AND (peg_updated IS NULL
                          OR peg_updated < NOW() - (:d || ' days')::interval))
                 OR (peg_vendor > 0 AND pe_forward > 0
                     AND (pe_forward / peg_vendor) < 3
                     AND earnings_growth_yoy > 0.15
                     AND (peg_ratio IS NOT NULL OR peg_source IS DISTINCT FROM 'consensus'))
                  )
            ORDER BY symbol
        """), {"d": max_age_days}).fetchall()

    stats = {"updated": 0, "nulled": 0, "fetch_failed": 0,
             "conflict_blanked": 0}
    batch = []
    for sym, pe_fwd, peg_now, vendor_stored, is_conflict in funds:
        vendor = vendor_stored if vendor_stored is not None else peg_now
        growth, n_analysts = _consensus_growth(sym)
        time.sleep(0.3)   # polite to Yahoo

        if growth is None and n_analysts is None:
            stats["fetch_failed"] += 1
            if is_conflict:
                # NEVER keep/restore a conflict-class value in peg_ratio —
                # blank beats junk (2026-08-23 rule). Audit copy stays on
                # peg_vendor.
                stats["conflict_blanked"] += 1
                batch.append({"s": sym, "peg": None, "vendor": vendor, "n": None})
            else:
                # transient/no data on a non-conflict row — keep existing
                batch.append({"s": sym, "peg": peg_now, "vendor": vendor, "n": None})
            continue

        peg = None
        if growth and growth > 0 and pe_fwd and float(pe_fwd) > 0:
            peg = round(float(pe_fwd) / (growth * 100), 2)
            if peg < 0 or peg > 99:
                peg = None
        stats["updated" if peg is not None else "nulled"] += 1
        batch.append({"s": sym, "peg": peg, "vendor": vendor, "n": n_analysts})

        if len(batch) >= 100:
            _flush(engine, batch)
            batch = []
    if batch:
        _flush(engine, batch)

    print(f"Consensus PEG: {stats} ({len(funds)} symbols due)")
    return stats


def _flush(engine, batch):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE fundamentals
            SET peg_ratio = :peg, peg_vendor = :vendor, peg_analysts = :n,
                peg_updated = NOW(),
                peg_source = CASE WHEN :peg IS NULL THEN NULL ELSE 'consensus' END
            WHERE symbol = :s
        """), batch)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    recompute_pegs(get_engine(), max_age_days=0)   # CLI: force full refresh
