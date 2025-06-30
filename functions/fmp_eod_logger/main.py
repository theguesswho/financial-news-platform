# functions/fmp_eod_logger/main.py (Final, Corrected)
import os, requests, time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# Use the single source of truth
from common.db_models import Base, EodPrice

FMP_API_KEY = os.getenv("FMP_API_KEY")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_HOST = os.getenv("DB_HOST_IP")

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
Session = sessionmaker(bind=engine)

def fetch_and_save_eod_data(session, ticker):
    try:
        api_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}?timeseries=5&apikey={FMP_API_KEY}"
        response = requests.get(api_url).json()
        if 'historical' not in response: return

        for values in response['historical']:
            # Create the record using only the columns defined in our common model
            record = EodPrice(
                ticker=ticker,
                price_date=datetime.strptime(values['date'], '%Y-%m-%d').date(),
                close_price=values.get('close'),
                volume=values.get('volume'),
                pe_ratio=values.get('pe')
            )
            session.merge(record)
        session.commit()
        print(f"  Saved/Updated EOD for {ticker}")
    except Exception as e:
        print(f"  ERROR for {ticker}: {e}")
        session.rollback()

def run_fmp_eod_logger():
    session = Session()
    from pathlib import Path
    # Note: Corrected path for local execution
    tickers_path = Path(__file__).resolve().parent.parent.parent / "config" / "tickers.txt"
    with open(tickers_path, 'r') as f: tickers = [line.strip() for line in f if line.strip()]

    for ticker in tickers[:10]: # Let's just test with the first 10
        print(f"Processing {ticker}...")
        fetch_and_save_eod_data(session, ticker)
        time.sleep(0.5)
    session.close()

if __name__ == "__main__":
    run_fmp_eod_logger()