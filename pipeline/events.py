"""
8-K material events pipeline.

8-Ks are filed for: earnings results, M&A, CEO/CFO changes, guidance updates,
restructurings, and other material events. They typically hit EDGAR hours before
the news cycle picks them up.

Uses Claude Haiku for classification + summarisation (cheap — 8-Ks are short).
"""
import json
import os
import time
from datetime import datetime, timedelta

import anthropic
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from db.models import Filing
from pipeline.ingestion import (
    EDGAR_HEADERS,
    _build_cik_map,
    _scrape_filing_content,
)

THIN_CONTENT_THRESHOLD = 5000  # chars — below this, try to fetch EX-99 exhibit


def _has_figures(text_: str) -> bool:
    """
    A real earnings summary cites FINANCIAL figures — percentages, dollar
    magnitudes, per-share numbers. Bare digits don't count: dates ("July 14,
    2026") appear in vacuous cover-page summaries too.
    """
    import re
    return bool(re.search(
        r"\d+(\.\d+)?\s*(%|percent|billion|million|bn\b|mm\b|[BMK]\b)"
        r"|[$€£]\s?\d"
        r"|\d+(\.\d+)?\s*(per share|eps)"
        r"|\d+(\.\d+)?x\b",
        text_ or "", re.IGNORECASE))


def _is_earnings(classification: dict, items: str) -> bool:
    """Earnings by LLM classification or by SEC item 2.02 (results of operations)."""
    return classification.get("event_type") == "EARNINGS" or "2.02" in (items or "")


def _fetch_exhibit_content(filing_url: str) -> str:
    """Fetch the EX-99 exhibit for cover-only 8-Ks that reference an attached press release."""
    try:
        base = filing_url.rsplit("/", 1)[0]
        folder = base.split("/")[-1]  # accession folder e.g. 000003799626000151
        # Format accession number: 000003799626000151 -> 0000037996-26-000151
        acc = f"{folder[:10]}-{folder[10:12]}-{folder[12:]}"
        index_url = f"{base}/{acc}-index.htm"
        resp = requests.get(index_url, headers=EDGAR_HEADERS, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "lxml")
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 3:
                doc_type = cells[-2].get_text(strip=True) if len(cells) > 2 else ""
                if "EX-99" in doc_type:
                    link = row.find("a", href=True)
                    if link:
                        exhibit_url = base + "/" + link["href"].split("/")[-1]
                        return _scrape_filing_content(exhibit_url)
    except Exception:
        pass
    return ""

HAIKU = "claude-haiku-4-5-20251001"
LOOKBACK_DAYS = 90
MAX_8K_CHARS = 15_000  # 8-Ks are short; this captures the full text

EVENT_TYPES = ["EARNINGS", "M&A", "EXEC_CHANGE", "GUIDANCE", "RESTRUCTURING", "LEGAL", "OTHER"]

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# EDGAR helpers
# ---------------------------------------------------------------------------

def _get_recent_8ks(cik: str, lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    recent = data.get("filings", {}).get("recent", {})
    results = []

    for i, form in enumerate(recent.get("form", [])):
        if form not in ("8-K", "8-K/A"):
            continue
        filing_date = datetime.strptime(recent["filingDate"][i], "%Y-%m-%d")
        if filing_date < cutoff:
            break  # filings are newest-first; stop once past lookback window

        acc = recent["accessionNumber"][i]
        acc_clean = acc.replace("-", "")
        primary = recent["primaryDocument"][i]
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
            f"/{acc_clean}/{primary}"
        )
        results.append({
            "type": form,
            "date": recent["filingDate"][i],
            "url": filing_url,
            "title": f"8-K — {data.get('name', '')} ({recent['filingDate'][i]})",
            "items": recent.get("items", [""])[i] if recent.get("items") else "",
        })

    return results


# ---------------------------------------------------------------------------
# AI classification
# ---------------------------------------------------------------------------

def _classify_8k(symbol: str, content: str, items: str) -> dict:
    """Classify and summarise an 8-K using Haiku."""
    items_hint = f"SEC item numbers reported: {items}\n" if items else ""

    prompt = f"""You are a financial analyst. Classify and summarise this 8-K filing for {symbol}.

{items_hint}Filing content:
{content[:MAX_8K_CHARS]}

Rules for the summary:
- Lead with the ACTUAL news — specific numbers, names, percentages, dollar amounts
- Do NOT describe what was filed or reference the 8-K itself (e.g. never write "filed an 8-K" or "the filing discloses")
- Include concrete figures where available (e.g. "sales rose 12% YoY", "CEO John Smith resigned", "USD 2.1B acquisition")
- 2-3 sentences maximum

Return ONLY valid JSON — no markdown:
{{
  "event_type": "<one of: EARNINGS, M&A, EXEC_CHANGE, GUIDANCE, RESTRUCTURING, LEGAL, OTHER>",
  "headline": "<10-15 word headline capturing the key event>",
  "summary": "<2-3 sentence plain-English summary with specific figures, no dollar signs>",
  "impact": "<POSITIVE, NEGATIVE, or NEUTRAL>",
  "score": <integer -5 to 5>
}}"""

    response = _get_client().messages.create(
        model=HAIKU,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip().strip("`").lstrip("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "event_type": "OTHER",
            "headline": "8-K filing",
            "summary": raw[:300],
            "impact": "NEUTRAL",
            "score": 0,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_events(session: Session, tickers: list[str]) -> dict:
    """
    Fetch and analyse recent 8-K filings for all tracked tickers.
    Skips filings already in the DB.
    """
    print(f"Building CIK map for {len(tickers)} tickers...")
    cik_map = _build_cik_map(tickers)

    added = 0
    errors = 0

    for symbol, cik in cik_map.items():
        try:
            recent_8ks = _get_recent_8ks(cik)
            for f in recent_8ks:
                if session.query(Filing).filter_by(url=f["url"]).first():
                    continue

                print(f"  [8-K] {symbol}: {f['date']}...", end=" ", flush=True)
                try:
                    content = _scrape_filing_content(f["url"])
                    if len(content) < THIN_CONTENT_THRESHOLD:
                        exhibit = _fetch_exhibit_content(f["url"])
                        if exhibit:
                            content = exhibit
                except Exception as exc:
                    content = ""
                    print(f"scrape failed ({exc}), ", end="")

                classification = _classify_8k(symbol, content, f.get("items", ""))

                # Semantic exhibit trigger: an earnings 8-K whose summary has
                # no figures means we summarised a cover page (IBM 2026-07-14:
                # cover was 5,455 chars — over the size threshold — and the
                # real numbers sat in EX-99). Character count is a bad proxy
                # for "contains the news"; absence of digits is the tell.
                if (_is_earnings(classification, f.get("items", ""))
                        and not _has_figures(classification.get("summary", ""))):
                    exhibit = _fetch_exhibit_content(f["url"])
                    if exhibit and len(exhibit) > len(content):
                        content = exhibit
                        classification = _classify_8k(symbol, content, f.get("items", ""))

                session.add(Filing(
                    symbol=symbol,
                    cik=cik,
                    filing_type=f["type"],
                    event_type=classification["event_type"],
                    title=classification["headline"],
                    url=f["url"],
                    filing_date=datetime.fromisoformat(f["date"]),
                    content=content,
                    llm_analysis=json.dumps(classification),
                    sentiment_score=classification["score"],
                    processed_at=datetime.utcnow(),
                ))
                session.commit()
                added += 1
                print(f"{classification['event_type']} / {classification['impact']}")
                time.sleep(0.1)

        except Exception as exc:
            errors += 1
            print(f"  [8-K] {symbol} error: {exc}")
            session.rollback()

    print(f"\n8-K ingest complete: {added} new events, {errors} errors.")
    return {"added": added, "errors": errors}
