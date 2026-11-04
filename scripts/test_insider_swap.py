"""insider_trades dedup swap harness (designed 2026-11-03, branch insider-dedup-swap).

Runs the REAL db/migrate.py swap and the REAL pipeline/insider.py writer
against a THROWAWAY Postgres cluster (initdb in a temp dir, port 55434,
deleted afterwards), on a table built the way prod's is: no primary key, no
index, ids reused (the July migration reset the sequence), blank key fields,
and equal-size same-day lots that the old five-column key would merge.
Stubbed: .env (prod is never reachable; every engine is asserted to point at
localhost:55434) and EDGAR (the writer test feeds fixed Form 4 trades).

  venv/bin/python scripts/test_insider_swap.py            # correctness + prod-scale timing
  SCALE=0 venv/bin/python scripts/test_insider_swap.py    # correctness only

Exit code 0 only if every check passes.
"""
import os, shutil, subprocess, sys, tempfile, threading, time
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORT = 55434
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
os.environ["DATABASE_URL"] = f"postgresql://postgres@localhost:{PORT}/swaptest"
sys.path.insert(0, str(REPO))

from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail}")


G = tempfile.mkdtemp(prefix="isw", dir="/tmp")
BIN = os.getenv("PG_BIN", "/Applications/Postgres.app/Contents/Versions/latest/bin")
DATA = f"{G}/pgdata"
KEY = "symbol, person_name, transaction_date, transaction_type, shares, price_per_share, shares_owned_after, form4_url"


def eng(db, autocommit=True):
    e = create_engine(f"postgresql+psycopg2://postgres@localhost:{PORT}/{db}",
                      **({"isolation_level": "AUTOCOMMIT"} if autocommit else {}))
    assert (e.url.host, e.url.port) == ("localhost", PORT), "REFUSING: not the throwaway cluster"
    return e


def q(db, sql, **kw):
    e = eng(db)
    with e.connect() as c:
        r = c.execute(text(sql), kw).fetchall()
    e.dispose()
    return r


def x(db, sql, **kw):
    e = eng(db)
    with e.connect() as c:
        c.execute(text(sql), kw)
    e.dispose()


PROD_DDL = """
CREATE SEQUENCE insider_trades_id_seq;
CREATE TABLE insider_trades (
    id INTEGER NOT NULL DEFAULT nextval('insider_trades_id_seq'),
    symbol VARCHAR(10) NOT NULL, person_name VARCHAR(200), person_title VARCHAR(200),
    transaction_date DATE NOT NULL, transaction_type VARCHAR(10), shares NUMERIC(16,2),
    price_per_share NUMERIC(12,4), total_value NUMERIC(20,2), shares_owned_after NUMERIC(16,2),
    form4_url VARCHAR(1000), created_at TIMESTAMP);
ALTER SEQUENCE insider_trades_id_seq OWNED BY insider_trades.id;
"""

# Distinct trades: 900 ordinary, 100 pairs of equal-size same-day lots (differ by
# price and shares-owned-after: the old key merges each pair), 30 with a blank
# in the key. Each trade is copied 1..60 times, ids partly reused.
SEED = """
WITH t AS (
  SELECT g AS n,
         'S' || lpad((g % 40)::text, 2, '0') AS symbol,
         CASE WHEN g % 34 = 0 THEN NULL ELSE 'Person ' || (g % 97) END AS person_name,
         'Director' AS person_title,
         DATE '2026-11-03' - (g % 90) AS transaction_date,
         CASE WHEN g % 3 = 0 THEN 'SELL' ELSE 'BUY' END AS transaction_type,
         (100 * (1 + g % 50))::numeric AS shares,
         CASE WHEN g % 41 = 0 THEN NULL ELSE round((10 + g % 70 + 0.25)::numeric, 4) END AS price,
         (100000 - g)::numeric AS owned_after,
         'https://www.sec.gov/f4/' || (g / 3) AS url
  FROM generate_series(1, 900) g
  UNION ALL   -- the equal-size same-day pairs: identical in the old five columns
  SELECT 1000 + 2 * p + k, 'P' || lpad((p % 20)::text, 2, '0'), 'Pair ' || p, 'CFO',
         DATE '2026-11-03' - (p % 30), 'SELL', 500::numeric,
         round((50 + k * 0.5 + p)::numeric, 4), (20000 - 500 * k)::numeric,
         'https://www.sec.gov/pair/' || p
  FROM generate_series(1, 100) p, generate_series(0, 1) k
)
INSERT INTO insider_trades (id, symbol, person_name, person_title, transaction_date, transaction_type,
                            shares, price_per_share, total_value, shares_owned_after, form4_url, created_at)
SELECT CASE WHEN (t.n + c) % 7 = 0 THEN (t.n * 13 + c) % 5000 + 1        -- reused ids (sequence reset)
            ELSE 100000 + t.n * 100 + c END,
       t.symbol, t.person_name, t.person_title, t.transaction_date, t.transaction_type,
       t.shares, t.price, round(t.shares * coalesce(t.price, 0), 2), t.owned_after, t.url,
       TIMESTAMP '2026-06-01' + (t.n % 90) * INTERVAL '1 day' + c * INTERVAL '1 day'
FROM t, generate_series(0, 59) c
WHERE c < 1 + (t.n * 7) % 60;
SELECT setval('insider_trades_id_seq', 2249905);
"""


def brief_sums(db, table):
    """What the brief's cluster query adds up (BUY, last 14 days of the seed), by symbol."""
    return dict(q(db, f"""SELECT symbol, SUM(total_value) FROM {table}
                          WHERE transaction_type = 'BUY' AND transaction_date >= DATE '2026-11-03' - 14
                          GROUP BY symbol"""))


subprocess.run([f"{BIN}/initdb", "-D", DATA, "-U", "postgres", "-A", "trust", "--no-sync"],
               check=True, capture_output=True)
subprocess.run([f"{BIN}/pg_ctl", "-D", DATA, "-l", f"{G}/pg.log", "-w", "start", "-o",
                f"-p {PORT} -c listen_addresses=localhost -c unix_socket_directories=''"],
               check=True, capture_output=True)
try:
    import db.migrate as mig
    for db in ("swaptest", "lockdb", "scaledb"):
        eng("postgres").connect().execute(text(f"CREATE DATABASE {db}"))
        x(db, PROD_DDL)

    print("\n1. Seed a prod-shaped table")
    x("swaptest", SEED)
    rows = q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0]
    trades = q("swaptest", f"SELECT COUNT(DISTINCT ({KEY})) FROM insider_trades")[0][0]
    model5 = q("swaptest", "SELECT COUNT(DISTINCT (symbol, person_name, transaction_date, transaction_type, shares)) FROM insider_trades")[0][0]
    dup_ids = q("swaptest", "SELECT COUNT(*) - COUNT(DISTINCT id) FROM insider_trades")[0][0]
    raw_sums = brief_sums("swaptest", "insider_trades")
    check("seed: many copies, reused ids, and the old key merges real lots",
          rows > trades * 10 and dup_ids > 0 and model5 < trades,
          f"{rows:,} rows, {trades:,} trades, old key {model5:,}, {dup_ids:,} reused ids")

    print("\n2. Swap, with one new trade and one duplicate written while the copy is built")
    e = eng("swaptest", autocommit=False)
    other = eng("swaptest")

    @event.listens_for(e, "after_cursor_execute")
    def _late_writer(conn, cursor, statement, *a):
        if statement.startswith("ANALYZE insider_trades_dedup_new"):
            with other.connect() as c:
                c.execute(text("""INSERT INTO insider_trades (symbol, person_name, transaction_date, transaction_type,
                                  shares, price_per_share, total_value, shares_owned_after, form4_url, created_at)
                                  VALUES ('LATE', 'New Person', '2026-11-03', 'BUY', 10, 5, 50, 10, 'u-late', NOW() + INTERVAL '1 hour')"""))
                c.execute(text(f"""INSERT INTO insider_trades (symbol, person_name, person_title, transaction_date, transaction_type,
                                  shares, price_per_share, total_value, shares_owned_after, form4_url, created_at)
                                  SELECT symbol, person_name, person_title, transaction_date, transaction_type, shares,
                                         price_per_share, total_value, shares_owned_after, form4_url, NOW() + INTERVAL '1 hour'
                                  FROM insider_trades ORDER BY id DESC LIMIT 1"""))
    summary = mig.run_migrations(e)
    check("migration step ran and did not fail",
          "insider_trades dedup swap + unique trade key" not in summary["failed"], str(summary["failed"]))
    after = q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0]
    keep_tbl = q("swaptest", "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'insider_trades_pre_dedup_%'")
    keep_rows = q("swaptest", f"SELECT COUNT(*) FROM {keep_tbl[0][0]}")[0][0] if keep_tbl else None
    check("one row per real trade, plus the one genuinely new late trade", after == trades + 1, f"{after:,} vs {trades:,} + 1")
    lost = q("swaptest", f"SELECT COUNT(*) FROM (SELECT {KEY} FROM {keep_tbl[0][0]} EXCEPT SELECT {KEY} FROM insider_trades) d")[0][0]
    check("no real trade lost (old table EXCEPT new table = 0, blanks compared as equal)", lost == 0, f"{lost}")
    check("old table kept for rollback, every row intact (incl. the late duplicate)",
          bool(keep_tbl) and keep_rows == rows + 2, f"{keep_tbl[0][0] if keep_tbl else None}: {keep_rows:,}")
    idx = dict(q("swaptest", "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'insider_trades'"))
    check("primary key + unique trade key (NULLS NOT DISTINCT) + symbol/date index on the live table",
          "insider_trades_pkey" in idx and "NULLS NOT DISTINCT" in idx.get("uq_insider_trades_trade", "")
          and "ix_insider_trades_symbol_date" in idx, str(sorted(idx)))
    owner = q("swaptest", "SELECT pg_get_serial_sequence('insider_trades', 'id')")[0][0]
    nxt = q("swaptest", "SELECT nextval('insider_trades_id_seq')")[0][0]
    mx = q("swaptest", "SELECT MAX(id) FROM insider_trades")[0][0]
    check("sequence now owned by the new table and above every id", owner == "public.insider_trades_id_seq" and nxt > mx,
          f"owner {owner}, next {nxt}, max id {mx}")
    new_sums = brief_sums("swaptest", "insider_trades")
    true_sums = dict(q("swaptest", f"""SELECT symbol, SUM(total_value) FROM (SELECT DISTINCT {KEY}, total_value FROM {keep_tbl[0][0]}
                                       WHERE created_at < '2026-11-04') d
                                       WHERE transaction_type = 'BUY' AND transaction_date >= DATE '2026-11-03' - 14 GROUP BY symbol"""))
    true_sums.pop("LATE", None); new_sums.pop("LATE", None)
    infl = sum(float(v) for v in raw_sums.values()) / max(1.0, sum(float(v) for v in true_sums.values()))
    check("brief-style 14-day buy sums now equal the true per-trade sums",
          {k: float(v) for k, v in new_sums.items()} == {k: float(v) for k, v in true_sums.items()},
          f"before the swap the same query was {infl:.1f}x too high")
    s2 = mig.run_migrations(e)
    n_keep = q("swaptest", "SELECT COUNT(*) FROM information_schema.tables WHERE table_name LIKE 'insider_trades_pre_dedup_%'")[0][0]
    check("second start-up: step not needed, nothing re-run", "insider_trades dedup swap + unique trade key" not in s2["failed"] and n_keep == 1 and
          q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0] == after, f"rollback copies {n_keep}")

    print("\n3. Writer: stored trades are skipped, new ones added, counts honest")
    import pipeline.insider as ins
    existing = [dict(r._mapping) for r in eng("swaptest").connect().execute(text(
        "SELECT symbol, person_name, person_title, transaction_date, transaction_type, shares, price_per_share, "
        "total_value, shares_owned_after, form4_url FROM insider_trades WHERE person_name IS NOT NULL ORDER BY id LIMIT 5"))]
    newone = dict(existing[0], form4_url="https://www.sec.gov/f4/brand-new", shares_owned_after=1)
    feed = {"trades": existing + [newone]}
    ins._build_cik_map = lambda tickers: {"S01": "0000000001"}
    ins._get_form4_urls = lambda cik, lookback_days=90: [{"url": "stub"}]
    ins._parse_form4 = lambda url, symbol: [dict(t) for t in feed["trades"]]
    import types
    ins.time = types.SimpleNamespace(sleep=lambda s: None)   # only the writer's pause, not the process
    n0 = q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0]
    with Session(eng("swaptest", autocommit=False)) as s:
        r1 = ins.run_insiders(s, ["S01"])
    with Session(eng("swaptest", autocommit=False)) as s:
        r2 = ins.run_insiders(s, ["S01"])
    n1 = q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0]
    check("first run adds only the new trade; re-run adds nothing",
          r1["added"] == 1 and r2["added"] == 0 and n1 == n0 + 1, f"{r1}, {r2}, rows {n0:,} -> {n1:,}")

    print("\n4. Rollback, as documented")
    x("swaptest", f"""BEGIN; SET LOCAL lock_timeout = '3s';
        ALTER TABLE insider_trades RENAME TO insider_trades_dedup_rolledback;
        ALTER TABLE {keep_tbl[0][0]} RENAME TO insider_trades;
        ALTER SEQUENCE insider_trades_id_seq OWNED BY insider_trades.id;
        COMMIT;""")
    back = q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0]
    s3 = mig.run_migrations(e)
    still = q("swaptest", "SELECT COUNT(*) FROM insider_trades")[0][0]
    check("rollback restores the original table; the swap does not re-run at the next start-up",
          back == rows + 2 and still == back and "insider_trades dedup swap + unique trade key" not in s3["failed"], f"{back:,} rows; next start-up left {still:,}")

    print("\n5. Lock timeout: a long reader holds the table")
    x("lockdb", SEED)
    lrows = q("lockdb", "SELECT COUNT(*) FROM insider_trades")[0][0]
    holder = eng("lockdb", autocommit=False).connect()
    htx = holder.begin()
    holder.execute(text("SELECT COUNT(*) FROM insider_trades")).scalar()     # ACCESS SHARE held until commit
    mig.SWAP_TRIES, mig.SWAP_RETRY_S = 2, 1
    reader_wait = {}

    def _late_reader():
        time.sleep(1.0)                                   # arrives while the swap is queued for its lock
        t = time.time()
        q("lockdb", "SELECT COUNT(*) FROM insider_trades")
        reader_wait["s"] = time.time() - t
    th = threading.Thread(target=_late_reader); th.start()
    t0 = time.time()
    try:
        mig._insider_dedup_swap(eng("lockdb", autocommit=False))
        failed_cleanly = False
    except RuntimeError as ex:
        failed_cleanly = "live table untouched" in str(ex)
    el = time.time() - t0
    th.join()
    htx.commit(); holder.close()
    left = q("lockdb", "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'insider_trades%' ORDER BY 1")
    check("swap gives up after 2 tries x 3 s, raises, drops its copy, live table untouched",
          failed_cleanly and [r[0] for r in left] == ["insider_trades"] and
          q("lockdb", "SELECT COUNT(*) FROM insider_trades")[0][0] == lrows, f"{el:.1f}s, tables {[r[0] for r in left]}")
    check("a reader arriving while the swap waits is delayed at most ~3 s (lock_timeout), never hung",
          reader_wait.get("s", 99) < 4.0, f"{reader_wait.get('s', 0):.1f}s")
    mig.SWAP_TRIES, mig.SWAP_RETRY_S = 5, 10
    out = mig._insider_dedup_swap(eng("lockdb", autocommit=False))
    check("with the reader gone, the same swap succeeds on the first try", out["attempt"] == 1, str(out))

    print("\n6. Deploy-gate DDL lint (DDL only in db/migrate.py)")
    import re
    DDL_RE = re.compile(r"\b(ALTER TABLE|ADD COLUMN|CREATE (?:UNIQUE )?INDEX)\b")
    hits = [f"{f}:{n}" for f in ("pipeline/insider.py", "pipeline/brief.py")
            for n, line in enumerate(open(REPO / f), 1) if not line.strip().startswith("#") and DDL_RE.search(line)]
    check("no table DDL in run paths", not hits, str(hits))

    if os.getenv("SCALE", "1") != "0":
        print("\n7. Prod scale: 22,500 trades x ~95 copies (~2.1M rows)")
        x("scaledb", """
          INSERT INTO insider_trades (id, symbol, person_name, person_title, transaction_date, transaction_type, shares,
                                      price_per_share, total_value, shares_owned_after, form4_url, created_at)
          SELECT (g * 97 + c) % 2000000 + 1, 'S' || (g % 830), 'Person ' || (g % 5000), 'Officer',
                 DATE '2026-11-03' - (g % 150), CASE WHEN g % 3 = 0 THEN 'BUY' ELSE 'SELL' END,
                 100 + g % 900, 10 + (g % 400) * 0.25, (100 + g % 900) * (10 + (g % 400) * 0.25), 1e6 - g,
                 'https://www.sec.gov/Archives/edgar/data/' || (g % 830) || '/' || g || '.xml',
                 TIMESTAMP '2026-06-01' + (g % 150) * INTERVAL '1 day' + c * INTERVAL '1 day'
          FROM generate_series(1, 22500) g, generate_series(0, 94) c""")
        srows = q("scaledb", "SELECT COUNT(*) FROM insider_trades")[0][0]
        size = q("scaledb", "SELECT pg_size_pretty(pg_total_relation_size('insider_trades'))")[0][0]
        out = mig._insider_dedup_swap(eng("scaledb", autocommit=False))
        kept = q("scaledb", "SELECT COUNT(*) FROM insider_trades")[0][0]
        check("prod scale: swap completes; readers locked out only for the swap itself",
              kept == 22500 and out["lock_s"] < 3.0,
              f"{srows:,} rows ({size}) -> {kept:,}; build {out['build_s']}s (no lock), exclusive lock {out['lock_s']}s")
finally:
    subprocess.run([f"{BIN}/pg_ctl", "-D", DATA, "-m", "immediate", "stop"], capture_output=True)
    shutil.rmtree(G, ignore_errors=True)
    print(f"\n{sum(ok for _, ok in results)} of {len(results)} checks passed; throwaway cluster stopped and removed")

sys.exit(0 if results and all(ok for _, ok in results) else 1)
