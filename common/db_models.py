# common/db_models.py (The Single Source of Truth)
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Numeric, BigInteger, UniqueConstraint, Text, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Article(Base):
    # ... (code for this class) ...
    __tablename__ = 'articles'
    id = Column(Integer, primary_key=True)
    link = Column(String, unique=True, nullable=False)
    title = Column(String); source = Column(String)
    published_date = Column(DateTime); created_at = Column(DateTime, default=datetime.utcnow)

class EodPrice(Base):
    # ... (code for this class) ...
    __tablename__ = 'eod_prices'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False); price_date = Column(Date, nullable=False)
    close_price = Column(Numeric(10, 4)); volume = Column(BigInteger)
    pe_ratio = Column(Numeric(10, 4), nullable=True) 
    __table_args__ = (UniqueConstraint('ticker', 'price_date', name='_ticker_date_uc'),)

class Report(Base):
    # ... (code for this class) ...
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    source_url = Column(String, unique=True)
    ai_thesis = Column(JSON); briefing_document = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class IncomeStatement(Base):
    # ... (code for this class) ...
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
    # ... (code for this class) ...
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
    # ... (code for this class) ...
    __tablename__ = 'cash_flow_statements'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    period = Column(String)
    net_cash_from_ops = Column(BigInteger); net_cash_from_investing = Column(BigInteger)
    net_cash_from_financing = Column(BigInteger)
    free_cash_flow = Column(BigInteger)
    __table_args__ = (UniqueConstraint('ticker', 'date', 'period', name='_cash_flow_uc'),)