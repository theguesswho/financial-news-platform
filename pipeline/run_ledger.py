"""
Run ledger for the scheduler — failures are not `ok` (V3 #28, T6 min set).

Three things, all fail-open (bookkeeping never breaks a run):

1. Per-step results in the DATABASE (`scheduler_steps`), written by the
   child process that runs the job: start, finish, status ok | failed |
   deferred | held, error text, counters. The parent reads them when the
   child exits and stamps the run `degraded` if any step failed. Nothing
   about a diagnosis depends on Railway log retention any more.

2. Pre-flight: one 5-token Haiku call at the start of each run. A billing
   400 ("credit balance is too low") or an auth 401 becomes a NAMED alarm
   in env_diagnostics (source='llm_preflight') and in the brief, instead
   of nine days of steps failing quietly inside their try/except.

3. Spend guards: a daily ceiling (DAILY_LLM_BUDGET_USD, default 8) for
   same-day work and a separate drain budget (DRAIN_BUDGET_USD_DAILY,
   default 12, only while DRAIN_MODE=1) for catch-up work on the backlog.
   Each LLM-heavy step asks `budget_ok(kind)` before it starts; over
   budget → the step is recorded `deferred` with the reason and the run
   is `degraded`, never silent. Spend is read from llm_usage, which
   stamps every call with the budget it ran under (llm_usage.CURRENT_BUDGET).
"""
import json
import os
from datetime import datetime

from sqlalchemy import text

# Set by scheduler_light's child entry point: {"job": ..., "slot": datetime}
CTX: dict = {"job": None, "slot": None, "step": None, "engine": None}


def _engine():
    if CTX.get("engine") is None:
        from pipeline.hidden_gem_scorer import get_engine
        CTX["engine"] = get_engine()
    return CTX["engine"]


def _active() -> bool:
    return bool(CTX.get("job") and CTX.get("slot"))


def step_start(step, label: str) -> None:
    CTX["step"] = str(step)
    if not _active():
        return
    try:
        with _engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO scheduler_steps (job_id, slot_ts, step, label, started_at, status)
                VALUES (:j, :s, :st, :l, NOW(), 'running')
            """), {"j": CTX["job"], "s": CTX["slot"], "st": str(step), "l": label[:200]})
    except Exception:
        pass


def step_end(status: str, note: str | None = None, error: str | None = None) -> None:
    """status: ok | failed | deferred | held.
    'ok' closes the latest OPEN row of the current step (a step that prints
    _ok twice closes once; later _ok lines are no-ops). A failure recorded
    AFTER an earlier _ok inside the same step (the assessor sweep prints
    progress with _ok) must still count: failed/deferred/held overwrite
    the latest row of the step whether or not it is open."""
    if not _active() or not CTX.get("step"):
        return
    open_only = "AND finished_at IS NULL" if status == "ok" else ""
    try:
        with _engine().begin() as conn:
            conn.execute(text(f"""
                UPDATE scheduler_steps SET finished_at = NOW(), status = :x, note = :n, error = :e
                WHERE id = (SELECT id FROM scheduler_steps
                            WHERE job_id = :j AND slot_ts = :s AND step = :st {open_only}
                            ORDER BY id DESC LIMIT 1)
            """), {"x": status, "n": (note or "")[:500] or None, "e": (error or "")[:500] or None,
                   "j": CTX["job"], "s": CTX["slot"], "st": CTX["step"]})
    except Exception:
        pass


def instance_tag() -> str:
    """Which scheduler instance is talking: Railway project/service and
    deployment when Railway provides them, else the host; plus the pid.
    Stamped on the run claim, the pre-flight row and any duplicate alarm,
    so a second scheduler is NAMED in the database, never inferred
    (2026-11-01: a forgotten second project ran every job for four months)."""
    import socket
    proj = os.getenv("RAILWAY_PROJECT_NAME") or "-"
    svc = os.getenv("RAILWAY_SERVICE_NAME") or "-"
    dep = (os.getenv("RAILWAY_DEPLOYMENT_ID") or "")[:8]
    if not dep:
        try:
            dep = socket.gethostname()[:24]
        except Exception:
            dep = "?"
    return f"{proj}/{svc}@{dep}:{os.getpid()}"[:120]


def alarm(engine, source: str, payload: dict) -> None:
    """Named alarm row in env_diagnostics. Fail-open."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS env_diagnostics (
                    id SERIAL PRIMARY KEY, source VARCHAR(40), result JSONB,
                    created_at TIMESTAMP DEFAULT NOW())"""))
            conn.execute(text("INSERT INTO env_diagnostics (source, result) VALUES (:s, :r)"),
                         {"s": source[:40], "r": json.dumps(payload, default=str)})
    except Exception:
        pass


def failed_steps(engine, job_id: str, slot) -> list[str]:
    """Steps of one run that ended failed/deferred (parent reads this)."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT step, status FROM scheduler_steps
                WHERE job_id = :j AND slot_ts = :s AND status IN ('failed', 'deferred')
                ORDER BY id
            """), {"j": job_id, "s": slot}).fetchall()
        return [f"{r[0]}:{r[1]}" for r in rows]
    except Exception:
        return []


# ── Pre-flight ───────────────────────────────────────────────────────────────

def preflight(engine, instance: str | None = None) -> dict:
    """One tiny call. Returns {"ok": bool, "kind": ok|billing|auth|other, "detail": str}.
    Writes env_diagnostics(source='llm_preflight') on every run so the brief
    and /health/platform can name a failure; `instance` names who ran it."""
    out = {"ok": True, "kind": "ok", "detail": ""}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        client.messages.create(model="claude-haiku-4-5", max_tokens=5,
                               messages=[{"role": "user", "content": "ping"}])
    except Exception as exc:  # noqa: BLE001 — classify, never raise
        msg = str(exc)[:300]
        code = getattr(exc, "status_code", None)
        if code == 400 and "credit" in msg.lower():
            kind = "billing"
        elif code in (401, 403):
            kind = "auth"
        else:
            kind = "other"
        out = {"ok": False, "kind": kind, "detail": msg}
    if instance:
        out["instance"] = instance
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS env_diagnostics (
                    id SERIAL PRIMARY KEY, source VARCHAR(40), result JSONB,
                    created_at TIMESTAMP DEFAULT NOW())"""))
            conn.execute(text("INSERT INTO env_diagnostics (source, result) VALUES ('llm_preflight', :r)"),
                         {"r": json.dumps(out)})
    except Exception:
        pass
    return out


# ── Spend guards ─────────────────────────────────────────────────────────────

def budgets() -> dict:
    daily = float(os.getenv("DAILY_LLM_BUDGET_USD", "8"))
    drain_on = os.getenv("DRAIN_MODE", "1") == "1"
    drain = float(os.getenv("DRAIN_BUDGET_USD_DAILY", "12")) if drain_on else 0.0
    return {"daily": daily, "drain": drain, "drain_mode": drain_on}


def spend_today(engine) -> dict:
    """Estimated $ today by budget tag (UTC day). Unknown/NULL tag counts as daily."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT COALESCE(budget, 'daily'), ROUND(COALESCE(SUM(est_cost_usd), 0)::numeric, 2)
                FROM llm_usage WHERE called_at >= CURRENT_DATE GROUP BY 1""")).fetchall()
        out = {"daily": 0.0, "drain": 0.0}
        for k, v in rows:
            out[k if k in out else "daily"] = out.get(k if k in out else "daily", 0.0) + float(v)
        return out
    except Exception:
        return {"daily": 0.0, "drain": 0.0}


def budget_ok(engine, kind: str) -> tuple[bool, str]:
    """kind: 'daily' | 'drain'. Drain falls back to the daily ceiling when
    DRAIN_MODE is off. Returns (ok, one-line reason)."""
    b = budgets()
    s = spend_today(engine)
    if kind == "drain" and not b["drain_mode"]:
        kind = "daily"
    cap = b[kind]
    spent = s.get(kind, 0.0)
    if spent >= cap:
        return False, f"{kind} budget exhausted: ${spent:.2f} of ${cap:.2f} today"
    return True, f"{kind} budget ${spent:.2f} of ${cap:.2f}"
