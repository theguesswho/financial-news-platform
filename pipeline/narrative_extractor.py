"""
Phase 1: Extract raw themes from every 10-K and 10-Q filing.

For filings that already have master_analysis  → extract from that text (fast, cheap).
For filings without master_analysis            → extract from raw content.

Output per filing (stored in filing_themes table):
  raw_themes         — list of raw theme strings in the company's own language
  trajectory         — accelerating / stable / decelerating
  narrative_strength — 0.0–1.0 (how clearly management is signalling a direction)
  management_tone    — confident / cautious / defensive
  catalysts          — specific future drivers
  risks              — what could break the thesis
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from anthropic import Anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(override=True)

MODEL = "claude-haiku-4-5-20251001"   # Fast + cheap for structured extraction
MAX_RETRIES = 3
MAX_WORKERS = 20  # Parallel API calls — Haiku handles high concurrency well
MAX_CONTENT_CHARS = 48_000  # ~12k tokens — Haiku handles 200k tokens, send full filing in one call


def get_engine():
    if os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
        from sqlalchemy import create_engine
        return create_engine(url, pool_pre_ping=True)
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}/{name}", pool_pre_ping=True)


EXTRACTION_PROMPT = """You are analysing a company SEC filing to extract narrative themes.

Extract the following as JSON. Be specific and concrete — use the company's actual language and context, not generic labels.

{{
  "raw_themes": [
    "3–8 specific themes this company is focused on, in their own words/context",
    "e.g. 'AI-driven drug discovery pipeline acceleration' not just 'AI'"
  ],
  "trajectory": "accelerating | stable | decelerating",
  "narrative_strength": 0.0–1.0 (how clearly is management signalling a strategic direction?),
  "management_tone": "confident | cautious | defensive",
  "catalysts": [
    "specific near-term drivers that could move the stock"
  ],
  "risks": [
    "specific risks management is highlighting"
  ]
}}

Return ONLY valid JSON. No explanation, no markdown fences.

FILING ({symbol} — {filing_type} — {filing_date}):
{text}"""


def extract_themes_from_filing(client, symbol, filing_type, filing_date, text_content):
    """
    Call Claude to extract structured themes from a filing.

    Sends the full document in ONE API call (Haiku supports 200k tokens;
    a typical filing/transcript is 8-15k tokens). This is 4× faster than
    the previous chunked approach and has fewer failure points.
    """
    # For very long documents, take samples from beginning, middle, and end
    # to ensure full coverage without exceeding context limits
    total_len = len(text_content)
    if total_len <= MAX_CONTENT_CHARS:
        text = text_content.strip()
    else:
        # Take first 40%, middle 20%, last 40% — covers exec summary, body, outlook
        a = int(MAX_CONTENT_CHARS * 0.40)
        b = int(MAX_CONTENT_CHARS * 0.20)
        c = int(MAX_CONTENT_CHARS * 0.40)
        mid_start = (total_len // 2) - (b // 2)
        text = (
            text_content[:a] +
            "\n\n[...]\n\n" +
            text_content[mid_start:mid_start + b] +
            "\n\n[...]\n\n" +
            text_content[total_len - c:]
        ).strip()

    prompt = EXTRACTION_PROMPT.format(
        symbol=symbol,
        filing_type=filing_type,
        filing_date=str(filing_date)[:10] if filing_date else "unknown",
        text=text,
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
                timeout=45,  # never hang a worker indefinitely
            )
            raw = response.content[0].text.strip()

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]

            result = json.loads(raw)

            if "raw_themes" not in result:
                raise ValueError("Missing raw_themes")

            return {
                "raw_themes":         result.get("raw_themes", [])[:12],
                "trajectory":         result.get("trajectory", "stable"),
                "narrative_strength": round(float(result.get("narrative_strength", 0.5)), 3),
                "management_tone":    result.get("management_tone", "cautious"),
                "catalysts":          result.get("catalysts", [])[:6],
                "risks":              result.get("risks", [])[:6],
            }

        except (json.JSONDecodeError, ValueError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)

        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    return None


def get_unprocessed_filings(engine, limit=None):
    """Get all 10-K/10-Q filings not yet in filing_themes."""
    query = """
        SELECT f.id, f.symbol, f.filing_type, f.filing_date,
               COALESCE(f.master_analysis, f.content) as text_content
        FROM filings f
        LEFT JOIN filing_themes ft ON ft.filing_id = f.id
        WHERE f.filing_type IN ('10-K', '10-Q', 'EARN_CALL')
          AND ft.id IS NULL
          AND (f.master_analysis IS NOT NULL OR f.content IS NOT NULL)
        ORDER BY f.filing_date DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    with engine.connect() as conn:
        result = conn.execute(text(query))
        return result.fetchall()


def store_themes(engine, filing_id, symbol, filing_type, filing_date, themes):
    """Store extracted themes in filing_themes table."""
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO filing_themes
                (filing_id, symbol, filing_type, filing_date,
                 raw_themes, trajectory, narrative_strength,
                 management_tone, catalysts, risks)
            VALUES
                (:filing_id, :symbol, :filing_type, :filing_date,
                 :raw_themes, :trajectory, :narrative_strength,
                 :management_tone, :catalysts, :risks)
            ON CONFLICT (filing_id) DO UPDATE SET
                raw_themes         = EXCLUDED.raw_themes,
                trajectory         = EXCLUDED.trajectory,
                narrative_strength = EXCLUDED.narrative_strength,
                management_tone    = EXCLUDED.management_tone,
                catalysts          = EXCLUDED.catalysts,
                risks              = EXCLUDED.risks,
                extracted_at       = NOW()
        """), {
            "filing_id":          filing_id,
            "symbol":             symbol,
            "filing_type":        filing_type,
            "filing_date":        filing_date,
            "raw_themes":         json.dumps(themes.get("raw_themes", [])),
            "trajectory":         themes.get("trajectory", "stable"),
            "narrative_strength": themes.get("narrative_strength", 0.5),
            "management_tone":    themes.get("management_tone", "cautious"),
            "catalysts":          json.dumps(themes.get("catalysts", [])),
            "risks":              json.dumps(themes.get("risks", [])),
        })
        conn.commit()


def run_extraction(limit=None):
    """
    Main entry point. Extract themes from all unprocessed 10-K/10-Q filings.
    Uses parallel workers for speed.
    """
    engine = get_engine()

    print("=" * 70)
    print("PHASE 1 — RAW THEME EXTRACTION (parallel)")
    print("=" * 70)

    filings = get_unprocessed_filings(engine, limit=limit)
    total = len(filings)

    if total == 0:
        print("✅ All filings already processed")
        return

    print(f"📋 {total} filings to process | {MAX_WORKERS} parallel workers\n")

    success = 0
    failed = 0
    completed = 0
    start = time.time()
    lock = Lock()

    def process_one(row):
        """Process a single filing — each worker gets its own Anthropic client."""
        filing_id, symbol, filing_type, filing_date, text_content = row
        if not text_content:
            return False, symbol, filing_type

        client = Anthropic()
        themes = extract_themes_from_filing(
            client, symbol, filing_type, filing_date, text_content
        )
        if themes:
            store_themes(engine, filing_id, symbol, filing_type, filing_date, themes)
            return True, symbol, filing_type
        return False, symbol, filing_type

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, row): row for row in filings}

        for future in as_completed(futures):
            ok, symbol, filing_type = future.result()

            with lock:
                completed += 1
                if ok:
                    success += 1
                else:
                    failed += 1

                if completed % 20 == 0 or completed == total:
                    elapsed = time.time() - start
                    rate = completed / elapsed
                    remaining = (total - completed) / rate if rate > 0 else 0
                    print(f"  [{completed:4d}/{total}] ✓{success} ✗{failed} | "
                          f"~{remaining/60:.0f}m remaining")

    elapsed = time.time() - start
    print(f"\n{'='*70}")
    print(f"✅ Complete: {success} extracted, {failed} failed — {elapsed/60:.1f} min")
    print(f"{'='*70}")


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_extraction(limit=limit)
