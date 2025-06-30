# scripts/db_schema_manager.py
import os
from sqlalchemy import create_engine
# Import our single source of truth
from common.db_models import Base

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_HOST = os.getenv("DB_HOST_IP")

if __name__ == "__main__":
    db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
    engine = create_engine(db_dsn)
    
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)
    print("Creating all tables from the common model definitions...")
    Base.metadata.create_all(engine)
    print("SUCCESS: Database schema is now synchronized with common/db_models.py")