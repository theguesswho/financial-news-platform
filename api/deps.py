"""Shared helpers for the read layer."""
import os

from sqlalchemy import create_engine

# The API's OWN engine (R1, 2026-09-20). It used to share db.session's
# engine with the pipeline; that engine has no statement timeout because
# the scheduler runs hour-long jobs on it. A read layer needs the
# opposite: a query that cannot finish in 15s must fail that one request
# (503) instead of holding a worker while a lock queue builds — the
# 2026-09-14 outage hung every /board request for 3.5 days. Connections
# are recycled every 30 min so role-level settings (idle-in-transaction /
# lock timeouts) reach the pool without a redeploy.
API_STATEMENT_TIMEOUT_MS = int(os.getenv("API_STATEMENT_TIMEOUT_MS", "15000"))

_engine = None


def _url() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
    host = os.environ["DB_HOST_IP"]
    password = os.environ["DB_PASSWORD"]
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return f"postgresql+psycopg2://{user}:{password}@{host}/{name}"


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _url(),
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"options": f"-c statement_timeout={API_STATEMENT_TIMEOUT_MS}"},
        )
    return _engine


def ten(v, dp: int = 1):
    """Boundary transform: internal 0-1 scores leave the API on the
    10-point display scale (pipeline.tiers.fmt10 convention), as numbers.
    None passes through so 'no data' stays distinguishable from 0."""
    if v is None:
        return None
    return round(float(v) * 10, dp)
