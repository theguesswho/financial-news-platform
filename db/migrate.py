"""
Schema migrations — the ONE place table DDL is allowed to run.

Born from the 2026-09-09 / 2026-09-14 outages (V3 #25/#26): run steps
used to carry their own "ADD COLUMN IF NOT EXISTS" and "CREATE INDEX IF
NOT EXISTS" statements and executed them on every run. Postgres takes an
ACCESS EXCLUSIVE lock for the former and a SHARE lock for the latter
even when nothing changes; queued behind one idle transaction, that
lock blocked every reader of `fundamentals` and took the site down for
14 hours, then 3.5 days. Rules now:

  * Run steps ASSUME the schema. They never issue DDL.
  * Every schema statement lives in MIGRATIONS below and runs ONCE, at
    scheduler start-up (`scheduler_light.py`, before jobs are scheduled)
    or by hand (`python scheduler_light.py --migrate`).
  * Each entry is checked against the catalog first, so a migrated
    database gets NO DDL at all; when DDL is needed it runs under a
    short lock_timeout and a failure is logged, never hung on.
  * scripts/deploy_gate.py refuses a push that puts DDL back under
    pipeline/, api/ or scheduler_light.py.

Entry kinds:
  col(table, column, type_sql)         -> ADD COLUMN IF NOT EXISTS
  idx(name, table, cols_sql, unique)   -> CREATE [UNIQUE] INDEX IF NOT EXISTS
  raw(label, sql, needed_sql)          -> run sql when needed_sql returns a row
"""
import logging
from dataclasses import dataclass

from sqlalchemy import text

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = "30s"


@dataclass(frozen=True)
class Step:
    label: str
    sql: str
    needed_sql: str | None          # SELECT that returns a row when the step is still needed
    params: dict | None = None


def col(table: str, column: str, type_sql: str) -> Step:
    return Step(
        label=f"{table}.{column}",
        sql=f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type_sql}",
        needed_sql=("SELECT 1 FROM information_schema.tables t "
                    "WHERE t.table_name = :t AND NOT EXISTS ("
                    "SELECT 1 FROM information_schema.columns c "
                    "WHERE c.table_name = :t AND c.column_name = :c)"),
        params={"t": table, "c": column},
    )


def idx(name: str, table: str, cols_sql: str, unique: bool = False) -> Step:
    kind = "UNIQUE INDEX" if unique else "INDEX"
    return Step(
        label=f"index {name}",
        sql=f"CREATE {kind} IF NOT EXISTS {name} ON {table} ({cols_sql})",
        needed_sql=("SELECT 1 FROM information_schema.tables t "
                    "WHERE t.table_name = :t AND NOT EXISTS ("
                    "SELECT 1 FROM pg_indexes i WHERE i.indexname = :n)"),
        params={"t": table, "n": name},
    )


def raw(label: str, sql: str, needed_sql: str | None, params: dict | None = None) -> Step:
    return Step(label=label, sql=sql, needed_sql=needed_sql, params=params)


# ── The inventory (V3 #26, 2026-09-20). Order: by table, then history. ──────
MIGRATIONS: list[Step] = [
    # scheduler_runs — run ledger (R1: status/error for the subprocess runner)
    col("scheduler_runs", "status", "VARCHAR(12)"),
    col("scheduler_runs", "error", "TEXT"),

    # fundamentals — PEG normalizer (2026-07-22) + FMP growth provenance (V3 #20)
    col("fundamentals", "peg_vendor", "NUMERIC(12,2)"),
    col("fundamentals", "peg_analysts", "INTEGER"),
    col("fundamentals", "peg_updated", "TIMESTAMP"),
    col("fundamentals", "peg_source", "VARCHAR(10)"),
    col("fundamentals", "growth_source", "VARCHAR(10)"),
    col("fundamentals", "growth_quarter_end", "DATE"),
    col("fundamentals", "growth_filing_date", "DATE"),
    col("fundamentals", "growth_fetched_at", "TIMESTAMP"),

    # historical_metrics — refresh heartbeat + the UNIQUE the Railway migration lost (V3 #21)
    idx("ix_hm_symbol", "historical_metrics", "symbol"),
    col("historical_metrics", "fetched_at", "TIMESTAMP DEFAULT NOW()"),
    raw("historical_metrics UNIQUE (symbol, date)",
        "ALTER TABLE historical_metrics ADD CONSTRAINT _hm_symbol_date_uc UNIQUE (symbol, date)",
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'historical_metrics' "
        "AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '_hm_symbol_date_uc')"),

    # fundamentals_history
    idx("idx_fh_symbol_date", "fundamentals_history", "symbol, period_end DESC"),

    # leaderboard_history — v2 components, qual layer, final rank
    idx("idx_lh_date", "leaderboard_history", "date DESC"),
    col("leaderboard_history", "assessed_tier", "VARCHAR(20)"),
    col("leaderboard_history", "narrative_score", "NUMERIC(10,4)"),
    col("leaderboard_history", "value_score", "NUMERIC(10,4)"),
    col("leaderboard_history", "quality_score", "NUMERIC(10,4)"),
    col("leaderboard_history", "gap_score", "NUMERIC(10,4)"),
    col("leaderboard_history", "priced_in", "NUMERIC(10,4)"),
    col("leaderboard_history", "ng_score", "NUMERIC(10,4)"),
    col("leaderboard_history", "qual_promoted", "BOOLEAN DEFAULT FALSE"),
    col("leaderboard_history", "gem_adjusted", "NUMERIC(10,4)"),
    col("leaderboard_history", "final_rank", "INTEGER"),

    # track_lots — v2d era, benchmarks, per-era uniqueness
    col("track_lots", "signal_date", "DATE"),
    col("track_lots", "benchmark", "VARCHAR(10) DEFAULT 'SPY'"),
    col("track_lots", "qual_promoted", "BOOLEAN DEFAULT FALSE"),
    col("track_lots", "era", "VARCHAR(4) DEFAULT 'v1'"),
    raw("track_lots drop (lot_date, symbol) uniqueness",
        "ALTER TABLE track_lots DROP CONSTRAINT IF EXISTS track_lots_lot_date_symbol_key",
        "SELECT 1 FROM pg_constraint WHERE conname = 'track_lots_lot_date_symbol_key'"),
    idx("track_lots_date_sym_era", "track_lots", "lot_date, symbol, era", unique=True),
    raw("track_lots era backfill (pre-v2 rows = 'v1')",
        "UPDATE track_lots SET era = 'v1' WHERE era IS NULL OR lot_date < :d",
        "SELECT 1 FROM track_lots WHERE era IS NULL OR (lot_date < :d AND era <> 'v1') LIMIT 1",
        {"d": "2026-07-23"}),   # V2_START (pipeline/track_record.py)

    # qual_assessments
    col("qual_assessments", "narrative_score", "NUMERIC(10,4)"),
    col("qual_assessments", "continuity", "VARCHAR(12)"),

    # deep_dives
    col("deep_dives", "last_filing_date", "DATE"),

    # narratives / exposures / checkpoints / structure
    col("narratives", "scope", "VARCHAR(12)"),
    col("narrative_exposures", "direction", "VARCHAR(12)"),
    col("narrative_exposures", "linkage", "VARCHAR(12)"),
    col("narrative_exposures", "signed_at", "TIMESTAMP"),
    col("narrative_exposures", "decays", "INTEGER NOT NULL DEFAULT 0"),
    col("narrative_checkpoints", "source_claim_id", "INT NULL"),
    idx("ix_nev_narrative_date", "narrative_evidence", "narrative_id, evidence_date"),
    idx("idx_nhh_week", "narrative_health_history", "week_start"),

    # filing_themes / stock_theme_alignment (narrative_db)
    idx("idx_filing_themes_symbol", "filing_themes", "symbol"),
    idx("idx_filing_themes_date", "filing_themes", "filing_date"),
    idx("idx_stock_theme_symbol", "stock_theme_alignment", "symbol"),
    idx("idx_stock_theme_score", "stock_theme_alignment", "alignment_score DESC"),

    # meta_themes — persistence columns + one-time first_seen fill
    col("meta_themes", "first_seen", "TIMESTAMP DEFAULT NOW()"),
    col("meta_themes", "status", "VARCHAR(20) DEFAULT 'active'"),
    raw("meta_themes first_seen backfill",
        "UPDATE meta_themes SET first_seen = updated_at WHERE first_seen IS NULL",
        "SELECT 1 FROM meta_themes WHERE first_seen IS NULL LIMIT 1"),
]


def run_migrations(engine, lock_timeout: str = LOCK_TIMEOUT) -> dict:
    """Apply every step that is still needed. Never raises: a failure is
    logged with its label and counted; the caller decides what to do.
    Returns {"checked", "applied", "skipped", "failed": [labels]}."""
    summary = {"checked": 0, "applied": 0, "skipped": 0, "failed": []}
    for step in MIGRATIONS:
        summary["checked"] += 1
        try:
            if step.needed_sql is not None:
                with engine.connect() as conn:
                    needed = conn.execute(text(step.needed_sql), step.params or {}).fetchone()
                if not needed:
                    summary["skipped"] += 1
                    continue
            with engine.begin() as conn:
                conn.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
                conn.execute(text(step.sql), step.params or {})
            summary["applied"] += 1
            logger.info("migrate: applied %s", step.label)
        except Exception as exc:
            # Missing table (fresh DB — the step's CREATE TABLE IF NOT EXISTS
            # builds it with the full shape) or a lock we refused to wait
            # for. Either way: say so, move on, never hang the start-up.
            summary["failed"].append(step.label)
            logger.warning("migrate: %s failed — %s", step.label, str(exc)[:200])
    logger.info("migrate: %d checked, %d applied, %d already in place, %d failed",
                summary["checked"], summary["applied"], summary["skipped"],
                len(summary["failed"]))
    return summary
