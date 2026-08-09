"""Deploy gate: block pushes during/near scheduler runs (see .githooks)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)
from sqlalchemy import text

from pipeline.hidden_gem_scorer import get_engine

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

# 2. slot starting within 10 minutes? (06:00 daily; 13:00/21:00 Mon-Fri)
slots = [(6, 0, "daily", range(7)), (13, 0, "midday", range(5)),
         (21, 0, "after_close", range(5)),
         (22, 0, "weekly", (4,))]   # Friday 22:00 UTC = 6am Sat SGT, ~60 min
for h, m, name, days in slots:
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    for d in (slot, slot + timedelta(days=1)):
        delta = (d - now).total_seconds() / 60
        if 0 <= delta <= 10 and d.weekday() in days:
            print(f"\nDEPLOY BLOCKED: '{name}' slot starts in {delta:.0f} min "
                  f"({d:%H:%M} UTC). Push after it completes.")
            sys.exit(1)
print("deploy gate: clear")
