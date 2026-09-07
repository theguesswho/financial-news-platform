import sys
sys.path.insert(0, "/Users/eha/Desktop/financial-news-platform")
from dotenv import load_dotenv
load_dotenv("/Users/eha/Desktop/financial-news-platform/.env", override=True)
from pipeline.fmp_historical import fetch_historical_metrics
from db.session import get_session
syms = [l.strip().upper() for l in open("/Users/eha/Desktop/financial-news-platform/config/tickers.txt") if l.strip()]
s = get_session()
r = fetch_historical_metrics(s, syms)
s.close()
print("RESULT", r)
