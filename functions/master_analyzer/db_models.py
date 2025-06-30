# scripts/db_schema_manager.py (FINAL FINANCIALS VERSION)

import os
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Numeric, BigInteger, UniqueConstraint, Text, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime

# --- DATABASE CONNECTION SETTINGS ---
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = os.getenv("DB_HOST_IP")

Base = declarative_base()

# --- TABLE DEFINITIONS ---

class Article(Base):
    __tablename__ = 'articles'
    id = Column(Integer, primary_key=True)
    link = Column(String, unique=True, nullable=False)
    title = Column(String); source = Column(String)
    published_date = Column(DateTime); created_at = Column(DateTime, default=datetime.utcnow)

class EodPrice(Base):
    __tablename__ = 'eod_prices'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False); price_date = Column(Date, nullable=False)
    close_price = Column(Numeric(10, 4)); volume = Column(BigInteger)
    pe_ratio = Column(Numeric(10, 4), nullable=True) 
    __table_args__ = (UniqueConstraint('ticker', 'price_date', name='_ticker_date_uc'),)

class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    source_url = Column(String, unique=True)
    ai_thesis = Column(JSON); briefing_document = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- NEW FINANCIAL STATEMENT TABLES ---

class IncomeStatement(Base):
    __tablename__ = 'income_statements'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    period = Column(String) # 'quarter' or 'annual'
    revenue = Column(BigInteger); cost_of_revenue = Column(BigInteger)
    gross_profit = Column(BigInteger); gross_profit_ratio = Column(Numeric(10, 4))
    net_income = Column(BigInteger); eps = Column(Numeric(10, 4))
    __table_args__ = (UniqueConstraint('ticker', 'date', 'period', name='_income_stmt_uc'),)

class BalanceSheet(Base):
    __tablename__ = 'balance_sheets'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    period = Column(String)
    total_assets = Column(BigInteger); total_liabilities = Column(BigInteger)
    total_debt = Column(BigInteger); cash_and_equivalents = Column(BigInteger)
    total_equity = Column(BigInteger)
    __table_args__ = (UniqueConstraint('ticker', 'date', 'period', name='_balance_sheet_uc'),)
    
class CashFlowStatement(Base):
    __tablename__ = 'cash_flow_statements'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    period = Column(String)
    net_cash_from_ops = Column(BigInteger); net_cash_from_investing = Column(BigInteger)
    net_cash_from_financing = Column(BigInteger)
    free_cash_flow = Column(BigInteger)
    __table_args__ = (UniqueConstraint('ticker', 'date', 'period', name='_cash_flow_uc'),)


if __name__ == "__main__":
    print("Connecting to the database to create/update tables...")
    
    if not all([DB_PASS, DB_HOST]):
        print("Error: DB_PASSWORD and DB_HOST_IP environment variables must be set.")
    else:
        try:
            db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
            engine = create_engine(db_dsn)
            
            print("Dropping all existing tables to ensure a clean slate for the new schema...")
            # We drop all tables to ensure no legacy data or columns remain
            Base.metadata.drop_all(engine)
            print("...Tables dropped successfully.")
            
            print("\nCREATING ALL TABLES FROM SCRATCH with the new financial schema...")
            Base.metadata.create_all(engine)
            
            print("\nSUCCESS: All tables have been recreated with the latest schema.")
        except Exception as e:
            print(f"\nAn error occurred: {e}")