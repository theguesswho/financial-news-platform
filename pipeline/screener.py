"""
Lightweight screener pipeline using claude-haiku for cost efficiency.

Produces one ScreenerResult per symbol: a sentiment score (-10 to +10)
and a one-sentence summary. Designed to run across all ~500 tracked tickers.

Estimated cost: ~$0.008 per ticker → ~$4 for the full S&P 500.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from sqlalchemy.orm import Session

from db.models import EodPrice, Filing, Fundamentals, ScreenerResult
from pipeline.ingestion import _build_cik_map, _get_edgar_filings, _scrape_filing_content
from pipeline.score import compute_v2_score

HAIKU = "claude-haiku-4-5-20251001"
MAX_SCREENER_CHARS = 20_000  # smaller window → cheaper + faster
CONFIG_DIR = Path(__file__).parent.parent / "config"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _load_company_names() -> dict[str, str]:
    with open(CONFIG_DIR / "company_map.json") as f:
        return json.load(f)


def _quick_score(symbol: str, filing_type: str, content: str) -> dict:
    """Ask Haiku for a score + one-liner. Returns {"score": int, "one_liner": str}."""
    prompt = f"""You are a financial analyst. Quickly assess this SEC {filing_type} filing for {symbol}.

Content (excerpt):
{content[:MAX_SCREENER_CHARS]}

Return ONLY a JSON object — no markdown, no extra text:
{{"score": <integer -10 (very bearish) to 10 (very bullish)>, "one_liner": "<single sentence summary, no dollar signs>"}}"""

    response = _get_client().messages.create(
        model=HAIKU,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Haiku occasionally wraps in fences despite instructions
        raw = raw.strip("`").lstrip("json").strip()
        return json.loads(raw)


def _latest_price_info(session: Session, symbol: str) -> tuple[float | None, float | None]:
    """Return (latest_close, pct_change_vs_prev_day)."""
    prices = (
        session.query(EodPrice)
        .filter(EodPrice.symbol == symbol)
        .order_by(EodPrice.date.desc())
        .limit(2)
        .all()
    )
    if not prices:
        return None, None
    latest = float(prices[0].close) if prices[0].close else None
    prev = float(prices[1].close) if len(prices) > 1 and prices[1].close else None
    pct = ((latest - prev) / prev * 100) if latest and prev else None
    return latest, pct


def _ensure_filing_ingested(session: Session, symbol: str, cik: str) -> Filing | None:
    """Return the most recent 10-K or 10-Q for this symbol, ingesting it if needed."""
    # Check DB first (filed within last 18 months)
    cutoff = datetime.utcnow() - timedelta(days=548)
    existing = (
        session.query(Filing)
        .filter(
            Filing.symbol == symbol,
            Filing.filing_type.in_(["10-K", "10-Q"]),
            Filing.filing_date >= cutoff,
        )
        .order_by(Filing.filing_date.desc())
        .first()
    )
    if existing:
        return existing

    # Not in DB — ingest just the latest one
    try:
        filings = _get_edgar_filings(symbol, cik, n=1)
        if not filings:
            return None
        f = filings[0]
        if session.query(Filing).filter_by(url=f["url"]).first():
            return session.query(Filing).filter_by(url=f["url"]).first()

        content = _scrape_filing_content(f["url"])
        filing = Filing(
            symbol=symbol,
            cik=cik,
            filing_type=f["type"],
            title=f["title"],
            url=f["url"],
            filing_date=datetime.fromisoformat(f["date"]),
            content=content,
        )
        session.add(filing)
        session.commit()
        time.sleep(0.15)
        return filing
    except Exception as exc:
        print(f"    ingest error: {exc}")
        session.rollback()
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def estimate_cost(n_tickers: int) -> float:
    """Rough cost estimate in USD for running the screener on n tickers."""
    tokens_per_filing = MAX_SCREENER_CHARS / 4  # ~5k tokens
    input_cost = n_tickers * tokens_per_filing * 0.80 / 1_000_000
    output_cost = n_tickers * 80 * 4.0 / 1_000_000
    return round(input_cost + output_cost, 2)


def run_screener(session: Session, tickers: list[str], force: bool = False) -> dict:
    """
    Run the lightweight screener for every ticker.

    Skips tickers that already have a ScreenerResult < 7 days old unless force=True.
    """
    company_names = _load_company_names()

    # Work out which tickers actually need updating
    fresh_cutoff = datetime.utcnow() - timedelta(days=7)
    if not force:
        existing = {
            row[0]
            for row in session.query(ScreenerResult.symbol)
            .filter(ScreenerResult.generated_at >= fresh_cutoff)
            .all()
        }
        to_process = [t for t in tickers if t not in existing]
    else:
        to_process = tickers

    if not to_process:
        print("All screener results are fresh (< 7 days). Use force=True to rerun.")
        return {"screened": 0, "skipped": len(tickers)}

    est = estimate_cost(len(to_process))
    print(f"\nScreener plan: {len(to_process)} tickers to score.")
    print(f"Estimated cost: ~${est:.2f} (using claude-haiku)")
    print(f"Skipping {len(tickers) - len(to_process)} already fresh.\n")

    if len(to_process) > 10 and sys.stdin.isatty():
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return {"screened": 0, "skipped": len(tickers)}

    # Build CIK map for tickers we need
    print("Building CIK map...")
    cik_map = _build_cik_map(to_process)

    screened = 0
    errors = 0

    for i, symbol in enumerate(to_process, 1):
        cik = cik_map.get(symbol)
        if not cik:
            print(f"  [{i}/{len(to_process)}] {symbol}: no CIK found, skipping")
            continue

        try:
            print(f"  [{i}/{len(to_process)}] {symbol}...", end=" ", flush=True)

            # Get current fundamentals (for V2 score)
            fund = session.query(Fundamentals).filter_by(symbol=symbol).first()
            if not fund:
                print("no fundamentals")
                continue

            # Compute V2 mismatch score
            v2_score = compute_v2_score(fund, session)

            # Get filing (for sentiment context)
            filing = _ensure_filing_ingested(session, symbol, cik)
            sentiment = 0
            one_liner = ""
            if filing and filing.content:
                result = _quick_score(symbol, filing.filing_type, filing.content)
                sentiment = result.get("score", 0)
                one_liner = result.get("one_liner", "")

            latest_close, pct_change = _latest_price_info(session, symbol)

            # Upsert ScreenerResult
            sr = session.query(ScreenerResult).filter_by(symbol=symbol).first()
            if not sr:
                sr = ScreenerResult(symbol=symbol)
                session.add(sr)

            sr.company_name = company_names.get(symbol, symbol)
            sr.filing_type = filing.filing_type if filing else None
            sr.filing_date = filing.filing_date if filing else None
            sr.v2_mismatch_score = float(v2_score)  # convert numpy float to Python float
            sr.sentiment_score = sentiment
            sr.one_liner = one_liner
            sr.latest_close = latest_close
            sr.price_change_pct = pct_change
            sr.generated_at = datetime.utcnow()

            session.commit()
            screened += 1
            print(f"v2={v2_score:.3f}  sentiment={sentiment:+d}")
            time.sleep(0.1)

        except Exception as exc:
            errors += 1
            print(f"error: {exc}")
            session.rollback()

    print(f"\nScreener complete: {screened} scored, {errors} errors.")
    return {"screened": screened, "errors": errors, "skipped": len(tickers) - len(to_process)}
