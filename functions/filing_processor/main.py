# functions/filing_processor/main.py

import os, base64, json, sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON, Date, Numeric, BigInteger
from datetime import datetime, date

# Import the AI analyzer logic
from ai_analyzer import analyze_text_with_gemini
from exhibit_extractor import extract_press_release

# --- SETTINGS & SCHEMA ---
DB_USER="postgres"; DB_PASS=os.getenv("DB_PASSWORD"); DB_NAME="postgres"; DB_HOST=os.getenv("DB_HOST_IP")
Base = declarative_base()

# We need to define the tables this function will interact with
class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    filing_url = Column(String, unique=True)
    ai_analysis = Column(JSON)
    market_context = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class EodPrice(Base):
    __tablename__ = 'eod_prices'
    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    price_date = Column(Date, nullable=False)
    close_price = Column(Numeric(10, 4))
    # Add other fields if you need them for context
    
# --- CLOUD FUNCTION ENTRY POINT ---
def process_analysis_request(event, context):
    """
    Triggered by a Pub/Sub message, this function fetches market data,
    gets the primary text, and synthesizes a report.
    """
    print(f"Master Analyzer triggered by messageId: {context.event_id}")
    try:
        engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
        Session = sessionmaker(bind=engine)
        session = Session()

        message_data = json.loads(base64.b64decode(event['data']).decode('utf-8'))
        event_type = message_data.get("eventType")
        ticker = message_data.get("ticker")

        if not ticker: raise Exception("Message is missing 'ticker'.")

        print(f"Processing '{event_type}' event for ticker: {ticker}")

        # --- FETCHING REAL MARKET CONTEXT ---
        market_context_text = "No recent market data found."
        latest_price_record = session.query(EodPrice).filter_by(ticker=ticker).order_by(EodPrice.price_date.desc()).first()
        
        if latest_price_record:
            market_context_text = f"The most recent end-of-day stock price for {ticker} was ${latest_price_record.close_price:.2f} on {latest_price_record.price_date.strftime('%Y-%m-%d')}."

        # The primary text for the AI depends on the event type
        primary_text = ""
        if event_type == "SIGNIFICANT_NEWS":
            primary_text = message_data.get('headline', 'News headline was not provided.')
        elif event_type == "SEC_FILING":
            # Assuming you have a way to get filing text, like the exhibit extractor
            primary_text = extract_press_release(message_data.get('url'))
            if not primary_text:
                primary_text = f"A new {message_data.get('form', 'filing')} was submitted, but the press release text could not be extracted."

        report_url = message_data.get("url", f"event_{context.event_id}")

        # Call the AI with the primary text and the REAL market context
        ai_snippet = analyze_text_with_gemini(primary_text, market_context_text)

        # Save the final report
        if not session.query(Report).filter_by(filing_url=report_url).first():
            final_report = Report(
                filing_url=report_url, 
                ai_analysis={'snippet': ai_snippet}, 
                market_context={'text': market_context_text, 'ticker': ticker}, 
                created_at=datetime.utcnow()
            )
            session.add(final_report)
            session.commit()
            print(f"SUCCESS: Final report for {ticker} saved to database.")

        session.close()

    except Exception as e:
        print(f"An error occurred in Master Analyzer: {e}"); raise e