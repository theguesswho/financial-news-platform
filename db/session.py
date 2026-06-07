import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base

_engine = None
_Session = None


def _get_engine():
    global _engine
    if _engine is None:
        host = os.environ["DB_HOST_IP"]
        password = os.environ["DB_PASSWORD"]
        user = os.getenv("DB_USER", "postgres")
        name = os.getenv("DB_NAME", "postgres")
        url = f"postgresql+psycopg2://{user}:{password}@{host}/{name}"
        _engine = create_engine(url, pool_pre_ping=True)
        Base.metadata.create_all(_engine)
    return _engine


def get_session():
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=_get_engine())
    return _Session()
