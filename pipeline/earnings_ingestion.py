"""
Earnings Call Transcript Ingestion.

Fetches earnings call transcripts from FMP for all tracked symbols,
stores them in the filings table (filing_type='EARN_CALL'), then
runs Phase 1 theme extraction so they feed directly into the narrative
scoring pipeline alongside 10-K/10-Q filings.

Architecture: flat job queue — every (symbol, quarter) is its own
independent task in a single pool of 16 workers. No nested parallelism,
no pool exhaustion. Already-processed jobs are skipped automatically
so this is safe to restart at any point.

Run:
  python -m pipeline.earnings_ingestion              # last 8 quarters
  python -m pipeline.earnings_ingestion --quarters 4
  python -m pipeline.earnings_ingestion --force       # re-fetch all
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from pipeline.narrative_extractor import extract_themes_from_filing, store_themes

load_dotenv(override=True)

FMP_KEY  = os.getenv("FMP_API_KEY")
FMP_BASE = "https://financialmodelingprep.com/api"

MAX_WORKERS   = 10    # reduced to avoid Haiku rate limits stalling workers
REQUEST_DELAY = 0.10  # slightly more breathing room for FMP
DB_POOL_SIZE  = 12
DB_OVERFLOW   = 8     # total max connections = 20, well within Postgres defaults


def get_engine():
    if os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
        from sqlalchemy import create_engine
        return create_engine(url, pool_pre_ping=True)
    host     = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user     = os.getenv("DB_USER", "postgres")
    name     = os.getenv("DB_NAME", "postgres")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}/{name}",
        pool_pre_ping=True,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_OVERFLOW,
        pool_timeout=60,
    )


def get_tracked_symbols(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT symbol FROM filing_themes ORDER BY symbol"
        )).fetchall()
    return [r[0] for r in rows]


def get_available_quarters(symbol: str) -> list[dict]:
    """Return list of {quarter, year, date} from FMP for this symbol."""
    try:
        r = requests.get(
            f"{FMP_BASE}/v4/earning_call_transcript",
            params={"symbol": symbol, "apikey": FMP_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return [{"quarter": d[0], "year": d[1], "date": d[2]} for d in data]
        print(f"  [FMP] {symbol} quarter-list HTTP {r.status_code}: {r.text[:120]}", flush=True)
    except Exception as exc:
        print(f"  [FMP] {symbol} quarter-list failed: {exc}", flush=True)
    return []


def fetch_transcript(symbol: str, quarter: int, year: int) -> str | None:
    """Fetch a single transcript from FMP."""
    try:
        r = requests.get(
            f"{FMP_BASE}/v3/earning_call_transcript/{symbol}",
            params={"quarter": quarter, "year": year, "apikey": FMP_KEY},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                return data[0].get("content")
    except Exception:
        pass
    return None


def is_already_done(engine, symbol: str, quarter: int, year: int) -> bool:
    """True if transcript is in DB AND themes have been extracted."""
    url_key = f"EARN_CALL:{symbol}:Q{quarter}:{year}"
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT ft.id FROM filings f
            JOIN filing_themes ft ON ft.filing_id = f.id
            WHERE f.url = :url
            LIMIT 1
        """), {"url": url_key}).fetchone()
    return row is not None


def store_transcript(engine, symbol: str, quarter: int, year: int,
                     date_str: str, content: str) -> int:
    """Upsert transcript into filings table. Returns filing id."""
    url_key    = f"EARN_CALL:{symbol}:Q{quarter}:{year}"
    title      = f"{symbol} Q{quarter} {year} Earnings Call"
    filing_date = date_str[:10] if date_str else f"{year}-01-01"

    with engine.connect() as conn:
        row = conn.execute(text("""
            INSERT INTO filings (symbol, filing_type, title, url, filing_date, content)
            VALUES (:symbol, 'EARN_CALL', :title, :url, :date, :content)
            ON CONFLICT (url) DO UPDATE SET content = EXCLUDED.content
            RETURNING id
        """), {
            "symbol":  symbol,
            "title":   title,
            "url":     url_key,
            "date":    filing_date,
            "content": content,
        }).fetchone()
        conn.commit()
    return row[0]


def process_one_quarter(engine, client, symbol, quarter, year, date_s, force):
    """
    Process a single (symbol, quarter) job.
    Returns 'done', 'skipped', or 'failed'.
    """
    time.sleep(REQUEST_DELAY)

    if not force and is_already_done(engine, symbol, quarter, year):
        return "skipped"

    content = fetch_transcript(symbol, quarter, year)
    if not content or len(content) < 500:
        return "failed"

    filing_id = store_transcript(engine, symbol, quarter, year, date_s, content)

    themes = extract_themes_from_filing(
        client, symbol, "EARN_CALL",
        date_s[:10] if date_s else None,
        content
    )

    if themes:
        store_themes(engine, filing_id, symbol, "EARN_CALL",
                     date_s[:10] if date_s else None, themes)
        return "done"
    else:
        return "failed"


def process_symbol(engine, client, symbol, quarters, force):
    """
    Discover and process all quarters for one symbol.
    Discovery + processing in one step — no upfront batch discovery
    that could hit FMP rate limits.
    Returns (done, skipped, failed) counts.
    """
    done = skipped = failed = 0

    available = get_available_quarters(symbol)
    if not available:
        return done, skipped, failed

    sorted_q = sorted(available, key=lambda x: (x["year"], x["quarter"]), reverse=True)
    targets  = sorted_q[:quarters]

    for q in targets:
        time.sleep(REQUEST_DELAY)
        result = process_one_quarter(
            engine, client,
            symbol, q["quarter"], q["year"], q["date"],
            force
        )
        if result == "done":
            done += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    return done, skipped, failed


def run_earnings_ingestion(quarters: int = 8, force: bool = False):
    engine = get_engine()
    client = Anthropic()

    print("=" * 70)
    print(f"EARNINGS CALL INGESTION  —  last {quarters} quarters | {MAX_WORKERS} workers")
    print("=" * 70)

    symbols = get_tracked_symbols(engine)
    total   = len(symbols)
    print(f"  {total} symbols  |  up to {total * quarters} transcripts\n")

    lock = Lock()
    counters  = {"done": 0, "skipped": 0, "failed": 0}
    completed = 0
    start     = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_symbol, engine, client, sym, quarters, force): sym
            for sym in symbols
        }

        for future in as_completed(futures):
            try:
                d, s, f = future.result()
            except Exception:
                d, s, f = 0, 0, 1

            with lock:
                completed           += 1
                counters["done"]    += d
                counters["skipped"] += s
                counters["failed"]  += f

            if completed % 20 == 0 or completed == total:
                elapsed   = time.time() - start
                rate      = completed / elapsed
                remaining = (total - completed) / rate if rate > 0 else 0
                pct       = completed / total * 100
                print(f"  [{completed:4d}/{total}] {pct:.0f}%  "
                      f"✓{counters['done']} extracted  "
                      f"↷{counters['skipped']} skipped  "
                      f"✗{counters['failed']} failed  "
                      f"~{remaining/60:.0f}m left")

    elapsed = time.time() - start
    print(f"\n{'='*70}")
    print(f"✅  {counters['done']} extracted  |  "
          f"{counters['skipped']} skipped  |  "
          f"{counters['failed']} failed  |  "
          f"{elapsed/60:.1f} min total")
    print(f"{'='*70}")


if __name__ == "__main__":
    quarters = 8
    force    = False
    for arg in sys.argv[1:]:
        if arg.startswith("--quarters="):
            quarters = int(arg.split("=")[1])
        elif arg == "--force":
            force = True
        elif arg.isdigit():
            quarters = int(arg)
    run_earnings_ingestion(quarters=quarters, force=force)
