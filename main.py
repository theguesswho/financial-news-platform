# main.py (Final Public IP Version for Deployment)
import os
import feedparser
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
import time

# --- DATABASE CONNECTION SETTINGS ---
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = "postgres"
DB_HOST = os.getenv("DB_HOST_IP")

# --- DATABASE SCHEMA DEFINITION ---
Base = declarative_base()
class Article(Base):
    __tablename__ = 'articles'
    id = Column(Integer, primary_key=True); title = Column(String); link = Column(String, unique=True, nullable=False); published_date = Column(DateTime); source = Column(String); created_at = Column(DateTime, default=datetime.utcnow)

# --- SCRIPT LOGIC ---
def save_articles_from_feed(engine, feed_url, source_name):
    print(f"Fetching news from: {source_name}"); user_agent = "Mozilla/5.0..."; feed = feedparser.parse(feed_url, agent=user_agent)
    if not feed.entries: print("No articles found."); return
    Session = sessionmaker(bind=engine); session = Session()
    new_articles_count = 0
    for entry in feed.entries:
        exists = session.query(Article).filter_by(link=entry.link).first()
        if not exists:
            new_articles_count += 1; published = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            new_article = Article(title=entry.title, link=entry.link, published_date=published, source=source_name)
            session.add(new_article)
    if new_articles_count > 0: session.commit(); print(f"Saved {new_articles_count} new articles.")
    else: print("No new articles to save.")
    session.close()

# --- CLOUD FUNCTION ENTRY POINT ---
def run_rss_aggregator(request):
    """This is the entry point that Google Cloud will call for an HTTP trigger."""
    print("Cloud Function 'run_rss_aggregator' triggered.")
    try:
        if not all([DB_PASS, DB_HOST]):
            raise Exception("DB_PASSWORD and DB_HOST_IP environment variables must be set.")
        
        db_dsn = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
        engine = create_engine(db_dsn)

        Base.metadata.create_all(engine)
        
        feeds_to_process = { "BBC News": "http://feeds.bbci.co.uk/news/rss.xml" }
        for source, url in feeds_to_process.items():
            save_articles_from_feed(engine, url, source)
            
        print("RSS Aggregator function finished successfully.")
        return "OK", 200
        
    except Exception as e:
        print(f"An error occurred: {e}")
        return f"Error: {e}", 500