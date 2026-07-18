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
    ("historical_metrics",  "SELECT MAX(date) FROM historical_metrics",                                115),
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


def run_sentinel(engine) -> list[dict]:
    """Check, log loudly, persist latest result for the brief to read."""
    import json
    violations = check_freshness(engine)
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
