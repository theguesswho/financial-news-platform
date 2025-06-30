# functions/rss_aggregator/main.py (FINAL - Full Feed List)

import os, requests, feedparser, sqlalchemy, time, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, date
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
    name_to_ticker = {v.lower(): k for k, v in company_map.items()}
    company_names = list(company_map.values())
    prompt = f"""
    You are an expert financial entity recognition service. Your sole task is to determine if a news headline is directly and primarily about one of the specific companies from the provided list.

    Analyze the following headline:
    "{headline}"

    Now, consider this specific list of companies:
    {', '.join(company_names)}

    Is the headline PRIMARILY about one of those companies?
    - If yes, respond with ONLY the official company name from the list that is the main subject.
    - If the headline mentions a company but only in a minor context (e.g., "analyst at JP Morgan says..."), or if it's about general market trends, or if no company from the list is mentioned, respond with "N/A".
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt, generation_config={"response_mime_type": "text/plain"})
        found_name = response.text.strip().lower()
        if found_name in name_to_ticker:
            return [name_to_ticker[found_name]]
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
        
        # --- THIS IS THE PATH FIX ---
        script_dir = Path(__file__).parent
        map_path = script_dir.parent.parent / "config" / "company_map.json"
        
        with open(map_path, 'r') as f:
            company_map = json.load(f)
        
        # --- THIS IS THE URL FIX ---
        feeds_to_process = {
            "MarketWatch Top Stories": "http://www.marketwatch.com/rss/topstories",
            "Seeking Alpha Market Currents": "https://seekingalpha.com/market_currents.xml",
            "Zacks Press Releases": "https://scr.zacks.com/distribution/rss-feeds/default.aspx",
            "BBC News Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
            "CNBC Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html" # New reliable feed
        }
        
        for source, url in feeds_to_process.items():
            print(f"\nFetching news from: {source}...")
            try:
                # Add a user-agent header to look like a real browser
                headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'}
                response = requests.get(url, headers=headers, timeout=20)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if not feed.entries: continue
                for entry in feed.entries:
                    if not session.query(Article).filter_by(link=entry.link).first():
                        published = datetime.utcnow();
                        try: 
                            published_struct = entry.get('published_parsed', time.gmtime())
                            published = datetime.fromtimestamp(time.mktime(published_struct))
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