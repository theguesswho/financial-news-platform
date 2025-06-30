# scripts/backfill_financials.py

import os
import requests
import time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_schema_manager import Base, EodPrice, IncomeStatement, BalanceSheet, CashFlowStatement
from pathlib import Path

# --- SETTINGS ---
FMP_API_KEY = os.getenv("FMP_API_KEY")
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = os.getenv("DB_HOST_IP")

# --- DATABASE CONNECTION ---
db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(db_dsn)
Session = sessionmaker(bind=engine)

def fetch_financial_statements(session, ticker):
    """Fetches and saves all quarterly financial statements for a ticker."""
    print(f"  Fetching financial statements for {ticker}...")
    try:
        # FMP provides a comprehensive endpoint for this
        api_url = f"https://financialmodelingprep.com/api/v3/financial-statement-full-as-reported/{ticker}?period=quarter&limit=40&apikey={FMP_API_KEY}"
        statements = requests.get(api_url, timeout=90).json()

        if not statements or not isinstance(statements, list):
            print(f"    No financial statements found for {ticker}.")
            return
        
        income_stmt_records = []
        balance_sheet_records = []
        cash_flow_records = []

        for stmt in statements:
            date_val = datetime.strptime(stmt['date'], '%Y-%m-%d').date()
            
            # Create Income Statement record
            income_stmt_records.append(IncomeStatement(
                ticker=ticker, date=date_val, period='quarter',
                revenue=stmt.get('revenue'), cost_of_revenue=stmt.get('costofrevenue'),
                gross_profit=stmt.get('grossprofit'), gross_profit_ratio=stmt.get('grossprofitratio'),
                net_income=stmt.get('netincome'), eps=stmt.get('eps')
            ))
            
            # Create Balance Sheet record
            balance_sheet_records.append(BalanceSheet(
                ticker=ticker, date=date_val, period='quarter',
                total_assets=stmt.get('totalassets'), total_liabilities=stmt.get('totalliabilities'),
                total_debt=stmt.get('totaldebt'), cash_and_equivalents=stmt.get('cashandcashequivalents'),
                total_equity=stmt.get('totalstockholdersequity')
            ))
            
            # Create Cash Flow Statement record
            cash_flow_records.append(CashFlowStatement(
                ticker=ticker, date=date_val, period='quarter',
                net_cash_from_ops=stmt.get('netcashprovidedbyoperatingactivities'),
                net_cash_from_investing=stmt.get('netcashusedforinvestingactivities'),
                net_cash_from_financing=stmt.get('netcashusedprovidedbyfinancingactivities'),
                free_cash_flow=stmt.get('freecashflow')
            ))

        # Bulk insert records for efficiency
        session.bulk_save_objects(income_stmt_records)
        session.bulk_save_objects(balance_sheet_records)
        session.bulk_save_objects(cash_flow_records)
        
        session.commit()
        print(f"    Saved {len(statements)} quarters of financial statements for {ticker}.")

    except Exception as e:
        session.rollback()
        print(f"    ERROR fetching financial statements for {ticker}: {e}")

def run_financials_backfill():
    """Main function to run the entire backfill process."""
    if not FMP_API_KEY or not DB_PASS:
        print("Error: FMP_API_KEY and DB_PASSWORD environment variables must be set.")
        return

    session = Session()

    # --- Wiping tables to ensure a clean slate ---
    print("--- Wiping existing financial statement data ---")
    try:
        session.execute(IncomeStatement.__table__.delete())
        session.execute(BalanceSheet.__table__.delete())
        session.execute(CashFlowStatement.__table__.delete())
        session.commit()
        print("--- Existing financial data wiped successfully ---")
    except Exception as e:
        print(f"--- Error wiping data: {e} ---")
        session.rollback()
        session.close()
        return
    
    script_dir = Path(__file__).parent
    tickers_path = script_dir.parent / "config" / "tickers.txt"
    with open(tickers_path, 'r') as f:
        tickers = [line.strip() for line in f if line.strip()]

    print(f"--- Starting Financial Statement Backfill for {len(tickers)} Tickers ---")
    
    for i, ticker in enumerate(tickers):
        print(f"\nProcessing Ticker {i+1}/{len(tickers)}: {ticker}")
        fetch_financial_statements(session, ticker)
        time.sleep(1) # Be respectful to the API

    session.close()
    print("\n--- Full Financial Statement Backfill Complete ---")

if __name__ == "__main__":
    run_financials_backfill()