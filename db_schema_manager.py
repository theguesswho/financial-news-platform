# db_schema_manager.py (Corrected)

import os
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Numeric, BigInteger, UniqueConstraint, Text, JSON # <-- THE FIX IS HERE
from sqlalchemy.orm import declarative_base
from datetime import datetime

# --- DATABASE CONNECTION SETTINGS ---
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = os.getenv("DB_HOST_IP")

# This Base is a registry for all our tables
Base = declarative_base()

# --- ALL TABLE DEFINITIONS ---

class Article(Base):
    __tablename__ = 'articles'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    link = Column(String, unique=True, nullable=False)
    published_date = Column(DateTime)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class AnalystRating(Base):
    __tablename__ = 'analyst_ratings'
    id = Column(Integer, primary_key=True)
    ticker = Column(String)
    recommendation = Column(String)
    scraped_at = Column(DateTime, default=datetime.utcnow)

class EodPrice(Base):
    __tablename__ = 'eod_prices'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    price_date = Column(Date, nullable=False)
    open_price = Column(Numeric(10, 4))
    high_price = Column(Numeric(10, 4))
    low_price = Column(Numeric(10, 4))
    close_price = Column(Numeric(10, 4))
    volume = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('ticker', 'price_date', name='_ticker_date_uc'),)
    
class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    filing_url = Column(String, unique=True)
    ai_analysis = Column(JSON)
    market_context = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class SecFiling(Base):
    __tablename__ = 'sec_filings'
    id = Column(Integer, primary_key=True)
    cik = Column(String, nullable=False)
    ticker = Column(String)
    form_type = Column(String)
    filed_at = Column(Date)
    filing_url = Column(String, unique=True, nullable=False)
    press_release_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


if __name__ == "__main__":
    print("Connecting to the database to create tables...")
    
    if not all([DB_PASS, DB_HOST]):
        print("Error: DB_PASSWORD and DB_HOST_IP environment variables must be set.")
    else:
        try:
            db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
            engine = create_engine(db_dsn)
            
            Base.metadata.create_all(engine)
            
            print("SUCCESS: All tables are created and ready in the database.")
        except Exception as e:
            print(f"An error occurred: {e}")