"""Operations readout — the drain verification surface (T6, 2026-10-31).

Read-only. What the desk and Edmund check daily while the backlog drains:
backlog counts by surface, LLM usage by module (24h / 7d) and by budget,
8-Ks stored per day, board seats whose verdict is older than their latest
filing, recent runs with status and failed steps, and the pre-flight.
Every section is tolerant: a column or table that the migration has not
created yet comes back as {"error": ...}, never as a 500.
"""
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from api.deps import get_engine

router = APIRouter(prefix="/ops", tags=["ops"])


def _rows(conn, sql, **p):
    try:
        with conn.begin_nested():
            return [list(r) for r in conn.execute(text(sql), p).fetchall()]
    except Exception as exc:
        return {"error": str(exc)[:160]}


def _one(conn, sql, **p):
    try:
        with conn.begin_nested():
            return conn.execute(text(sql), p).scalar()
    except Exception as exc:
        return {"error": str(exc)[:160]}


def _fix(v):
    if isinstance(v, list):
        return [_fix(x) for x in v]
    if isinstance(v, dict):
        return {k: _fix(x) for k, x in v.items()}
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if type(v).__name__ == "Decimal":
        return float(v)
    return v


@router.get("/backlog")
def backlog():
    now = datetime.now(timezone.utc)
    out: dict = {"checked_at": now.isoformat(timespec="seconds")}
    with get_engine().connect() as conn:
        out["backlog"] = {
            "filings_without_analysis_by_type_30d": _rows(conn, """
                SELECT f.filing_type, COUNT(*) FROM filings f
                WHERE f.created_at >= NOW() - INTERVAL '30 days'
                  AND f.filing_type IN ('10-Q','10-K','EARN_CALL','8-K')
                  AND NOT EXISTS (SELECT 1 FROM filing_themes ft WHERE ft.filing_id = f.id)
                GROUP BY 1 ORDER BY 2 DESC"""),
            "calls_without_claims_30d": _one(conn, """
                SELECT COUNT(*) FROM filings f WHERE f.filing_type = 'EARN_CALL'
                  AND f.filing_date >= NOW() - INTERVAL '30 days'
                  AND NOT EXISTS (SELECT 1 FROM earnings_claims ec WHERE ec.filing_id = f.id)"""),
            "filers_unassessed_since_filing_30d": _one(conn, """
                SELECT COUNT(DISTINCT f.symbol) FROM filings f
                WHERE f.filing_type IN ('10-Q','10-K') AND f.created_at >= NOW() - INTERVAL '30 days'
                  AND NOT EXISTS (SELECT 1 FROM qual_assessments q
                                  WHERE q.symbol = f.symbol AND q.assessed_at >= f.created_at)"""),
            "symbols_awaiting_ledger": _one(conn, """
                WITH ledger AS (SELECT symbol, MIN(last_evidence_at) AS since
                                FROM narrative_exposures GROUP BY symbol)
                SELECT COUNT(DISTINCT ne.symbol) FROM ledger ne
                JOIN filings f ON f.symbol = ne.symbol AND f.filing_date > ne.since
                  AND (f.filing_type IN ('10-K','10-Q','EARN_CALL')
                       OR (f.filing_type = '8-K' AND f.event_type IS NOT NULL))"""),
            "checkpoints_overdue_pending": _one(conn, """
                SELECT COUNT(*) FROM narrative_checkpoints
                WHERE status = 'pending' AND deadline < CURRENT_DATE"""),
            "eight_k_unclassified": _one(conn, """
                SELECT COUNT(*) FROM filings
                WHERE filing_type IN ('8-K','8-K/A') AND event_type IS NULL"""),
            "backfilled_filings_30d": _one(conn, """
                SELECT COUNT(*) FROM filings
                WHERE COALESCE(backfilled, FALSE) AND created_at >= NOW() - INTERVAL '30 days'"""),
        }
        out["board_seats_verdict_older_than_filing"] = _rows(conn, """
            SELECT l.symbol, COALESCE(l.assessed_tier, l.tier), q.assessed_at::date, lf.fd
            FROM leaderboard_history l
            LEFT JOIN qual_assessments q ON q.symbol = l.symbol
            JOIN LATERAL (SELECT MAX(created_at)::date AS fd FROM filings f
                          WHERE f.symbol = l.symbol
                            AND f.filing_type IN ('10-Q','10-K','EARN_CALL')) lf ON TRUE
            WHERE l.date = (SELECT MAX(date) FROM leaderboard_history)
              AND COALESCE(l.assessed_tier, l.tier) IN ('Strong Buy','Buy','Watch')
              AND (q.assessed_at IS NULL OR q.assessed_at::date < lf.fd)
            ORDER BY l.final_rank NULLS LAST""")
        out["eight_k_stored_per_day_14d"] = _rows(conn, """
            SELECT created_at::date, COUNT(*) FROM filings
            WHERE filing_type IN ('8-K','8-K/A') AND created_at >= CURRENT_DATE - 14
            GROUP BY 1 ORDER BY 1""")
        out["llm_usage"] = {
            "by_module_24h": _rows(conn, """
                SELECT module, COUNT(*), ROUND(SUM(est_cost_usd)::numeric, 2) FROM llm_usage
                WHERE called_at >= NOW() - INTERVAL '24 hours' GROUP BY 1 ORDER BY 3 DESC"""),
            "by_module_7d": _rows(conn, """
                SELECT module, COUNT(*), ROUND(SUM(est_cost_usd)::numeric, 2) FROM llm_usage
                WHERE called_at >= NOW() - INTERVAL '7 days' GROUP BY 1 ORDER BY 3 DESC"""),
            "by_budget_today": _rows(conn, """
                SELECT COALESCE(budget, 'daily'), COUNT(*), ROUND(SUM(est_cost_usd)::numeric, 2)
                FROM llm_usage WHERE called_at >= CURRENT_DATE GROUP BY 1"""),
            "per_day_14d": _rows(conn, """
                SELECT called_at::date, COUNT(*), ROUND(SUM(est_cost_usd)::numeric, 2) FROM llm_usage
                WHERE called_at >= CURRENT_DATE - 14 GROUP BY 1 ORDER BY 1"""),
        }
        out["runs_recent"] = _rows(conn, """
            SELECT job_id, slot_ts, status, ROUND(EXTRACT(EPOCH FROM finished_at - started_at)/60), error
            FROM scheduler_runs ORDER BY slot_ts DESC LIMIT 8""")
        out["steps_failed_48h"] = _rows(conn, """
            SELECT job_id, slot_ts, step, status, error FROM scheduler_steps
            WHERE started_at >= NOW() - INTERVAL '48 hours' AND status IN ('failed','deferred','held')
            ORDER BY started_at DESC LIMIT 40""")
        out["llm_preflight_latest"] = _one(conn, """
            SELECT result FROM env_diagnostics WHERE source = 'llm_preflight' ORDER BY id DESC LIMIT 1""")
        out["freshness_latest"] = _one(conn, """
            SELECT result FROM env_diagnostics WHERE source = 'freshness' ORDER BY id DESC LIMIT 1""")
    return _fix(out)
