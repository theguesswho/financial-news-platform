import os
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON
from fastapi import FastAPI, Depends

# --- DATABASE CONNECTION & SETUP ---
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = os.getenv("DB_HOST_IP")

# Create the database engine
engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
# Create a Session class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Create a Base for our models
Base = declarative_base()

# --- DATABASE MODEL DEFINITION ---
# We define the 'Report' model here so the API knows the data structure
class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True, index=True)
    filing_url = Column(String, unique=True)
    ai_analysis = Column(JSON)
    market_context = Column(JSON)
    created_at = Column(DateTime)

# --- API DEFINITION ---
# Create the FastAPI application object
app = FastAPI()

# Dependency to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Define our first API endpoint
@app.get("/reports")
def read_reports(db: sqlalchemy.orm.Session = Depends(get_db)):
    """
    This endpoint fetches all the generated reports from the database.
    """
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return reports