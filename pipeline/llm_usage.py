"""
LLM usage ledger — every pipeline call records its tokens, cache hits, and
cost so savings are measurable, not estimated (user directive 2026-08-02).

Usage:  from pipeline.llm_usage import record_usage
        resp = client.messages.create(...)
        record_usage(engine_or_none, module="qual_assessor", model=MODEL, usage=resp.usage)

Costs use published per-MTok rates; cache reads billed at 10% of input,
cache writes at 125%. Fail-open: a logging failure never breaks the caller.
"""
from sqlalchemy import text

RATES = {  # (input, output) USD per MTok
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def record_usage(engine, module: str, model: str, usage) -> None:
    try:
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        ri, ro = RATES.get(model, (3.0, 15.0))
        cost = (inp * ri + cw * ri * 1.25 + cr * ri * 0.10) / 1e6 + out * ro / 1e6
        if engine is None:
            from pipeline.hidden_gem_scorer import get_engine
            engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id SERIAL PRIMARY KEY,
                    module VARCHAR(40), model VARCHAR(40),
                    input_tokens INTEGER, output_tokens INTEGER,
                    cache_write_tokens INTEGER, cache_read_tokens INTEGER,
                    est_cost_usd NUMERIC(10,6),
                    called_at TIMESTAMP DEFAULT NOW()
                )"""))
            conn.execute(text("""
                INSERT INTO llm_usage (module, model, input_tokens, output_tokens,
                                       cache_write_tokens, cache_read_tokens, est_cost_usd)
                VALUES (:mo, :md, :i, :o, :cw, :cr, :c)
            """), {"mo": module, "md": model, "i": inp, "o": out,
                   "cw": cw, "cr": cr, "c": round(cost, 6)})
    except Exception:
        pass   # never break the caller over bookkeeping


def usage_summary(engine, days: int = 7) -> list:
    """Per-module rollup for the brief / checkpoint."""
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT module,
                   COUNT(*) AS calls,
                   SUM(input_tokens) AS inp, SUM(output_tokens) AS outp,
                   SUM(cache_read_tokens) AS cache_reads,
                   ROUND(SUM(est_cost_usd), 2) AS cost_usd
            FROM llm_usage
            WHERE called_at > NOW() - (:d || ' days')::interval
            GROUP BY module ORDER BY cost_usd DESC
        """), {"d": days}).fetchall()
