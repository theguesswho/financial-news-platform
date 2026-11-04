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
  proc(label, fn, needed_sql)          -> call fn(engine) when needed_sql returns a row
                                          (multi-step work that one statement cannot do
                                          safely, e.g. a table swap with lock retries)
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = "30s"


@dataclass(frozen=True)
class Step:
    label: str
    sql: str
    needed_sql: str | None          # SELECT that returns a row when the step is still needed
    params: dict | None = None
    fn: Callable | None = None      # proc(): called with the engine instead of running `sql`


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


def proc(label: str, fn: Callable, needed_sql: str | None, params: dict | None = None) -> Step:
    return Step(label=label, sql="", needed_sql=needed_sql, params=params, fn=fn)


# ── insider_trades: deduplicating SWAP (designed 2026-11-03, NOT YET APPROVED) ──
# The Railway migration (July 2026) dropped this table's unique key, primary
# key and sequence history. insider.py relies on a duplicate-key error to skip
# trades it already has; with no key that error never fires, so every daily
# run re-inserted the full 90-day Form 4 window: 2,136,629 rows for 22,522
# real trades on 3 Nov 2026 (ids are not unique either: 21,003 distinct ids
# among the trades' first copies). Readers that SUM the rows (daily brief,
# product stock page, Streamlit) showed inflated figures. No score, band,
# assessor or ledger input reads this table.
#
# Safe swap, never an in-place DELETE of 2.1M rows under a lock:
#   1. build insider_trades_dedup_new: one row per real trade (earliest copy),
#      ids renumbered in first-seen order (the sequence is far above them);
#   2. primary key, unique trade key (NULLS NOT DISTINCT: 274 rows have a
#      blank in the key) and a (symbol, transaction_date) index on the COPY —
#      the live table is only read, readers and the writer are never blocked;
#   3. swap under ACCESS EXCLUSIVE with a 3 s lock_timeout (a queued lock
#      blocks every reader behind it — the 09-14 lesson), 5 tries 10 s apart:
#      copy any row written since step 1, rename live -> insider_trades_pre_dedup_<date>
#      (kept for rollback), rename the copy -> insider_trades, move the
#      sequence's ownership to the new table;
#   4. if the lock never comes: drop the copy, live table untouched, FAIL
#      the step by label (logged at start-up), retry at the next start-up.
# Rollback (manual, documented in INSIDER_DEDUP_PLAN.md): rename back; the
# deduplicated table is kept as insider_trades_dedup_rolledback, whose
# presence stops this step from re-running.
INSIDER_KEY = ("symbol", "person_name", "transaction_date", "transaction_type", "shares",
               "price_per_share", "shares_owned_after", "form4_url")
INSIDER_COLS = ("id", "symbol", "person_name", "person_title", "transaction_date", "transaction_type",
                "shares", "price_per_share", "total_value", "shares_owned_after", "form4_url", "created_at")
INSIDER_UQ = "uq_insider_trades_trade"
SWAP_LOCK_TIMEOUT = "3s"
SWAP_TRIES = 5
SWAP_RETRY_S = 10


def _insider_dedup_swap(engine) -> dict:
    key = ", ".join(INSIDER_KEY)
    cols = ", ".join(INSIDER_COLS)
    data_cols = ", ".join(INSIDER_COLS[1:])
    keep = f"insider_trades_pre_dedup_{datetime.utcnow():%Y%m%d}"
    t0 = time.time()
    with engine.begin() as c:                       # leftovers of an interrupted attempt are ours
        c.execute(text(f"SET LOCAL lock_timeout = '{SWAP_LOCK_TIMEOUT}'"))
        c.execute(text("DROP TABLE IF EXISTS insider_trades_dedup_new"))
    # 1. the deduplicated copy, from one consistent snapshot of the live table
    with engine.begin() as c:
        c.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        c.execute(text(f"SET LOCAL lock_timeout = '{SWAP_LOCK_TIMEOUT}'"))
        snap = c.execute(text("SELECT COUNT(*), COALESCE(MAX(created_at), NOW()) FROM insider_trades")).fetchone()
        c.execute(text("CREATE TABLE insider_trades_dedup_new (LIKE insider_trades INCLUDING DEFAULTS)"))
        c.execute(text(f"""
            INSERT INTO insider_trades_dedup_new ({cols})
            SELECT ROW_NUMBER() OVER (ORDER BY created_at, id), {data_cols}
            FROM (SELECT DISTINCT ON ({key}) * FROM insider_trades
                  ORDER BY {key}, created_at, id) first_copies"""))
    # 2. keys on the copy — nothing here touches the live table
    with engine.begin() as c:
        c.execute(text("ALTER TABLE insider_trades_dedup_new ADD CONSTRAINT insider_trades_pkey PRIMARY KEY (id)"))
        c.execute(text(f"CREATE UNIQUE INDEX {INSIDER_UQ} ON insider_trades_dedup_new ({key}) NULLS NOT DISTINCT"))
        c.execute(text("CREATE INDEX ix_insider_trades_symbol_date ON insider_trades_dedup_new (symbol, transaction_date)"))
        c.execute(text("ANALYZE insider_trades_dedup_new"))
        kept = c.execute(text("SELECT COUNT(*) FROM insider_trades_dedup_new")).scalar()
    built_s = time.time() - t0
    # 3. the swap: short exclusive lock, bounded wait, retried
    last_err = None
    for attempt in range(1, SWAP_TRIES + 1):
        try:
            t1 = time.time()
            with engine.begin() as c:
                c.execute(text(f"SET LOCAL lock_timeout = '{SWAP_LOCK_TIMEOUT}'"))
                c.execute(text("LOCK TABLE insider_trades IN ACCESS EXCLUSIVE MODE"))
                late = c.execute(text(f"""
                    INSERT INTO insider_trades_dedup_new ({data_cols})
                    SELECT {data_cols} FROM insider_trades WHERE created_at > :t
                    ON CONFLICT DO NOTHING RETURNING 1"""), {"t": snap[1]}).fetchall()
                c.execute(text(f"ALTER TABLE insider_trades RENAME TO {keep}"))
                c.execute(text("ALTER TABLE insider_trades_dedup_new RENAME TO insider_trades"))
                c.execute(text("ALTER SEQUENCE IF EXISTS insider_trades_id_seq OWNED BY insider_trades.id"))
            out = {"rows_before": int(snap[0]), "trades_kept": int(kept), "late_rows_added": len(late),
                   "kept_for_rollback": keep, "build_s": round(built_s, 1),
                   "lock_s": round(time.time() - t1, 2), "attempt": attempt}
            logger.info("migrate: insider_trades swapped: %s", out)
            return out
        except Exception as exc:
            last_err = exc
            if "lock timeout" not in str(exc).lower() and "55P03" not in str(exc):
                break
            logger.warning("migrate: insider swap attempt %d/%d could not get the lock in %s",
                           attempt, SWAP_TRIES, SWAP_LOCK_TIMEOUT)
            time.sleep(SWAP_RETRY_S)
    with engine.begin() as c:                       # never leave a half-built copy behind
        c.execute(text(f"SET LOCAL lock_timeout = '{SWAP_LOCK_TIMEOUT}'"))
        c.execute(text("DROP TABLE IF EXISTS insider_trades_dedup_new"))
    raise RuntimeError(f"insider swap not done, live table untouched: {str(last_err)[:160]}")


# ── The inventory (V3 #26, 2026-09-20). Order: by table, then history. ──────
MIGRATIONS: list[Step] = [
    # scheduler_runs — run ledger (R1: status/error for the subprocess runner)
    col("scheduler_runs", "status", "VARCHAR(12)"),
    col("scheduler_runs", "error", "TEXT"),
    # Single-scheduler guard (2026-11-01): a second Railway project ran every
    # job a second time on this database from 25 Jun to 1 Nov. Each run is now
    # claimed by ONE instance (owner) and kept alive by a heartbeat; another
    # instance that finds a live claim stands down and raises an alarm.
    col("scheduler_runs", "owner", "VARCHAR(120)"),
    col("scheduler_runs", "heartbeat_at", "TIMESTAMP"),

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

    # T6 (2026-10-31): per-step run ledger, backfilled mark, budget tag
    raw("scheduler_steps table",
        """CREATE TABLE IF NOT EXISTS scheduler_steps (
               id SERIAL PRIMARY KEY, job_id VARCHAR(20) NOT NULL, slot_ts TIMESTAMP NOT NULL,
               step VARCHAR(16) NOT NULL, label VARCHAR(200), started_at TIMESTAMP, finished_at TIMESTAMP,
               status VARCHAR(12), note VARCHAR(500), error VARCHAR(500))""",
        "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scheduler_steps')"),
    idx("idx_sched_steps_run", "scheduler_steps", "job_id, slot_ts"),
    col("filings", "backfilled", "BOOLEAN DEFAULT FALSE"),
    col("llm_usage", "budget", "VARCHAR(10)"),

    # insider_trades dedup swap + unique trade key (designed 2026-11-03; see
    # _insider_dedup_swap). Needed while the live table has no trade key and
    # no deliberate rollback is on record.
    proc("insider_trades dedup swap + unique trade key", _insider_dedup_swap,
         "SELECT 1 FROM information_schema.tables WHERE table_name = 'insider_trades' "
         "AND NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'insider_trades' "
         "                AND indexname = 'uq_insider_trades_trade') "
         "AND NOT EXISTS (SELECT 1 FROM information_schema.tables "
         "                WHERE table_name = 'insider_trades_dedup_rolledback')"),
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
            if step.fn is not None:
                step.fn(engine)                     # manages its own transactions and lock timeouts
            else:
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
