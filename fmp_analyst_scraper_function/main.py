# fmp_analyst_scraper_function/main.py (Pub/Sub Version)

import os
import requests
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
import time
from pathlib import Path

# --- SETTINGS & SCHEMA ---
DB_USER = "postgres"; DB_PASS = os.getenv("DB_PASSWORD"); DB_NAME = "postgres"; DB_HOST = os.getenv("DB_HOST_IP"); FMP_API_KEY = os.getenv("FMP_API_KEY")
Base = declarative_base()
class AnalystRating(Base):
    __tablename__ = 'analyst_ratings'; id = Column(Integer, primary_key=True); ticker = Column(String); recommendation = Column(String); scraped_at = Column(DateTime, default=datetime.utcnow)

def get_and_save_rating(engine, ticker_symbol):
    try:
        print(f"Processing ticker: {ticker_symbol}")
        api_url = f"https://financialmodelingprep.com/api/v3/analyst-recommendations/{ticker_symbol}?apikey={FMP_API_KEY}"
        response = requests.get(api_url, timeout=15); response.raise_for_status(); data = response.json()
        if not data: print(f"--> {ticker_symbol}: No analyst data found."); return
        latest_recommendation = data[0]; consensus = latest_recommendation.get('rating')
        if consensus:
            Session = sessionmaker(bind=engine); session = Session()
            new_rating = AnalystRating(ticker=ticker_symbol, recommendation=consensus)
            session.add(new_rating); session.commit(); session.close()
            print(f"--> {ticker_symbol}: Saved latest consensus rating: '{consensus}'.")
        else:
            print(f"--> {ticker_symbol}: Consensus rating not found.")
    except Exception as e:
        print(f"--> ERROR processing {ticker_symbol}: {e}")

# --- CLOUD FUNCTION ENTRY POINT (Corrected for Pub/Sub) ---
def run_fmp_analyst_scraper(event, context):
    """Cloud Function to scrape analyst ratings, triggered by Pub/Sub."""
    print("FMP Analyst Scraper (Pub/Sub) triggered.")
    try:
        if not all([DB_PASS, DB_HOST, FMP_API_KEY]): raise Exception("Required environment variables are not set.")
        engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
        Base.metadata.create_all(engine)

        config_path = Path(__file__).parent / "config" / "tickers.txt"
        with open(config_path, 'r') as f:
            tickers_to_process = [line.strip().upper() for line in f if line.strip()]

        print(f"Loaded {len(tickers_to_process)} tickers. Starting scrape...")

        for ticker in tickers_to_process:
            get_and_save_rating(engine, ticker)
            time.sleep(0.5)

        print("Analyst Scraper function finished successfully.")
    except Exception as e:
        print(f"An error occurred: {e}"); raise e