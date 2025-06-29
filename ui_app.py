# ui_app.py (Final Version with Auth Proxy)

import streamlit as st
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON
import os
from datetime import datetime

# --- DATABASE SCHEMA DEFINITION ---
Base = declarative_base()
class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True, index=True)
    filing_url = Column(String, unique=True)
    ai_analysis = Column(JSON)
    market_context = Column(JSON)
    created_at = Column(DateTime)

# --- DATABASE CONNECTION for LOCAL DEVELOPMENT with Auth Proxy ---
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = "127.0.0.1" # Connect to the proxy on localhost
DB_PORT = "5432"    # The proxy listens on the default postgres port

@st.cache_resource
def get_db_engine():
    """Creates a database engine that connects to the local Auth Proxy."""
    if not DB_PASS:
        st.error("DB_PASSWORD environment variable is not set.")
        return None
    db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    try:
        engine = create_engine(db_dsn)
        connection = engine.connect()
        connection.close()
        return engine
    except Exception as e:
        st.error(f"Failed to connect to the database via proxy. Is the proxy running? Error: {e}")
        return None

# --- UI LAYOUT ---
st.set_page_config(layout="wide", page_title="Financial Intelligence")
st.title("🤖 Objective Intelligence Platform")

engine = get_db_engine()
if engine:
    Session = sessionmaker(bind=engine)
    session = Session()
    latest_report = session.query(Report).order_by(Report.created_at.desc()).first()
    session.close()
    if latest_report:
        st.header("Latest Intelligence Report", divider="rainbow")
        ai_analysis_data = latest_report.ai_analysis
        ai_snippet = ai_analysis_data.get('snippet', 'Analysis snippet not found.')
        st.markdown(f"> {ai_snippet}")
        st.caption(f"Source: {latest_report.filing_url}")
        st.caption(f"Generated at: {latest_report.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    else:
        st.info("No reports found yet. The autonomous system is running.")
else:
    st.error("Could not create database engine.")