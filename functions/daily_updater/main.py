# functions/daily_updater/main.py

import os
import requests
import time
from datetime import datetime
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

# Add parent dir to path to import schema
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from scripts.db_schema_manager import Base, EodPrice, IncomeStatement # etc.

# --- SETTINGS & DB ---
FMP_API_KEY = os.getenv("FMP_API_KEY")
DB_USER = "postgres"; DB_PASS = os.getenv("DB_PASSWORD"); DB_NAME = "postgres"; DB_HOST = os.getenv("DB_HOST_IP")
db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(db_dsn)
Session = sessionmaker(bind=engine)

def update_daily_eod_prices(session, ticker):
    """Fetches the latest EOD price for a ticker and adds it if new."""
    try:
        api_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}?timeseries=1&apikey={FMP_API_KEY}"
        response = requests.get(api_url).json()
        
        if response and 'historical' in response and response['historical']:
            latest_data = response['historical'][0]
            price_date = datetime.strptime(latest_data['date'], '%Y-%m-%d').date()
            
            exists = session.query(EodPrice).filter_by(ticker=ticker, price_date=price_date).first()
            if not exists:
                record = EodPrice(
                    ticker=ticker, price_date=price_date, close_price=latest_data['close'],
                    volume=latest_data['volume'], pe_ratio=latest_data.get('pe')
                )
                session.add(record)
                session.commit()
                print(f"  Added new EOD price for {ticker} for date {price_date}")
    except Exception as e:
        print(f"  ERROR updating EOD for {ticker}: {e}")
        session.rollback()

def run_daily_updater(event, context):
    """The main function, triggered by Cloud Scheduler, to update all data."""
    print("--- Starting Daily Data Updater ---")
    session = Session()
    try:
        tickers_path = Path(__file__).parent.parent.parent / "config" / "tickers.txt"
        with open(tickers_path, 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]

        for i, ticker in enumerate(tickers):
            print(f"\nUpdating {i+1}/{len(tickers)}: {ticker}")
            update_daily_eod_prices(session, ticker)
            # Add other update functions here (e.g., for new financials, press releases)
            time.sleep(0.5) # Be respectful to the API

        print("\n--- Daily Data Updater Finished Successfully ---")
    
    except Exception as e:
        print(f"FATAL ERROR in Daily Updater: {e}")
    finally:
        session.close()