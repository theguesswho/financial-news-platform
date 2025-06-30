# functions/master_analyzer/main.py (Final, Self-Contained Version)

import os
import json
import base64
from datetime import datetime
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
import google.generativeai as genai
import functions_framework

# This import now works because the file is in the same directory
from db_models import Base, Report, EodPrice, IncomeStatement, BalanceSheet, CashFlowStatement

# --- SETTINGS & GLOBAL CONFIG ---
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_HOST = os.getenv("DB_HOST_IP")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

try:
    db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
    engine = create_engine(db_dsn)
    Session = sessionmaker(bind=engine)
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"FATAL: Could not configure globals on startup: {e}")
    engine = None; Session = None

# ... The get_briefing_document and get_ai_thesis functions remain exactly the same ...
def get_briefing_document(session, ticker, headline):
    briefing = {"ticker": ticker, "primary_news": headline}
    eod_prices = session.query(EodPrice).filter_by(ticker=ticker).order_by(desc(EodPrice.price_date)).limit(252).all()
    if eod_prices:
        latest_price = eod_prices[0]
        valid_pes = [p.pe_ratio for p in eod_prices if p.pe_ratio is not None and p.pe_ratio > 0]
        avg_pe = sum(valid_pes) / len(valid_pes) if valid_pes else 0
        briefing["valuation_context"] = f"The stock closed at ${latest_price.close_price:.2f} with a P/E ratio of {latest_price.pe_ratio:.2f}. The 12-month average P/E is {avg_pe:.2f}."
    else: briefing["valuation_context"] = "No EOD price data available."
    financials = {"revenue": [], "net_income": [], "gross_profit_ratio": [], "total_debt": [], "free_cash_flow": []}
    income_stmts = session.query(IncomeStatement).filter_by(ticker=ticker, period='quarter').order_by(desc(IncomeStatement.date)).limit(8).all()
    balance_sheets = session.query(BalanceSheet).filter_by(ticker=ticker, period='quarter').order_by(desc(BalanceSheet.date)).limit(8).all()
    cash_flows = session.query(CashFlowStatement).filter_by(ticker=ticker, period='quarter').order_by(desc(CashFlowStatement.date)).limit(8).all()
    for stmt in reversed(income_stmts):
        financials["revenue"].append(f"{stmt.date}: ${stmt.revenue/1000000:.2f}M"); financials["net_income"].append(f"{stmt.date}: ${stmt.net_income/1000000:.2f}M"); financials["gross_profit_ratio"].append(f"{stmt.date}: {stmt.gross_profit_ratio*100:.2f}%")
    for stmt in reversed(balance_sheets):
        financials["total_debt"].append(f"{stmt.date}: ${stmt.total_debt/1000000:.2f}M")
    for stmt in reversed(cash_flows):
        financials["free_cash_flow"].append(f"{stmt.date}: ${stmt.free_cash_flow/1000000:.2f}M")
    briefing["financial_snapshot"] = json.dumps(financials, indent=2)
    return briefing

def get_ai_thesis(briefing_document):
    prompt = f"""
    You are a value investing analyst trained in the philosophies of Peter Lynch and Joel Greenblatt. Analyze the provided briefing document and write a concise, 3-sentence thesis for your portfolio manager.

    **Briefing Document:**
    * **Primary News:** {briefing_document['primary_news']}
    * **Valuation Context:** {briefing_document['valuation_context']}
    * **Financial Snapshot (last 8qtrs):** {briefing_document['financial_snapshot']}
    ---
    **Final Thesis (Your 3-sentence output):**
    """
    model = genai.GenerativeModel('gemini-1.5-flash'); response = model.generate_content(prompt)
    return response.text

@functions_framework.cloud_event
def master_analyzer(cloud_event):
    if not Session:
        print("CRITICAL: Database session not available. Exiting."); return

    session = Session()
    try:
        message_data = json.loads(base64.b64decode(cloud_event.data['message']['data']).decode('utf-8'))
        ticker = message_data.get("ticker")
        headline = message_data.get("headline", "No headline provided.")
        url = message_data.get("url", f"event_{cloud_event.data['message']['message_id']}")

        if not ticker: raise Exception("Message is missing 'ticker'.")

        print(f"Analyzing '{headline}' for ticker: {ticker}")
        briefing_document = get_briefing_document(session, ticker, headline)
        ai_thesis = get_ai_thesis(briefing_document)

        new_report = Report(source_url=url, ai_thesis={'thesis': ai_thesis}, briefing_document=briefing_document, created_at=datetime.utcnow())
        session.add(new_report); session.commit()
        print(f"\nSUCCESS: Final report for {ticker} saved to database.")
    except Exception as e:
        print(f"An error occurred in Master Analyzer: {e}"); session.rollback()
    finally:
        session.close()