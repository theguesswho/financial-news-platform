# scripts/backfill_all_data.py (FINAL, DIRECT DOWNLOAD METHOD)

import os
import requests
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_schema_manager import Base, EodPrice, SecFiling, AnalystRating
from pathlib import Path
from bs4 import BeautifulSoup

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

def fetch_and_save_eod_data(session, ticker, start_date, end_date):
    """Fetches historical Price and P/E data from FMP."""
    print(f"  Fetching EOD data for {ticker}...")
    try:
        api_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}?from={start_date}&to={end_date}&apikey={FMP_API_KEY}"
        response_json = requests.get(api_url, timeout=60).json()
        
        if isinstance(response_json, dict) and 'Error Message' in response_json:
            print(f"    API Error for {ticker}: {response_json['Error Message']}")
            return

        if not response_json or 'historical' not in response_json:
            print(f"    No EOD data found for {ticker}.")
            return

        for values in response_json['historical']:
            record = EodPrice(ticker=ticker, price_date=datetime.strptime(values['date'], '%Y-%m-%d').date(), open_price=values['open'], high_price=values['high'], low_price=values['low'], close_price=values['close'], volume=values['volume'], pe_ratio=values.get('pe'))
            session.add(record)
        session.commit()
        print(f"    Saved {len(response_json['historical'])} EOD records for {ticker}.")
    except Exception as e:
        session.rollback()
        print(f"    ERROR fetching EOD data for {ticker}: {e}")

def fetch_and_save_sec_filings(session, ticker):
    """Fetches SEC filing metadata from FMP and downloads text directly from SEC."""
    print(f"  Fetching SEC filings for {ticker}...")
    try:
        api_url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker}?limit=100&apikey={FMP_API_KEY}"
        filings_response = requests.get(api_url, timeout=60).json()

        if not filings_response or isinstance(filings_response, dict) and 'Error Message' in filings_response:
            print(f"    No filings found or API error for {ticker}.")
            return
        
        count = 0
        for filing in filings_response:
            if filing['type'] not in ['8-K', '10-K', '10-Q']:
                continue

            # --- THIS IS THE NEW DIRECT DOWNLOAD LOGIC ---
            filing_text = "Text not available."
            try:
                sec_url = filing.get('finalLink')
                if sec_url:
                    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'}
                    page_response = requests.get(sec_url, headers=headers, timeout=30)
                    page_response.raise_for_status() # Will raise an error for bad status codes
                    
                    soup = BeautifulSoup(page_response.content, 'html.parser')
                    filing_text = soup.get_text(separator='\n', strip=True)
                    print(f"    Successfully downloaded text for {sec_url}")
                else:
                    print(f"    No 'finalLink' found for a filing.")

            except Exception as text_e:
                print(f"    ERROR directly downloading text for {filing.get('finalLink', 'Unknown URL')}: {text_e}")

            record = SecFiling(ticker=ticker, form_type=filing['type'], filed_at=datetime.strptime(filing['fillingDate'], '%Y-%m-%d %H:%M:%S'), filing_url=filing['finalLink'], filing_text=filing_text)
            session.add(record)
            count += 1
            time.sleep(0.5)

        if count > 0:
            session.commit()
            print(f"    Saved {count} filing records for {ticker}.")

    except Exception as e:
        session.rollback()
        print(f"    ERROR processing filings for {ticker}: {e}")

def run_backfill():
    """Main function to run the entire backfill process."""
    if not FMP_API_KEY or not DB_PASS:
        print("Error: FMP_API_KEY and DB_PASSWORD environment variables must be set.")
        return

    session = Session()
    print("--- Wiping existing data to ensure a clean slate ---")
    try:
        session.execute(SecFiling.__table__.delete())
        session.execute(EodPrice.__table__.delete())
        session.commit()
        print("--- Existing data wiped successfully ---")
    except Exception as e:
        print(f"--- Error wiping data: {e} ---")
        session.rollback()
        session.close()
        return

    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    script_dir = Path(__file__).parent
    tickers_path = script_dir.parent / "config" / "tickers.txt"
    with open(tickers_path, 'r') as f:
        tickers = [line.strip() for line in f if line.strip()]

    print(f"--- Starting 5-Year Data Backfill for {len(tickers)} Tickers ---")
    
    # Let's just process the first ticker to confirm the new logic
    for i, ticker in enumerate(tickers[:1]): 
        print(f"\nProcessing Ticker {i+1}/1: {ticker} (Final Test Run)")
        
        fetch_and_save_eod_data(session, ticker, start_date_str, end_date_str)
        time.sleep(1) 
        
        fetch_and_save_sec_filings(session, ticker)
        time.sleep(1) 

    session.close()
    print("\n--- Final Test Run Complete ---")
    print("If this run was successful, remove the '[:1]' to process all tickers.")

if __name__ == "__main__":
    run_backfill()