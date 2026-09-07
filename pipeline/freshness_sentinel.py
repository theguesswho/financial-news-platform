"""
Data freshness sentinel — converts silent pipeline death into a loud alarm.

Born from the July 2026 transcript outage: FMP-fed ingestion produced zero
rows for THREE WEEKS and nothing noticed, because every failure path was a
bare `except` and "no new rows" looks identical to "quiet week".

Every source table declares a maximum acceptable staleness. The daily run
checks all of them; violations are logged loudly, stored (env_diagnostics,
source='freshness'), and surfaced in the daily brief as system-health
warnings the user actually sees.
"""
from sqlalchemy import text

# (name, SQL returning the latest timestamp/date, max acceptable age in days)
EXPECTATIONS = [
    ("eod_prices",          "SELECT MAX(date) FROM eod_prices",                                          4),
    ("leaderboard",         "SELECT MAX(date) FROM leaderboard_history",                                 2),
    ("daily_brief",         "SELECT MAX(date) FROM daily_briefs",                                        2),
    ("8-K filings",         "SELECT MAX(filing_date) FROM filings WHERE filing_type IN ('8-K','8-K/A')", 5),
    ("earnings transcripts","SELECT MAX(filing_date) FROM filings WHERE filing_type='EARN_CALL'",        7),
    ("fundamentals",        "SELECT MAX(fetched_at) FROM fundamentals",                                  8),
    ("qual_assessments",    "SELECT MAX(assessed_at) FROM qual_assessments",                             8),
    ("narrative_exposures", "SELECT MAX(updated_at) FROM narrative_exposures",                           9),
    ("narrative_history",   "SELECT MAX(snapshot_date) FROM narrative_history",                          9),
    ("insider_trades",      "SELECT MAX(created_at) FROM insider_trades",                                7),
    # historical_metrics (weekly FMP table, scheduler step 6): 115d on the
    # quarter-end date hid a dead table for four months (V3 #21). Two bars
    # now — a 10-day bar on the refresh heartbeat (fetched_at, stamped on
    # every row the weekly upsert touches) and a 60-day bar on the newest
    # quarter-end, which lags 30-50 days by construction (10-Q lag).
    ("historical_metrics",  "SELECT MAX(fetched_at) FROM historical_metrics",                           10),
    ("historical_metrics newest quarter", "SELECT MAX(date) FROM historical_metrics",                    60),
]


def check_freshness(engine) -> list[dict]:
    """Return list of violations: [{source, latest, age_days, max_days}]."""
    violations = []
    with engine.connect() as conn:
        for name, sql, max_days in EXPECTATIONS:
            try:
                latest = conn.execute(text(sql)).scalar()
                age = conn.execute(text("SELECT EXTRACT(EPOCH FROM (NOW() - :ts))/86400"),
                                   {"ts": latest}).scalar() if latest else None
            except Exception as exc:
                violations.append({"source": name, "latest": None,
                                   "age_days": None, "max_days": max_days,
                                   "error": str(exc)[:120]})
                continue
            if latest is None or (age is not None and age > max_days):
                violations.append({"source": name,
                                   "latest": str(latest) if latest else "NEVER",
                                   "age_days": round(float(age), 1) if age else None,
                                   "max_days": max_days})
    return violations


# Growth-block content check (V3 #20c, 2026-09-06/07 — the AECOM lesson):
# MAX(fetched_at) says a row was touched, not that its CONTENT is current.
# Per symbol, the quarter the score uses (fundamentals.growth_quarter_end,
# stamped by pipeline/fmp_quarterly.py) is compared with the latest
# 10-Q/10-K on record in `filings`. Stated latency (DATA_SCORECARD A):
# the filing evening (step 3d) or the next 06:00 daily sweep.
#
# The rule keys on the QUARTER END, not on FMP's fillingDate: that vendor
# stamp is the earnings-release date for some filers (NUE 07-27 vs 10-Q
# 08-12) and a placeholder equal to the period end for others (MDLN,
# PNFP) — comparing it to the SEC date produced false alarms on correct
# quarters (found 2026-09-07). Calibration on the live universe the same
# day: the gap between the score's quarter end and the latest 10-Q/10-K
# was 10..62 days for every one of 820 symbols; a quarter that PREDATES
# the latest filing's period sits >= ~100 days behind it (ACM's stale
# March quarter vs the 08-11 10-Q: 133 days). 95 days splits the two.
GROWTH_MAX_DAYS = 3         # days after the latest 10-Q/10-K before a stale quarter is a breach
GROWTH_QUARTER_GAP_DAYS = 95  # quarter_end older than this vs the filing date = not the filed quarter


def check_growth_quarters(engine) -> list[dict]:
    """One violation per symbol whose growth block predates its latest
    10-Q/10-K by more than the stated latency. Shape matches the table
    checks so the brief prints it unchanged: source names the symbol.
    Symbols with no 10-Q/10-K on record are not checked (nothing to
    compare against); a NULL quarter with a filing on record IS a breach."""
    sql = text("""
        SELECT f.symbol, f.growth_source, f.growth_quarter_end,
               f.growth_filing_date, lf.filing_date::date AS latest_filing,
               EXTRACT(EPOCH FROM (NOW() - lf.filing_date))/86400 AS age_days
        FROM fundamentals f
        JOIN LATERAL (
            SELECT MAX(filing_date) AS filing_date FROM filings
            WHERE symbol = f.symbol AND filing_type IN ('10-Q', '10-K')
        ) lf ON true
        WHERE lf.filing_date IS NOT NULL
          AND lf.filing_date < NOW() - (:max_days || ' days')::interval
          AND (f.growth_quarter_end IS NULL
               OR f.growth_quarter_end < lf.filing_date::date - :gap)
        ORDER BY lf.filing_date DESC, f.symbol
    """)
    out = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, {"max_days": GROWTH_MAX_DAYS,
                                      "gap": GROWTH_QUARTER_GAP_DAYS}).fetchall()
    except Exception as exc:
        return [{"source": "growth_quarter", "latest": None, "age_days": None,
                 "max_days": GROWTH_MAX_DAYS, "error": str(exc)[:120]}]
    for sym, src, qend, fdate, latest_filing, age in rows:
        out.append({"source": f"growth_quarter:{sym}",
                    "symbol": sym,
                    "growth_source": src,
                    "latest": (f"score quarter {qend} ({src}, vendor stamp {fdate})"
                               if qend else f"no quarter in score ({src})"),
                    "latest_filing": str(latest_filing),
                    "age_days": round(float(age), 1) if age is not None else None,
                    "max_days": GROWTH_MAX_DAYS})
    return out


def run_sentinel(engine) -> list[dict]:
    """Check, log loudly, persist latest result for the brief to read."""
    import json
    violations = check_freshness(engine) + check_growth_quarters(engine)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS env_diagnostics (
                id SERIAL PRIMARY KEY, source VARCHAR(30),
                result JSONB, created_at TIMESTAMP DEFAULT NOW())
        """))
        conn.execute(text(
            "INSERT INTO env_diagnostics (source, result) VALUES ('freshness', :r)"),
            {"r": json.dumps(violations)})
    if violations:
        print("🚨 DATA FRESHNESS VIOLATIONS:")
        for v in violations:
            print(f"   {v['source']}: latest={v['latest']} "
                  f"(age {v['age_days']}d, max {v['max_days']}d)")
    else:
        print("✓ All data sources within freshness expectations")
    return violations


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    run_sentinel(get_engine())
