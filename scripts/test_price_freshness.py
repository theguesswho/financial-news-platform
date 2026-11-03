"""Evening-closes incident harness (2026-11-03).

From 21 Sep to 3 Nov 2026 the 22:00 UTC run never stored the session that
had just closed (Yahoo's `end` is exclusive and the code passed today's
date), every freshness check passed on a single SPY row, and the ops
backlog page could hang for minutes. This harness runs the REAL fixed code
against a THROWAWAY Postgres cluster (initdb in a temp dir, port 55433,
deleted afterwards). Stubbed: .env loading (prod can never be reached; the
script asserts every engine points at localhost:55433) and yfinance (a
fake `download` that honours Yahoo's exclusive `end` and can leak a partial
"today" bar). The previous price code is loaded from git HEAD and run on
the same inputs, so each price check shows before and after.

  venv/bin/python scripts/test_price_freshness.py
  PG_BIN=/path/to/postgres/bin venv/bin/python scripts/test_price_freshness.py

Exit code 0 only if every check passes.
"""
import importlib.util, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORT = 55433
DB = "pricetest"
URL = f"postgresql://postgres@localhost:{PORT}/{DB}"

# ── isolation: never read the real .env (prod DATABASE_URL) ──────────────────
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
os.environ["DATABASE_URL"] = URL

# ── fake yfinance ─────────────────────────────────────────────────────────────
import pandas as pd
YF = {"data": {}, "leak": None, "calls": []}


def _download(tickers=None, start=None, end=None, **kw):
    YF["calls"].append({"tickers": tickers, "start": str(start), "end": str(end)})
    s, e = date.fromisoformat(str(start)[:10]), date.fromisoformat(str(end)[:10])
    syms = [t for t in (tickers if isinstance(tickers, list) else str(tickers).split()) if t in YF["data"]]
    keep = lambda d: s <= d < e or d == YF["leak"]          # Yahoo: end EXCLUSIVE (+ optional partial bar)
    dates = sorted({d for sy in syms for d in YF["data"][sy] if keep(d)})
    cols = pd.MultiIndex.from_product([["Close", "High", "Low", "Open", "Volume"], syms])
    df = pd.DataFrame(index=pd.DatetimeIndex([pd.Timestamp(d) for d in dates]), columns=cols, dtype=float)
    for sy in syms:
        for d, (o, h, l, c, v) in YF["data"][sy].items():
            if keep(d):
                ts = pd.Timestamp(d)
                for f, val in (("Open", o), ("High", h), ("Low", l), ("Close", c), ("Volume", v)):
                    df.loc[ts, (f, sy)] = val
    return df


yf = types.ModuleType("yfinance")
yf.download = _download
yf.set_tz_cache_location = lambda *_: None
sys.modules["yfinance"] = yf
sys.path.insert(0, str(REPO))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {detail}")


G = tempfile.mkdtemp(prefix="pf", dir="/tmp")
BIN = os.getenv("PG_BIN", "/Applications/Postgres.app/Contents/Versions/latest/bin")
DATA = f"{G}/pgdata"


def eng(db=DB):
    e = create_engine(f"postgresql+psycopg2://postgres@localhost:{PORT}/{db}", isolation_level="AUTOCOMMIT")
    assert (e.url.host, e.url.port) == ("localhost", PORT), "REFUSING: not the throwaway cluster"
    return e


def oeng():
    """Transactional engine (default isolation), like prod's ORM sessions."""
    e = create_engine(f"postgresql+psycopg2://postgres@localhost:{PORT}/{DB}")
    assert (e.url.host, e.url.port) == ("localhost", PORT), "REFUSING: not the throwaway cluster"
    return e


def q(sql, **kw):
    e = eng()
    with e.connect() as c:
        r = c.execute(text(sql), kw).fetchall()
    e.dispose()
    return r


def x(sql, **kw):
    e = eng()
    with e.connect() as c:
        c.execute(text(sql), kw)
    e.dispose()


def bar(c, v=1_000_000):
    return (c - 0.5, c + 1.0, c - 1.0, c, v)


def utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def load_old_prices():
    """pipeline/prices.py as it is on HEAD (the code prod runs)."""
    src = subprocess.run(["git", "show", "HEAD:pipeline/prices.py"], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    p = Path(G) / "old_prices.py"
    p.write_text(src)
    spec = importlib.util.spec_from_file_location("old_prices", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def freeze_today(module, d):
    class _D(date):
        @classmethod
        def today(cls):
            return cls(d.year, d.month, d.day)
    module.date = _D


subprocess.run([f"{BIN}/initdb", "-D", DATA, "-U", "postgres", "-A", "trust", "--no-sync"],
               check=True, capture_output=True)
subprocess.run([f"{BIN}/pg_ctl", "-D", DATA, "-l", f"{G}/pg.log", "-w", "start", "-o",
                f"-p {PORT} -c listen_addresses=localhost -c unix_socket_directories=''"],
               check=True, capture_output=True)
try:
    eng("postgres").connect().execute(text(f"CREATE DATABASE {DB}"))
    # eod_prices exactly as prod has it: unique INDEX (not a named constraint)
    x("""CREATE TABLE eod_prices (id SERIAL PRIMARY KEY, symbol VARCHAR(10) NOT NULL, date DATE NOT NULL,
         open NUMERIC(12,4), high NUMERIC(12,4), low NUMERIC(12,4), close NUMERIC(12,4), volume BIGINT)""")
    x("CREATE UNIQUE INDEX uq_eod_prices_symbol_date ON eod_prices USING btree (symbol, date)")

    import pipeline.trading_days as td
    import api.trading_days as atd
    import pipeline.prices as newp
    from pipeline.freshness_sentinel import price_coverage, check_price_coverage, run_sentinel

    print("\n1. Trading calendar")
    cases = [(utc(2026, 11, 2, 22), date(2026, 11, 2), "Mon 22:00 UTC (EST) -> Monday"),
             (utc(2026, 11, 3, 6), date(2026, 11, 2), "Tue 06:00 UTC -> Monday"),
             (utc(2026, 11, 2, 6), date(2026, 10, 30), "Mon 06:00 UTC -> Friday"),
             (utc(2026, 11, 26, 22), date(2026, 11, 25), "Thanksgiving evening -> Wednesday"),
             (utc(2026, 7, 15, 20, 30), date(2026, 7, 15), "summer 16:30 EDT -> same day"),
             (utc(2026, 7, 15, 20, 10), date(2026, 7, 14), "summer 16:10 EDT -> day before"),
             (utc(2026, 11, 7, 22), date(2026, 11, 6), "Saturday -> Friday")]
    for now, want, label in cases:
        got = td.last_closed_session(now)
        check(f"last closed session: {label}", got == want, f"got {got}")
    rule_ok = all(td._ny_rule(utc(2026, 1, 1, 0) + timedelta(hours=h)).utcoffset() ==
                  td.ny_time(utc(2026, 1, 1, 0) + timedelta(hours=h)).utcoffset()
                  for h in range(0, 24 * 730))
    check("built-in Eastern-time rule equals the tz database every hour of 2026-2027", rule_ok)
    check("Yahoo end at Mon 22:00 UTC is Tuesday (exclusive end keeps Monday)",
          td.yahoo_end(utc(2026, 11, 2, 22)) == date(2026, 11, 3))
    # the API's due-session rule must be unchanged by the calendar move
    old_api = subprocess.run(["git", "show", "HEAD:api/trading_days.py"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
    ns: dict = {}
    exec(compile(old_api, "old_api_trading_days", "exec"), ns)
    same = all(ns["last_trading_day"](utc(2026, 1, 1, 0) + timedelta(hours=h)) ==
               atd.last_trading_day(utc(2026, 1, 1, 0) + timedelta(hours=h))
               for h in range(0, 24 * 730, 5))
    check("API last_trading_day identical to HEAD for every 5h step over 2026-2027", same)

    print("\n2. Evening fetch at Mon 2 Nov 22:00 UTC (old code vs new)")
    sessions = [date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30), date(2026, 11, 2)]
    YF["data"] = {s: {d: bar(100 + i + j) for j, d in enumerate(sessions)} for i, s in enumerate(["AAA", "BBB", "CCC"])}
    YF["leak"] = None
    # AAA already has 27, 29, 30 Oct stored — 28 Oct is a HOLE inside the window
    for d in (date(2026, 10, 27), date(2026, 10, 29), date(2026, 10, 30)):
        o, h, l, c, v = YF["data"]["AAA"][d]
        x("INSERT INTO eod_prices (symbol, date, open, high, low, close, volume) VALUES ('AAA', :d, :o, :h, :l, :c, :v)",
          d=d, o=o, h=h, l=l, c=c, v=v)
    snapshot = q("SELECT symbol, date, close FROM eod_prices ORDER BY 1, 2")

    old = load_old_prices()
    freeze_today(old, date(2026, 11, 2))                 # Railway at 22:00 UTC: date.today() = Monday
    e = eng()
    oe = oeng()
    with Session(oe) as s:
        r_old = old.fetch_prices(s, ["AAA", "BBB", "CCC"], days=7)
    old_end = YF["calls"][-1]["end"]
    old_mon = q("SELECT COUNT(*) FROM eod_prices WHERE date = '2026-11-02'")[0][0]
    old_hole = q("SELECT COUNT(*) FROM eod_prices WHERE symbol = 'AAA' AND date = '2026-10-28'")[0][0]
    check("BEFORE (HEAD): end passed to Yahoo is Monday itself", old_end.startswith("2026-11-02"), old_end)
    check("BEFORE (HEAD): Monday's close stored for 0 of 3 names", old_mon == 0, f"{old_mon} stored")
    check("BEFORE (HEAD): AAA's 28 Oct hole NOT filled (later rows existed)", old_hole == 0,
          f"old code reported added={r_old.get('added')}")

    x("TRUNCATE eod_prices RESTART IDENTITY")
    for sym, d, c in snapshot:
        o, h, l, cc, v = YF["data"][sym][d]
        x("INSERT INTO eod_prices (symbol, date, open, high, low, close, volume) VALUES (:s, :d, :o, :h, :l, :c, :v)",
          s=sym, d=d, o=o, h=h, l=l, c=cc, v=v)
    for i, sym in enumerate(["AAA", "BBB", "CCC"]):
        YF["data"][sym][date(2026, 11, 3)] = bar(200 + i)  # a Tuesday bar exists at the vendor...
    YF["leak"] = date(2026, 11, 3)                       # ...and Yahoo leaks it as a partial bar
    with Session(oe) as s:
        r_new = newp.fetch_prices(s, ["AAA", "BBB", "CCC"], days=7, now=utc(2026, 11, 2, 22))
    new_end = YF["calls"][-1]["end"]
    new_mon = q("SELECT COUNT(*) FROM eod_prices WHERE date = '2026-11-02'")[0][0]
    new_hole = q("SELECT COUNT(*) FROM eod_prices WHERE symbol = 'AAA' AND date = '2026-10-28'")[0][0]
    leaked = q("SELECT COUNT(*) FROM eod_prices WHERE date > '2026-11-02'")[0][0]
    total = q("SELECT COUNT(*) FROM eod_prices")[0][0]
    check("AFTER: end passed to Yahoo is Tuesday (Monday included)", new_end.startswith("2026-11-03"), new_end)
    check("AFTER: Monday's close stored for 3 of 3 names", new_mon == 3, f"{new_mon} stored")
    check("AFTER: AAA's 28 Oct hole filled", new_hole == 1)
    check("AFTER: a partial bar dated after the last closed session is never stored", leaked == 0)
    check("AFTER: counts are honest (12 added, 0 corrected; 15 rows in table)",
          r_new["added"] == 12 and r_new["corrected"] == 0 and total == 15, str(r_new))
    check("AFTER: result names the session and how many names have it",
          r_new["last_session"] == "2026-11-02" and r_new["session_names"] == 3, str(r_new))

    print("\n3. Morning run at Tue 3 Nov 06:00 UTC overwrites the last two sessions")
    YF["leak"] = None
    YF["data"]["AAA"][date(2026, 11, 2)] = bar(150.25, 2_000_000)    # settled close differs from 22:00 value
    YF["data"]["BBB"][date(2026, 10, 30)] = bar(151.5, 3_000_000)   # second-latest session differs too
    YF["data"]["CCC"][date(2026, 10, 29)] = bar(152.75, 4_000_000)  # older session: must NOT be touched
    before_ccc = q("SELECT close FROM eod_prices WHERE symbol='CCC' AND date='2026-10-29'")[0][0]
    with Session(oe) as s:
        r_m = newp.fetch_prices(s, ["AAA", "BBB", "CCC"], days=7, refresh_sessions=2, now=utc(2026, 11, 3, 6))
    aaa = q("SELECT close, volume FROM eod_prices WHERE symbol='AAA' AND date='2026-11-02'")[0]
    bbb = q("SELECT close FROM eod_prices WHERE symbol='BBB' AND date='2026-10-30'")[0][0]
    ccc = q("SELECT close FROM eod_prices WHERE symbol='CCC' AND date='2026-10-29'")[0][0]
    check("Monday's 22:00 close corrected in the morning", float(aaa[0]) == 150.25 and aaa[1] == 2_000_000, str(aaa))
    check("Friday (second-latest session) corrected", float(bbb) == 151.5)
    check("older sessions left as stored", ccc == before_ccc, f"{ccc}")
    check("only changed rows counted as corrected (2), none added",
          r_m["corrected"] == 2 and r_m["added"] == 0 and r_m["refreshed"] == ["2026-10-30", "2026-11-02"], str(r_m))
    with Session(oe) as s:
        r_m2 = newp.fetch_prices(s, ["AAA", "BBB", "CCC"], days=7, refresh_sessions=2, now=utc(2026, 11, 3, 6))
    check("re-running the morning fetch changes nothing", r_m2["corrected"] == 0 and r_m2["added"] == 0, str(r_m2))

    print("\n4. Coverage check vs the old MAX(date) check")
    x("TRUNCATE eod_prices RESTART IDENTITY")
    names = [f"N{i:03d}" for i in range(100)]
    for d in sessions[:-1]:
        x("INSERT INTO eod_prices (symbol, date, close) SELECT unnest(cast(:s as text[])), :d, 10",
          s=names + ["SPY"], d=d)
    x("INSERT INTO eod_prices (symbol, date, close) VALUES ('SPY', '2026-11-02', 10)")   # the 2 Nov evening state
    mon = date(2026, 11, 2)
    old_ok = q("SELECT MAX(date) FROM eod_prices")[0][0] >= mon
    with e.connect() as c:
        c1 = price_coverage(c, mon)
    check("state of 2 Nov 22:00: old MAX(date) check says fresh", old_ok)
    check("state of 2 Nov 22:00: coverage says 0 of 100 names -> NOT ok", not c1["ok"] and c1["have"] == 0
          and c1["reference"] == 100, str(c1))
    x("INSERT INTO eod_prices (symbol, date, close) SELECT unnest(cast(:s as text[])), '2026-11-02', 10", s=names[:94])
    with e.connect() as c:
        c2 = price_coverage(c, mon)
    x("INSERT INTO eod_prices (symbol, date, close) SELECT unnest(cast(:s as text[])), '2026-11-02', 10", s=names[94:95])
    with e.connect() as c:
        c3 = price_coverage(c, mon)
    check("94 of 100 -> NOT ok; 95 of 100 -> ok (threshold 95%)", (not c2["ok"]) and c3["ok"], f"{c2['have']}, {c3['have']}")
    x("DELETE FROM eod_prices WHERE date = '2026-11-02' AND symbol <> 'SPY'")
    v = check_price_coverage(e, mon)
    check("sentinel violation names the gap in plain words",
          len(v) == 1 and v[0]["latest"] == "0 of 100 names have the 2026-11-02 close", str(v))
    x("CREATE TABLE env_diagnostics (id SERIAL PRIMARY KEY, source VARCHAR(40), result JSONB, created_at TIMESTAMP DEFAULT NOW())")
    import pipeline.freshness_sentinel as fs
    _real_lcs = td.last_closed_session
    td.last_closed_session = lambda now=None: mon          # pin "today" for run_sentinel's default
    try:
        sv = run_sentinel(e)
    finally:
        td.last_closed_session = _real_lcs
    stored = q("SELECT result FROM env_diagnostics WHERE source='freshness' ORDER BY id DESC LIMIT 1")[0][0]
    check("run_sentinel stores the coverage violation (daily brief reads it)",
          any(x_.get("source") == "eod_prices coverage" for x_ in stored), str([x_.get("source") for x_ in sv])[:160])

    print("\n5. GET /health/platform price check")
    x("CREATE TABLE scheduler_runs (id SERIAL PRIMARY KEY, job_id VARCHAR(20), slot_ts TIMESTAMP, started_at TIMESTAMP, finished_at TIMESTAMP)")
    x("INSERT INTO scheduler_runs (job_id, slot_ts, started_at, finished_at) VALUES ('daily', NOW(), NOW(), NOW())")
    x("CREATE TABLE leaderboard_history (id SERIAL PRIMARY KEY, symbol VARCHAR(10), date DATE)")
    import api.deps as deps
    deps._engine = None
    import api.routers.health as health
    due = atd.last_trading_day()
    x("INSERT INTO leaderboard_history (symbol, date) VALUES ('AAA', :d)", d=due)
    x("DELETE FROM eod_prices")
    for d in [due - timedelta(days=k) for k in range(1, 10)]:
        x("INSERT INTO eod_prices (symbol, date, close) SELECT unnest(cast(:s as text[])), :d, 10", s=names + ["SPY"], d=d)
    x("INSERT INTO eod_prices (symbol, date, close) VALUES ('SPY', :d, 10)", d=due)
    h1 = health._run_checks()
    x("INSERT INTO eod_prices (symbol, date, close) SELECT unnest(cast(:s as text[])), :d, 10", s=names, d=due)
    h2 = health._run_checks()
    check(f"due session {due} with only SPY: health FAILS on eod_prices (old check passed)",
          h1["checks"]["eod_prices"]["ok"] is False and "eod_prices" in h1["failing"]
          and h1["checks"]["eod_prices"]["latest"] == due.isoformat(), str(h1["checks"]["eod_prices"]))
    check("all names present: health passes", h2["checks"]["eod_prices"]["ok"] and h2["status"] == "ok",
          str(h2["checks"]["eod_prices"]))
    u = deps.get_engine().url
    check("API engine accepted connect_timeout / tcp_user_timeout / keepalives (libpq %s)"
          % __import__("psycopg2").__libpq_version__, (u.host, u.port) == ("localhost", PORT))

    print("\n6. /ops/backlog: 8-Ks out of the backlog figure; hard deadline")
    x("""CREATE TABLE filings (id SERIAL PRIMARY KEY, symbol VARCHAR(10), filing_type VARCHAR(20), filing_date TIMESTAMP,
         created_at TIMESTAMP DEFAULT NOW(), event_type VARCHAR(30), backfilled BOOLEAN DEFAULT FALSE)""")
    x("CREATE TABLE filing_themes (id SERIAL PRIMARY KEY, filing_id INT, symbol VARCHAR(10))")
    x("""INSERT INTO filings (symbol, filing_type, filing_date) VALUES ('AAA','8-K',NOW()), ('AAA','8-K',NOW()),
         ('BBB','10-Q',NOW())""")
    from fastapi import Response
    import api.routers.ops as ops
    t0 = time.time(); body = ops.backlog(Response()); el = time.time() - t0
    fw = body["backlog"]["filings_without_analysis_by_type_30d"]
    check("backlog lists 10-Q only (2 unthemed 8-Ks no longer counted)", fw == [["10-Q", 1]], f"{fw} in {el:.1f}s")
    # stuck mid-query: another session holds an ACCESS EXCLUSIVE lock on filings
    ops.OPS_DEADLINE_S = 3
    blocker = oeng().connect()
    tx = blocker.begin()
    blocker.execute(text("SET LOCAL lock_timeout = '60s'"))
    blocker.execute(text("LOCK TABLE filings IN ACCESS EXCLUSIVE MODE"))
    r6 = Response(); t0 = time.time(); body = ops.backlog(r6); el = time.time() - t0
    tx.rollback(); blocker.close()
    check("query stuck behind a lock: 503 within the deadline, names the section",
          r6.status_code == 503 and body.get("stuck_in") == "backlog" and el < 5, f"{body} in {el:.1f}s")
    # stuck on the connection: a server that accepts TCP and never answers
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(8); bh_port = srv.getsockname()[1]
    held = []
    def _accept_forever():
        try:
            for _ in range(8):
                held.append(srv.accept())        # accept, never answer, never close
        except OSError:
            pass                                 # listener closed at the end of the test
    threading.Thread(target=_accept_forever, daemon=True).start()
    os.environ["DATABASE_URL"] = f"postgresql://postgres@127.0.0.1:{bh_port}/{DB}"
    deps._engine = None
    r7 = Response(); t0 = time.time(); body = ops.backlog(r7); el = time.time() - t0
    check("connection that never answers: 503 within the deadline, stuck in 'connect'",
          r7.status_code == 503 and body.get("stuck_in") == "connect" and el < 5, f"{body} in {el:.1f}s")
    t0 = time.time()
    try:
        deps.get_engine().connect()
        released = False
    except Exception as ex:
        released = "timeout" in str(ex).lower()
    el = time.time() - t0
    check("the worker behind it is released by connect_timeout (10s), not left hanging",
          released and el < 25, f"{el:.1f}s")
    os.environ["DATABASE_URL"] = URL
    deps._engine = None
    srv.close()

    print("\n7. Deploy-gate DDL lint on every changed file")
    DDL_RE = re.compile(r"\b(ALTER TABLE|ADD COLUMN|CREATE (?:UNIQUE )?INDEX)\b")
    changed = ["pipeline/prices.py", "pipeline/trading_days.py", "pipeline/freshness_sentinel.py",
               "pipeline/hidden_gem_scorer.py", "pipeline/brief.py", "scheduler_light.py",
               "api/routers/health.py", "api/routers/ops.py", "api/deps.py", "api/trading_days.py"]
    hits = [f"{f}:{n}" for f in changed for n, line in enumerate(open(REPO / f), 1)
            if not line.strip().startswith("#") and DDL_RE.search(line)]
    check("no table DDL in run paths", not hits, str(hits))
finally:
    subprocess.run([f"{BIN}/pg_ctl", "-D", DATA, "-m", "immediate", "stop"], capture_output=True)
    shutil.rmtree(G, ignore_errors=True)
    print(f"\n{sum(ok for _, ok in results)} of {len(results)} checks passed; throwaway cluster stopped and removed")

sys.exit(0 if results and all(ok for _, ok in results) else 1)
