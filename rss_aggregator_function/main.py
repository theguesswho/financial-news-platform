# rss_aggregator_function/main.py (FINAL - Full Feed List)

import os, requests, feedparser, sqlalchemy, time, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from pathlib import Path
from google.cloud import pubsub_v1
import google.generativeai as genai

# --- SETTINGS & SCHEMA ---
DB_USER = "postgres"; DB_PASS = os.getenv("DB_PASSWORD"); DB_NAME = "postgres"; DB_HOST = os.getenv("DB_HOST_IP")
PROJECT_ID = os.getenv("PROJECT_ID"); GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANALYSIS_TOPIC_ID = "analysis-request-topic"
Base = declarative_base()
class Article(Base):
    __tablename__ = 'articles'; id = Column(Integer, primary_key=True); title = Column(String); link = Column(String, unique=True, nullable=False); published_date = Column(DateTime); source = Column(String); created_at = Column(DateTime, default=datetime.utcnow)

def get_ticker_from_headline(headline, company_map):
    if not GEMINI_API_KEY: return None
    genai.configure(api_key=GEMINI_API_KEY)
    company_names = list(company_map.values())[:200]
    prompt = f"""You are a financial entity recognition service. Your only job is to identify a company from a news headline. Read the following headline. From this list of potential companies: {', '.join(company_names)}. Which one company from the list is the primary subject of the headline? Respond with ONLY the official company name you identified. If no companies from the list are relevant, respond with "N/A"."""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash'); response = model.generate_content(prompt, generation_config={"response_mime_type": "text/plain"})
        name_to_ticker = {v: k for k, v in company_map.items()}; found_name = response.text.strip()
        if found_name in name_to_ticker: return [name_to_ticker[found_name]]
    except Exception as e:
        print(f"Gemini API call for Ticker Recognition failed: {e}")
    return None

def run_rss_aggregator(event, context):
    print("AI-Powered RSS Aggregator (Full Feeds) triggered.")
    try:
        if not all([DB_PASS, DB_HOST, PROJECT_ID, GEMINI_API_KEY]): raise Exception("Required env vars not set.")
        engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine); session = Session()
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, ANALYSIS_TOPIC_ID)
        map_path = Path(__file__).parent / "config" / "company_map.json"
        with open(map_path, 'r') as f:
            company_map = json.load(f)
        
        # --- THE CORRECT, COMPREHENSIVE LIST OF FEEDS ---
        feeds_to_process = {
            "Reuters World News": "https://www.reuters.com/pf/api/v2/content/articles/rss/world/",
            "Reuters Business": "https://www.reuters.com/pf/api/v2/content/articles/rss/business/",
            "MarketWatch Top Stories": "http://www.marketwatch.com/rss/topstories",
            "Nasdaq Original Content": "https://www.nasdaq.com/feed/nasdaq-original/rss.xml",
            "Seeking Alpha Market Currents": "https://seekingalpha.com/market_currents.xml",
            "Zacks Press Releases": "https://scr.zacks.com/distribution/rss-feeds/default.aspx",
            "BBC News Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
            "AP News Business": "https://apnews.com/hub/business.rss"
        }
        
        for source, url in feeds_to_process.items():
            print(f"\nFetching news from: {source}...")
            try:
                response = requests.get(url, headers={'User-Agent': 'FinancialNewsPlatform e.h.arghand@gmail.com'}, timeout=20); response.raise_for_status()
                feed = feedparser.parse(response.content)
                if not feed.entries: continue
                for entry in feed.entries:
                    if not session.query(Article).filter_by(link=entry.link).first():
                        published = datetime.utcnow();
                        try: published = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                        except Exception: pass
                        new_article = Article(title=entry.title, link=entry.link, published_date=published, source=source)
                        session.add(new_article); session.commit()
                        identified_tickers = get_ticker_from_headline(entry.title, company_map)
                        if identified_tickers:
                            for ticker in identified_tickers:
                                print(f"✅ Relevant article for '{ticker}': '{entry.title}'. Publishing analysis request.")
                                message = {"eventType": "SIGNIFICANT_NEWS", "headline": entry.title, "url": entry.link, "ticker": ticker}
                                publisher.publish(topic_path, json.dumps(message).encode('utf-8')).result()
            except Exception as e:
                print(f"--> ERROR processing feed {source}: {e}")
        session.close()
        print("\nRSS Aggregator function finished successfully.")
    except Exception as e:
        print(f"An error occurred: {e}"); raise e