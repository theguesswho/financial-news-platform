# ui/ui_app.py

import streamlit as st
import sqlalchemy
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
import os
import json

# Add parent dir to path to import schema
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from scripts.db_schema_manager import Base, Report

# --- DATABASE CONNECTION ---
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = "127.0.0.1" 
DB_PORT = "5432"

@st.cache_resource
def get_db_engine():
    """Creates a database engine that connects to the local Auth Proxy."""
    if not DB_PASS:
        st.error("DB_PASSWORD environment variable is not set.")
        return None
    db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    try:
        engine = create_engine(db_dsn)
        Base.metadata.create_all(engine) # Ensure tables exist
        return engine
    except Exception as e:
        st.error(f"Failed to connect to the database via proxy. Is the proxy running? Error: {e}")
        return None

# --- UI LAYOUT ---
st.set_page_config(layout="wide", page_title="Financial Intelligence")
st.title("🤖 Quantitative Analyst AI")
st.write("Powered by the philosophies of Peter Lynch and Joel Greenblatt.")

engine = get_db_engine()
if engine:
    Session = sessionmaker(bind=engine)
    session = Session()
    
    st.sidebar.header("Filters")
    # You can add filters here later, e.g., by ticker

    latest_reports = session.query(Report).order_by(desc(Report.created_at)).limit(10).all()
    session.close()

    if latest_reports:
        for report in latest_reports:
            st.header(f"Analysis for: {report.briefing_document.get('ticker', 'Unknown Ticker')}", divider="rainbow")
            st.subheader("AI-Generated Thesis")
            
            thesis_data = report.ai_thesis
            if thesis_data and 'thesis' in thesis_data:
                st.markdown(f"> {thesis_data['thesis']}")
            else:
                st.markdown("> AI thesis not available.")
            
            st.caption(f"Source: {report.source_url} | Generated at: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")

            with st.expander("Show Briefing Document (Data provided to AI)"):
                st.json(report.briefing_document)
    else:
        st.info("No reports found yet. The autonomous system is running.")
else:
    st.error("Could not create database engine.")