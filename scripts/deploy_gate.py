"""Deploy gate: block pushes during/near scheduler runs (see .githooks),
and refuse table DDL outside db/migrate.py (V3 #26 R1, 2026-09-20)."""
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# 0. DDL lint — runs first and offline. Schema statements executed inside
#    run steps took the site down twice (2026-09-09, 2026-09-14: an ALTER
#    queued behind an idle transaction blocked every reader). They live in
#    db/migrate.py only. Comment lines are skipped; SQL strings are not.
DDL_RE = re.compile(r"\b(ALTER TABLE|ADD COLUMN|CREATE (?:UNIQUE )?INDEX)\b")
DDL_ALLOWED = {"db/migrate.py"}
tracked = subprocess.run(
    ["git", "ls-files", "pipeline", "api", "scheduler_light.py"],
    capture_output=True, text=True, cwd=ROOT).stdout.split()
ddl_hits = []
for rel in tracked:
    if rel in DDL_ALLOWED or not rel.endswith(".py"):
        continue
    with open(ROOT / rel, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.strip().startswith("#"):
                continue
            if DDL_RE.search(line):
                ddl_hits.append(f"  {rel}:{n}: {line.strip()[:90]}")
if ddl_hits:
    print("\nDEPLOY BLOCKED: table DDL outside db/migrate.py (run steps must "
          "assume the schema — V3 #26):\n" + "\n".join(ddl_hits))
    sys.exit(1)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)
from sqlalchemy import text  # noqa: E402

from pipeline.hidden_gem_scorer import get_engine  # noqa: E402

now = datetime.now(timezone.utc).replace(tzinfo=None)

# 1. live run?
with get_engine().connect() as c:
    live = c.execute(text("""
        SELECT job_id, started_at FROM scheduler_runs
        WHERE started_at > NOW() - INTERVAL '2 hours' AND finished_at IS NULL
        ORDER BY started_at DESC LIMIT 1""")).fetchone()
if live:
    print(f"\nDEPLOY BLOCKED: '{live[0]}' run live since {live[1]} UTC "
          f"(deploys kill runs — the Saturday lesson).\n"
          f"Wait for it to finish, or DEPLOY_ANYWAY=1 git push for emergencies.")
    sys.exit(1)

# 1b. queue job running? (the bridge-weekly lesson, 2026-08-09)
with get_engine().connect() as c:
    qjob = c.execute(text("""
        SELECT job_type FROM job_queue WHERE status='running'
        UNION ALL SELECT 'onboarding' FROM onboarding_queue WHERE status='running'
        LIMIT 1""")).fetchone()
if qjob:
    print(f"\nDEPLOY BLOCKED: queue job '{qjob[0]}' is running on Railway "
          f"(a deploy would kill it). Wait for it, or DEPLOY_ANYWAY=1.")
    sys.exit(1)

# 2. slot starting within 10 minutes? (06:00 daily; 13:00/21:00 Mon-Fri)
slots = [(6, 0, "daily", range(7)),
         (22, 0, "after_close", range(5)),
         (23, 30, "weekly", (4,))]   # Fri 23:30 UTC = 7:30am Sat SGT, ~60 min
for h, m, name, days in slots:
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    for d in (slot, slot + timedelta(days=1)):
        delta = (d - now).total_seconds() / 60
        if 0 <= delta <= 10 and d.weekday() in days:
            print(f"\nDEPLOY BLOCKED: '{name}' slot starts in {delta:.0f} min "
                  f"({d:%H:%M} UTC). Push after it completes.")
            sys.exit(1)
print("deploy gate: clear")
