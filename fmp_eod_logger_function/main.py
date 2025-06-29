# fmp_eod_logger_function/main.py (The Correct Version)

import os
import requests
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, BigInteger, UniqueConstraint
from datetime import datetime
import time
from pathlib import Path

# --- SETTINGS & SCHEMA ---
DB_USER = "postgres"; DB_PASS = os.getenv("DB_PASSWORD"); DB_NAME = "postgres"; DB_HOST = os.getenv("DB_HOST_IP"); FMP_API_KEY = os.getenv("FMP_API_KEY")
Base = declarative_base()
class EodPrice(Base):
    __tablename__ = 'eod_prices'; id = Column(Integer, primary_key=True); ticker = Column(String, nullable=False); price_date = Column(Date, nullable=False); open_price = Column(Numeric(10, 4)); high_price = Column(Numeric(10, 4)); low_price = Column(Numeric(10, 4)); close_price = Column(Numeric(10, 4)); volume = Column(BigInteger); created_at = Column(DateTime, default=datetime.utcnow); __table_args__ = (UniqueConstraint('ticker', 'price_date', name='_ticker_date_uc'),)

def fetch_and_save_eod_data(engine, ticker_symbol):
    try:
        api_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker_symbol}?apikey={FMP_API_KEY}"
        print(f"Fetching data for {ticker_symbol}...")
        response = requests.get(api_url, timeout=20); response.raise_for_status(); data = response.json()
        daily_data = data.get('historical', [])
        if not daily_data: print(f"--> {ticker_symbol}: No data found."); return

        Session = sessionmaker(bind=engine); session = Session()
        new_records_count = 0
        for values in daily_data[:100]:
            price_date = datetime.strptime(values['date'], '%Y-%m-%d').date()
            exists = session.query(EodPrice).filter_by(ticker=ticker_symbol, price_date=price_date).first()
            if not exists:
                new_records_count += 1
                new_record = EodPrice(ticker=ticker_symbol, price_date=price_date, open_price=values['open'], high_price=values['high'], low_price=values['low'], close_price=values['close'], volume=values['volume'])
                session.add(new_record)
        if new_records_count > 0: session.commit()
        print(f"--> {ticker_symbol}: Saved {new_records_count} new EOD records.")
        session.close()
    except Exception as e:
        print(f"--> ERROR processing {ticker_symbol}: {e}")

# --- CLOUD FUNCTION ENTRY POINT ---
def run_fmp_eod_logger(event, context):
    """Cloud Function to get EOD data for a full list of tickers, triggered by Pub/Sub."""
    print("FMP EOD Logger (Full List, Pub/Sub) triggered.")
    try:
        if not all([DB_PASS, DB_HOST, FMP_API_KEY]): raise Exception("Required environment variables are not set.")
        engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
        Base.metadata.create_all(engine)

        config_path = Path(__file__).parent / "config" / "tickers.txt"
        with open(config_path, 'r') as f:
            tickers_to_process = [line.strip().upper() for line in f if line.strip()]

        print(f"Loaded {len(tickers_to_process)} tickers. Processing batch...")

        for ticker in tickers_to_process:
            fetch_and_save_eod_data(engine, ticker)
            time.sleep(0.5)

        print("FMP EOD Logger function finished successfully.")
    except Exception as e:
        print(f"An error occurred: {e}"); raise e