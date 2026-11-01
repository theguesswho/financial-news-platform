"""Single-scheduler guard harness (2026-11-01).

From 25 Jun to 1 Nov a second Railway project ran this scheduler against the
same database. This harness proves the guard in scheduler_light
(_claim_run / _heartbeat / owner-checked finish) with REAL worker processes
running the REAL _run_job_recorded against a THROWAWAY Postgres cluster
(initdb in a temp dir, port 55432, deleted afterwards). Stubbed: .env
loading (prod can never be reached; each worker asserts its engine points
at localhost:55432), the LLM pre-flight call, and the child job (a sleeper).

  venv/bin/python scripts/test_scheduler_guard.py
  PG_BIN=/path/to/postgres/bin venv/bin/python scripts/test_scheduler_guard.py

Scenarios: two instances fire one slot at once; owner killed mid-run and
rescued after its heartbeat goes stale; deliberate re-run of a finished
slot; un-migrated database fails open; stalled owner cannot overwrite a run
another instance took over. Exit code 0 only if every check passes.
"""
import os, sys, time, json, shutil, signal, subprocess, tempfile, argparse, types
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

if "--worker" in sys.argv:
    sys.argv.remove("--worker")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db"); ap.add_argument("--tag"); ap.add_argument("--job", default="daily")
    ap.add_argument("--slot"); ap.add_argument("--child-s", type=float, default=3)
    ap.add_argument("--wait", type=int, default=0); ap.add_argument("--start-at", type=float, default=0)
    ap.add_argument("--stall-s", type=float, default=0)
    ap.add_argument("--marks")
    a = ap.parse_args()

    import dotenv
    dotenv.load_dotenv = lambda *x, **k: False          # never read the real .env (prod DATABASE_URL)
    os.environ["DATABASE_URL"] = f"postgresql://postgres@localhost:55432/{a.db}"
    os.environ.update(RAILWAY_PROJECT_NAME=a.tag, RAILWAY_SERVICE_NAME="scheduler",
                      RAILWAY_DEPLOYMENT_ID=f"{a.tag}-dep0")
    yf = types.ModuleType("yfinance"); yf.set_tz_cache_location = lambda *_: None; sys.modules["yfinance"] = yf
    import anthropic
    class _Msgs:
        def create(self, **k): return None
    class _Client:
        def __init__(self, **k): self.messages = _Msgs()
    anthropic.Anthropic = _Client
    sys.path.insert(0, str(REPO))
    import scheduler_light as sl
    from pipeline.hidden_gem_scorer import get_engine
    u = get_engine().url
    assert (u.host, u.port, u.database) == ("localhost", 55432, a.db), f"REFUSING: engine points at {u.host}:{u.port}"
    sl.HEARTBEAT_S, sl.STALE_HEARTBEAT_S, sl.CLAIM_RETRY_S = 1, 4, 1

    _RealPopen = subprocess.Popen
    def _fake_child(cmd, **kw):                          # the 'job': a sleeper, real process, real wait()
        with open(a.marks, "a") as f: f.write(f"spawn {a.tag} {a.slot}\n")
        return _RealPopen([sys.executable, "-c", f"import time; time.sleep({a.child_s})"])
    subprocess.Popen = _fake_child

    if a.stall_s:
        _real_hb, _t_claim = sl._heartbeat, time.time()
        def _stalled(*x, **k):
            return True if time.time() - _t_claim < a.stall_s else _real_hb(*x, **k)
        sl._heartbeat = _stalled

    from datetime import datetime
    slot = datetime.fromisoformat(a.slot)
    while a.start_at and time.time() < a.start_at: time.sleep(0.01)
    if a.stall_s: _t_claim = time.time()
    res = sl._run_job_recorded(a.job, slot, claim_wait_s=a.wait)
    with open(a.marks, "a") as f: f.write(f"result {a.tag} {a.slot} {res}\n")
    print("RESULT", a.tag, res, flush=True)
    sys.exit(0)

G = tempfile.mkdtemp(prefix="sg", dir="/tmp")
BIN = os.getenv("PG_BIN", "/Applications/Postgres.app/Contents/Versions/latest/bin")
PY = sys.executable
DATA, MARKS = f"{G}/pgdata", f"{G}/marks.txt"
sys.path.insert(0, str(REPO))
from sqlalchemy import create_engine, text
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond))); print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail}")
def eng(db): return create_engine(f"postgresql+psycopg2://postgres@localhost:55432/{db}", isolation_level="AUTOCOMMIT")
def q(db, sql, **kw):
    e = eng(db)
    with e.connect() as c: r = [dict(x._mapping) for x in c.execute(text(sql), kw)]
    e.dispose(); return r
def worker(db, tag, slot, **kw):
    args = [PY, str(Path(__file__).resolve()), "--worker", "--db", db, "--tag", tag, "--slot", slot, "--marks", MARKS]
    for k, v in kw.items(): args += [f"--{k.replace('_', '-')}", str(v)]
    return subprocess.Popen(args, stdout=open(f"{G}/{tag}.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
def marks(): return open(MARKS).read().splitlines() if os.path.exists(MARKS) else []
def log(tag): return open(f"{G}/{tag}.log").read()

shutil.rmtree(DATA, ignore_errors=True)
subprocess.run([f"{BIN}/initdb", "-D", DATA, "-U", "postgres", "-A", "trust", "--no-sync"], check=True, capture_output=True)
subprocess.run([f"{BIN}/pg_ctl", "-D", DATA, "-l", f"{G}/pg.log", "-w", "start", "-o",
                f"-p 55432 -c listen_addresses=localhost -c unix_socket_directories=''"], check=True, capture_output=True)
try:
    for db in ("guardtest", "guardlegacy"):
        eng("postgres").connect().execute(text(f"CREATE DATABASE {db}"))
        for s in ("lock_timeout = '30s'", "idle_in_transaction_session_timeout = '10min'"):
            eng("postgres").connect().execute(text(f"ALTER DATABASE {db} SET {s}"))
    legacy_runs = """CREATE TABLE scheduler_runs (id SERIAL PRIMARY KEY, job_id VARCHAR(20) NOT NULL,
                     slot_ts TIMESTAMP NOT NULL, started_at TIMESTAMP, finished_at TIMESTAMP, UNIQUE (job_id, slot_ts))"""
    e = eng("guardtest"); e.connect().execute(text(legacy_runs)); 
    from db.migrate import run_migrations
    m = run_migrations(e); e.dispose()
    cols = [r["column_name"] for r in q("guardtest", "select column_name from information_schema.columns where table_name='scheduler_runs' order by ordinal_position")]
    print("migrated scheduler_runs:", cols, "| applied", m["applied"])
    check("migration adds owner + heartbeat_at", "owner" in cols and "heartbeat_at" in cols)
    e = eng("guardlegacy"); c = e.connect()
    c.execute(text(legacy_runs)); c.execute(text("ALTER TABLE scheduler_runs ADD COLUMN status VARCHAR(12), ADD COLUMN error TEXT"))
    c.execute(text("""CREATE TABLE scheduler_steps (id SERIAL PRIMARY KEY, job_id VARCHAR(20), slot_ts TIMESTAMP, step VARCHAR(16),
                      label VARCHAR(200), started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR(12), note VARCHAR(500), error VARCHAR(500))"""))
    c.close(); e.dispose()

    print("\nT1  two instances fire the same slot at the same instant")
    S1, t = "2030-01-06T06:00:00", time.time() + 6
    pa, pb = worker("guardtest", "alpha", S1, child_s=4, start_at=t), worker("guardtest", "beta", S1, child_s=4, start_at=t)
    pa.wait(60); pb.wait(60)
    res = {l.split()[1]: l.split()[3] for l in marks() if l.startswith("result") and S1 in l}
    spawns = [l for l in marks() if l.startswith("spawn") and S1 in l]
    row = q("guardtest", "select owner, status, finished_at, heartbeat_at > started_at beat from scheduler_runs where slot_ts = :s", s=S1)[0]
    winner = row["owner"].split("/")[0]
    dup = q("guardtest", "select result from env_diagnostics where source='duplicate_scheduler'")
    pf = q("guardtest", "select result from env_diagnostics where source='llm_preflight'")
    check("exactly one runs, the other stands down", sorted(res.values()) == ["ok", "skipped"], str(res))
    check("exactly one child spawned", len(spawns) == 1, str(spawns))
    check("run row owned by the winner, status ok, finished, heartbeat advanced",
          res.get(winner) == "ok" and row["status"] == "ok" and row["finished_at"] and row["beat"], str(row))
    check("one duplicate_scheduler alarm naming the holder",
          len(dup) == 1 and dup[0]["result"]["holder"].startswith(winner), str(dup))
    check("one pre-flight row, stamped with the winner's instance",
          len(pf) == 1 and pf[0]["result"].get("instance", "").startswith(winner), str(pf))

    print("\nT2  owner killed mid-run (deploy kill); catch-up rescues after the heartbeat goes stale")
    S2 = "2030-01-07T06:00:00"
    pg = worker("guardtest", "gamma", S2, child_s=60)
    time.sleep(6); os.killpg(pg.pid, signal.SIGKILL); t_kill = time.time()
    pd = worker("guardtest", "delta", S2, child_s=2, wait=30); pd.wait(90)
    row = q("guardtest", "select owner, status from scheduler_runs where slot_ts = :s", s=S2)[0]
    check("rescuer claims the dead run and completes it",
          row["owner"].startswith("delta") and row["status"] == "ok", f"{row} after {time.time()-t_kill:.0f}s")
    check("rescuer waited for staleness, did not jump a live claim", "stands down" not in log("delta"))

    print("\nT3  deliberate re-run of a finished slot")
    pe = worker("guardtest", "epsilon", S1, child_s=1); pe.wait(60)
    row = q("guardtest", "select owner, status from scheduler_runs where slot_ts = :s", s=S1)[0]
    check("finished slot can be re-claimed", row["owner"].startswith("epsilon") and row["status"] == "ok", str(row))

    print("\nT4  database not migrated yet (no owner/heartbeat columns): fail open")
    S4 = "2030-01-08T06:00:00"
    pl = worker("guardlegacy", "legacy", S4, child_s=1); pl.wait(60)
    row = q("guardlegacy", "select status, finished_at from scheduler_runs where slot_ts = :s", s=S4)
    check("legacy start, run completes, status written",
          row and row[0]["status"] == "ok" and row[0]["finished_at"] and "legacy start" in log("legacy"), str(row))

    print("\nT5  owner's heartbeat stalls, another instance takes over; the stale owner must not overwrite")
    S5, t = "2030-01-09T06:00:00", time.time() + 6
    pz = worker("guardtest", "zeta", S5, child_s=14, stall_s=9, start_at=t)
    pt = worker("guardtest", "eta", S5, child_s=2, wait=30, start_at=t + 2)
    pz.wait(90); pt.wait(90)
    row = q("guardtest", "select owner, status from scheduler_runs where slot_ts = :s", s=S5)[0]
    lost = [d for d in q("guardtest", "select result from env_diagnostics where source='duplicate_scheduler'")
            if d["result"].get("lost_claim", "").startswith("zeta")]
    check("taker owns and finished the row; stale owner did not overwrite it",
          row["owner"].startswith("eta") and row["status"] == "ok", str(row))
    check("stale owner named the lost claim (log + alarm)", "CLAIM LOST" in log("zeta") and len(lost) == 1, str(lost))
finally:
    subprocess.run([f"{BIN}/pg_ctl", "-D", DATA, "-m", "fast", "stop"], capture_output=True)
    shutil.rmtree(G, ignore_errors=True)
    print(f"\n{sum(ok for _, ok in results)} of {len(results)} checks passed; throwaway cluster stopped and removed")

sys.exit(0 if results and all(ok for _, ok in results) else 1)
