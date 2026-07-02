"""
One-time historical backfill — run once on Railway to seed:
  - eod_prices: 7 months of daily close prices
  - historical_metrics: quarterly PE ratios (for gap score PE expansion tracking)

Run via Railway one-off: python backfill_history.py
"""
import os
import sys
import logging
from pathlib import Path
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv(override=True)

root = Path(__file__).parent
sys.path.insert(0, str(root))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

import yfinance as yf
yf.set_tz_cache_location("/tmp/yf_tz_cache")

from sqlalchemy import text
from pipeline.hidden_gem_scorer import get_engine

eng = get_engine()

with open(root / "config" / "tickers.txt") as f:
    symbols = [l.strip().upper() for l in f if l.strip()]

log.info(f"Backfilling {len(symbols)} symbols")

# ── 1. EOD Prices (7 months) ─────────────────────────────────────────────────
start = str(date.today() - timedelta(days=220))
log.info(f"Fetching prices from {start}...")

batch_size = 50
price_rows = []
for i in range(0, len(symbols), batch_size):
    batch = symbols[i:i+batch_size]
    try:
        raw = yf.download(batch, start=start, auto_adjust=True, progress=False)
        close = raw["Close"] if hasattr(raw["Close"], "columns") else raw[["Close"]]
        for sym in (close.columns if hasattr(close, "columns") else batch):
            series = close[sym] if hasattr(close, "columns") else close["Close"]
            for dt, price in series.dropna().items():
                price_rows.append({"sym": sym, "dt": dt.date(), "price": float(price)})
    except Exception as e:
        log.warning(f"Batch {i//batch_size+1} error: {e}")
    if (i // batch_size + 1) % 5 == 0:
        log.info(f"  Downloaded {i+batch_size}/{len(symbols)} symbols, {len(price_rows)} rows")

log.info(f"Inserting {len(price_rows)} price rows...")
CHUNK = 500
inserted = 0
for i in range(0, len(price_rows), CHUNK):
    chunk = price_rows[i:i+CHUNK]
    try:
        with eng.begin() as conn:
            conn.execute(text("""
                INSERT INTO eod_prices (symbol, date, close)
                VALUES (:sym, :dt, :price)
                ON CONFLICT (symbol, date) DO UPDATE SET close = EXCLUDED.close
            """), chunk)
        inserted += len(chunk)
    except Exception as e:
        log.error(f"Insert chunk error: {e}")
log.info(f"EOD prices done: {inserted} rows upserted")

# ── 2. Historical metrics (quarterly PE via yfinance) ─────────────────────────
log.info("Fetching quarterly PE ratios...")
pe_rows = []
for i, sym in enumerate(symbols):
    try:
        tk = yf.Ticker(sym)
        hist = tk.quarterly_financials
        info = tk.fast_info
        price = getattr(info, "last_price", None)
        if hist is not None and not hist.empty and price:
            for col in hist.columns[:8]:  # last 8 quarters
                try:
                    eps = hist.loc["Basic EPS", col] if "Basic EPS" in hist.index else None
                    if eps and float(eps) > 0:
                        pe = price / (float(eps) * 4)
                        if 0 < pe < 500:
                            pe_rows.append({"sym": sym, "dt": col.date(), "pe": round(pe, 2)})
                except Exception:
                    pass
    except Exception:
        pass
    if (i + 1) % 50 == 0:
        log.info(f"  PE: {i+1}/{len(symbols)} symbols, {len(pe_rows)} rows")

log.info(f"Inserting {len(pe_rows)} PE rows into historical_metrics...")
inserted_pe = 0
for row in pe_rows:
    try:
        with eng.begin() as conn:
            conn.execute(text("""
                INSERT INTO historical_metrics (symbol, date, pe_ratio)
                VALUES (:sym, :dt, :pe)
                ON CONFLICT (symbol, date) DO UPDATE SET pe_ratio = EXCLUDED.pe_ratio
            """), row)
        inserted_pe += 1
    except Exception as e:
        pass
log.info(f"Historical metrics done: {inserted_pe} rows upserted")

log.info("Backfill complete.")
