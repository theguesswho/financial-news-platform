"""Platform health — the alarm that lives OUTSIDE the scheduler process.

The freshness sentinel runs inside the scheduler; when the scheduler
wedged (2026-09-14 → 09-18) it died with it and nothing said so. This
endpoint answers from the API, reads only, and is what an external
monitor pings. 200 = every check passes; 503 = at least one failed,
named in `failing`. Checks (V3 #26 R1):
  scheduler_recent_finish  some scheduler run finished in the last 26h
  blocked_readers          no backend blocked on a core table
  board_snapshot           leaderboard_history covers the last due session
  eod_prices               eod_prices covers the last due session
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from sqlalchemy import text

from api.deps import get_engine
from api.trading_days import last_trading_day

router = APIRouter(prefix="/health", tags=["health"])

MAX_HOURS_SINCE_FINISH = 26
CORE_TABLES = ("fundamentals", "leaderboard_history", "filings", "eod_prices")


def _run_checks() -> dict:
    now = datetime.now(timezone.utc)
    due = last_trading_day(now)
    checks: dict = {}
    with get_engine().connect() as conn:
        latest_finish = conn.execute(
            text("SELECT MAX(finished_at) FROM scheduler_runs")).scalar()
        age_h = ((now.replace(tzinfo=None) - latest_finish).total_seconds() / 3600
                 if latest_finish else None)
        checks["scheduler_recent_finish"] = {
            "ok": age_h is not None and age_h <= MAX_HOURS_SINCE_FINISH,
            "latest_finish": latest_finish.isoformat() if latest_finish else None,
            "age_hours": round(age_h, 1) if age_h is not None else None,
            "max_hours": MAX_HOURS_SINCE_FINISH,
        }

        blocked = conn.execute(text("""
            SELECT pid, EXTRACT(EPOCH FROM now() - query_start)::int AS secs,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 80) AS q
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND cardinality(pg_blocking_pids(pid)) > 0
        """)).fetchall()
        detail = [{"pid": r[0], "waiting_s": r[1], "query": r[2]} for r in blocked
                  if any(t in (r[2] or "").lower() for t in CORE_TABLES)]
        checks["blocked_readers"] = {"ok": not detail, "blocked": len(detail),
                                     "tables": list(CORE_TABLES), "detail": detail[:5]}

        for name, sql in (("board_snapshot", "SELECT MAX(date) FROM leaderboard_history"),
                          ("eod_prices", "SELECT MAX(date) FROM eod_prices")):
            latest = conn.execute(text(sql)).scalar()
            checks[name] = {"ok": latest is not None and latest >= due,
                            "latest": latest.isoformat() if latest else None,
                            "expected_min": due.isoformat()}
    failing = [k for k, v in checks.items() if not v["ok"]]
    return {"status": "ok" if not failing else "fail",
            "checked_at": now.isoformat(timespec="seconds"),
            "last_trading_day": due.isoformat(),
            "checks": checks, "failing": failing}


@router.get("/platform")
def platform_health(response: Response):
    try:
        body = _run_checks()
    except Exception as exc:  # DB down, statement timeout, anything
        response.status_code = 503
        return {"status": "fail", "error": str(exc)[:200],
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if body["status"] != "ok":
        response.status_code = 503
    return body
