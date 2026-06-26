"""
Claim Extractor — Phase 4 of the narrative pipeline.

Reads each earnings call transcript and extracts specific forward-looking
claims that management made: revenue targets, margin guidance, segment growth
predictions, strategic pivots, and catalysts.

These claims are stored in earnings_claims with enough structure to later
check them against actual financial outcomes — forming the basis of the
believability score.

Why this matters:
- A CEO who consistently delivers on stated targets = high believability
- A CEO who talks up AI but shows falling AI-related metrics = low believability
- Believability × narrative strength = how much to trust the narrative score

Run:
  python -m pipeline.claim_extractor              # all unprocessed transcripts
  python -m pipeline.claim_extractor --symbol NVDA # single stock
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

MODEL = "claude-haiku-4-5-20251001"
MAX_WORKERS = 8
MAX_RETRIES = 3

CLAIM_PROMPT = """You are analysing an earnings call transcript to extract specific, verifiable forward-looking claims.

Focus on claims that can be checked against future financial data — not vague aspirations.

Extract up to 8 claims as a JSON array:

[
  {{
    "claim_type": "revenue_guidance | margin_guidance | segment_growth | strategic_pivot | catalyst | risk",
    "claim_text": "Exact or near-exact quote of the claim",
    "metric": "what metric this relates to (e.g. 'total_revenue', 'operating_margin', 'ai_segment_revenue', 'free_cash_flow')",
    "direction": "up | down | flat",
    "magnitude": "quantified expectation if given (e.g. '15-20% growth', '200bps expansion', 'breakeven') or null",
    "timeframe": "when they expect this (e.g. 'Q3 2025', 'full year 2026', 'next 18 months') or null",
    "confidence": 0.0-1.0
  }}
]

Confidence guide:
- 1.0 = Specific number, committed ("we guide to $4.2B revenue")
- 0.8 = Range given ("15-20% growth")
- 0.6 = Directional with timeframe ("margins will expand in H2")
- 0.4 = Directional, no timeframe ("we expect continued growth")
- 0.2 = Vague aspiration ("we remain confident in our AI opportunity")

Only include claims where something actually verifiable was said.
Return ONLY valid JSON array. No markdown, no explanation.

TRANSCRIPT ({symbol} — {call_date}):
{text}"""


def get_engine():
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}/{name}",
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
    )


def get_unprocessed_transcripts(engine, symbol=None):
    """Get EARN_CALL filings not yet in earnings_claims."""
    where = "AND f.symbol = :symbol" if symbol else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT f.id, f.symbol, f.filing_date, f.content
            FROM filings f
            LEFT JOIN earnings_claims ec ON ec.filing_id = f.id
            WHERE f.filing_type = 'EARN_CALL'
              AND f.content IS NOT NULL
              AND ec.id IS NULL
              {where}
            ORDER BY f.filing_date DESC
        """), {"symbol": symbol} if symbol else {}).fetchall()
    return rows


def extract_claims(client, symbol, call_date, content):
    """Extract forward-looking claims from a transcript."""
    # Use the middle 60% of the transcript — skips operator intro,
    # focuses on prepared remarks + analyst Q&A where guidance lives
    total = len(content)
    start = int(total * 0.10)
    end   = int(total * 0.80)
    text_slice = content[start:end][:14000]  # ~3,500 tokens — enough for all guidance

    prompt = CLAIM_PROMPT.format(
        symbol=symbol,
        call_date=str(call_date)[:10] if call_date else "unknown",
        text=text_slice,
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]
            claims = json.loads(raw)
            if isinstance(claims, list):
                return claims
        except (json.JSONDecodeError, ValueError):
            if attempt == MAX_RETRIES - 1:
                return []
            time.sleep(1)
        except Exception:
            if attempt == MAX_RETRIES - 1:
                return []
            time.sleep(2 ** attempt)
    return []


def store_claims(engine, filing_id, symbol, call_date, claims):
    """Store extracted claims in earnings_claims table."""
    if not claims:
        return 0
    stored = 0
    with engine.connect() as conn:
        for c in claims:
            if not c.get("claim_text"):
                continue
            conn.execute(text("""
                INSERT INTO earnings_claims
                    (filing_id, symbol, call_date, claim_type, claim_text,
                     metric, direction, magnitude, timeframe, confidence)
                VALUES
                    (:filing_id, :symbol, :call_date, :claim_type, :claim_text,
                     :metric, :direction, :magnitude, :timeframe, :confidence)
            """), {
                "filing_id":  filing_id,
                "symbol":     symbol,
                "call_date":  str(call_date)[:10] if call_date else None,
                "claim_type": c.get("claim_type", "catalyst")[:30],
                "claim_text": c.get("claim_text", "")[:1000],
                "metric":     (c.get("metric") or "")[:50],
                "direction":  (c.get("direction") or "")[:10],
                "magnitude":  (c.get("magnitude") or "")[:50],
                "timeframe":  (c.get("timeframe") or "")[:50],
                "confidence": float(c.get("confidence", 0.5)),
            })
            stored += 1
        conn.commit()
    return stored


def run_claim_extraction(symbol=None):
    """Main entry point."""
    engine = get_engine()
    client = Anthropic()

    print("=" * 70)
    print("CLAIM EXTRACTOR — extracting forward-looking statements")
    print("=" * 70)

    rows = get_unprocessed_transcripts(engine, symbol=symbol)
    total = len(rows)

    if total == 0:
        print("✅ All transcripts already processed")
        return

    print(f"  {total} transcripts to process\n")

    lock = Lock()
    counters = {"transcripts": 0, "claims": 0, "failed": 0}
    completed = 0
    start = time.time()

    def process_one(row):
        filing_id, sym, call_date, content = row
        claims = extract_claims(client, sym, call_date, content)
        n = store_claims(engine, filing_id, sym, call_date, claims)
        return sym, n

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, row): row for row in rows}

        for future in as_completed(futures):
            try:
                sym, n_claims = future.result()
                with lock:
                    counters["transcripts"] += 1
                    counters["claims"] += n_claims
            except Exception as e:
                with lock:
                    counters["failed"] += 1

            with lock:
                completed += 1

            if completed % 25 == 0 or completed == total:
                elapsed = time.time() - start
                rate = completed / elapsed
                remaining = (total - completed) / rate if rate > 0 else 0
                print(f"  [{completed:4d}/{total}] "
                      f"{counters['claims']} claims extracted | "
                      f"~{remaining/60:.0f}m remaining")

    print(f"\n{'='*70}")
    print(f"✅ {counters['transcripts']} transcripts → {counters['claims']} claims extracted")
    print(f"{'='*70}")

    # Quick sample
    with engine.connect() as conn:
        sample = conn.execute(text("""
            SELECT symbol, claim_type, confidence, LEFT(claim_text, 80)
            FROM earnings_claims
            ORDER BY confidence DESC, created_at DESC
            LIMIT 8
        """)).fetchall()
    print("\nHighest confidence claims extracted:")
    for r in sample:
        print(f"  {r[0]:<6} [{r[1]:<18}] conf={r[2]:.1f}  {r[3]}")


if __name__ == "__main__":
    import sys
    sym = None
    for arg in sys.argv[1:]:
        if arg.startswith("--symbol="):
            sym = arg.split("=")[1]
        elif not arg.startswith("--"):
            sym = arg
    run_claim_extraction(symbol=sym)
