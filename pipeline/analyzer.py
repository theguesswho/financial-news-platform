"""
Analysis pipeline: generates per-filing LLM analysis and a master synthesis
that incorporates recent price action, using Claude via the Anthropic SDK.
"""
import json
import os
from datetime import datetime, timedelta

import anthropic
from sqlalchemy.orm import Session

from db.models import EodPrice, Filing

MODEL = "claude-sonnet-4-6"
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _call_claude(system: str, user: str, cached_content: str | None = None) -> str:
    """
    Call Claude. If cached_content is provided it is sent as a cache-breakpoint
    block so repeated calls with the same large filing text hit the prompt cache.
    """
    if cached_content:
        user_blocks = [
            {
                "type": "text",
                "text": cached_content,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": user},
        ]
    else:
        user_blocks = [{"type": "text", "text": user}]

    response = _get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_blocks}],
    )
    return response.content[0].text.strip()


def _parse_json_response(text: str) -> dict:
    """Strip markdown fences if present, then parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
    return json.loads(text.rstrip("`").strip())


# ---------------------------------------------------------------------------
# Step 1: per-filing structured analysis
# ---------------------------------------------------------------------------

def _analyze_filing(filing: Filing) -> dict:
    system = "You are a senior financial analyst. Return only valid JSON with no markdown, commentary, or extra text."

    user = f"""Analyze this SEC {filing.filing_type} filing for {filing.symbol}.

Title: {filing.title}

Important: write all dollar amounts as plain numbers with "USD" or "billion/million" — do NOT use the $ symbol.

Return a JSON object with exactly these fields:
{{
  "summary": "2-3 sentence plain-English summary",
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "key_opportunities": ["opportunity 1", "opportunity 2", "opportunity 3"],
  "financial_health": "1-2 sentence assessment of financial condition",
  "sentiment_score": <integer -10 (very bearish) to 10 (very bullish)>
}}"""

    raw = _call_claude(system=system, user=user, cached_content=filing.content)
    try:
        return _parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return {
            "summary": raw,
            "key_risks": [],
            "key_opportunities": [],
            "financial_health": "",
            "sentiment_score": 0,
        }


# ---------------------------------------------------------------------------
# Step 2: master synthesis with market context
# ---------------------------------------------------------------------------

def _master_analysis(session: Session, filing: Filing, per_filing: dict) -> tuple[str, int]:
    cutoff = filing.filing_date.date() - timedelta(days=45) if filing.filing_date else None
    prices = []
    if cutoff:
        prices = (
            session.query(EodPrice)
            .filter(EodPrice.symbol == filing.symbol, EodPrice.date >= cutoff)
            .order_by(EodPrice.date.desc())
            .limit(45)
            .all()
        )

    price_str = (
        "\n".join(f"  {p.date}: ${float(p.close):.2f}" for p in prices)
        if prices
        else "  No recent price data available."
    )

    system = "You are a senior equity analyst writing concise, actionable investment briefs for institutional clients. Write all dollar amounts as plain numbers with 'billion'/'million' — never use the $ symbol."

    user = f"""Write an investment brief for {filing.symbol} based on their recent {filing.filing_type}.

Filing Analysis:
- Summary: {per_filing.get('summary', '')}
- Key Risks: {', '.join(per_filing.get('key_risks', []))}
- Key Opportunities: {', '.join(per_filing.get('key_opportunities', []))}
- Financial Health: {per_filing.get('financial_health', '')}

Recent Stock Prices (last 45 days, newest first):
{price_str}

Write 3-4 paragraphs covering:
1. What this filing reveals about the company's trajectory
2. How recent price action aligns with or diverges from the filing's content
3. Key catalysts or risks to watch over the next quarter
4. Overall investment stance

End with exactly this line (replace X with your integer score):
Sentiment Score: X"""

    text = _call_claude(system=system, user=user)

    sentiment = per_filing.get("sentiment_score", 0)
    for line in reversed(text.splitlines()):
        if "sentiment score:" in line.lower():
            try:
                raw_score = line.lower().split("sentiment score:")[1].strip().split()[0]
                sentiment = max(-10, min(10, int(raw_score)))
            except (ValueError, IndexError):
                pass
            break

    return text, sentiment


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_analysis(session: Session, symbols: list[str] | None = None) -> dict:
    """Analyze filings that have content but no analysis yet.
    Pass symbols to restrict to a specific set of tickers."""
    q = session.query(Filing).filter(
        Filing.content.isnot(None),
        Filing.content != "",
        Filing.llm_analysis.is_(None),
    )
    if symbols:
        q = q.filter(Filing.symbol.in_(symbols))
    unanalyzed = q.order_by(Filing.filing_date.desc()).all()

    if not unanalyzed:
        print("No filings pending analysis.")
        return {"analyzed": 0}

    print(f"Analyzing {len(unanalyzed)} filing(s)...")
    analyzed = 0

    for filing in unanalyzed:
        try:
            print(f"  [analyze] {filing.symbol}: {filing.title}")

            per_filing = _analyze_filing(filing)
            filing.llm_analysis = json.dumps(per_filing)

            master_text, sentiment = _master_analysis(session, filing, per_filing)
            filing.master_analysis = master_text
            filing.sentiment_score = sentiment
            filing.processed_at = datetime.utcnow()

            session.commit()
            analyzed += 1
            print(f"    → sentiment {sentiment:+d}")

        except Exception as exc:
            print(f"  [analyze] {filing.symbol} error: {exc}")
            session.rollback()

    return {"analyzed": analyzed}
