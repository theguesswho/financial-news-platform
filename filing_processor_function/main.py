# filing_processor_function/main.py (FINAL - FMP ARCHITECTURE)

import os, base64, json, sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime
import google.generativeai as genai

# Import the AI analyzer logic
from ai_analyzer import analyze_text_with_gemini

# --- SETTINGS & SCHEMA ---
DB_USER="postgres"; DB_PASS=os.getenv("DB_PASSWORD"); DB_NAME="postgres"; DB_HOST=os.getenv("DB_HOST_IP")
Base = declarative_base()
class Report(Base):
    __tablename__ = 'reports'; id = Column(Integer, primary_key=True); filing_url = Column(String, unique=True); ai_analysis = Column(JSON); market_context = Column(JSON); created_at = Column(DateTime, default=datetime.utcnow)

# --- CLOUD FUNCTION ENTRY POINT ---
def process_analysis_request(event, context):
    """
    Triggered by any event, this function synthesizes a report.
    """
    print(f"Master Analyzer (FMP Architecture) triggered by messageId: {context.event_id}")
    try:
        engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
        Session = sessionmaker(bind=engine); session = Session()

        message_data = json.loads(base64.b64decode(event['data']).decode('utf-8'))
        event_type = message_data.get("eventType")
        ticker = message_data.get("ticker")

        if not ticker: raise Exception(f"Message is missing 'ticker'.")

        print(f"Processing '{event_type}' event for ticker: {ticker}")

        # The primary text for the AI is now always based on the event message
        primary_text = message_data.get('headline') or f"A new {message_data.get('form', 'filing')} was submitted."
        # The market context is a placeholder for this final build
        market_context_text = "Market context placeholder."
        report_url = message_data.get("url", f"event_{context.event_id}")

        # Call the AI with the clean context
        ai_snippet = analyze_text_with_gemini(primary_text, market_context_text)

        # Save the final report
        if not session.query(Report).filter_by(filing_url=report_url).first():
            final_report = Report(filing_url=report_url, ai_analysis={'snippet': ai_snippet}, market_context={'text': market_context_text})
            session.add(final_report); session.commit()
            print(f"SUCCESS: Final report for {ticker} saved to database.")

        session.close()

    except Exception as e:
        print(f"An error occurred in Master Analyzer: {e}"); raise e