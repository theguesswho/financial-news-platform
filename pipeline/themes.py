"""
Theme extraction pipeline.

Reads existing 10-K/10-Q AI analysis and asks Claude to:
  1. Identify which macro themes the company is exposed to
  2. Assess whether that exposure is growing, stable, or declining
  3. Note any specific catalysts mentioned in the filing

Themes are stored in the Fundamentals table as JSON.

Cost: ~$0.001 per company (Haiku on short summary text, not raw filing).
"""
import json
import os
import time
from datetime import datetime

import anthropic
from sqlalchemy import desc
from sqlalchemy.orm import Session

from db.models import Filing, Fundamentals

HAIKU = "claude-haiku-4-5-20251001"

# Predefined taxonomy — keeps classification consistent across companies.
# Claude can also suggest additional themes but must map to these first.
THEME_TAXONOMY = [
    "AI_INFRASTRUCTURE",      # servers, networking, data centres, GPUs
    "AI_SOFTWARE",            # models, SaaS AI tools, AI-native applications
    "CLOUD_COMPUTING",        # hyperscalers, cloud services, IaaS/PaaS
    "SEMICONDUCTORS",         # chips, fab, EDA, materials
    "ENERGY_TRANSITION",      # renewables, storage, grid, EVs
    "NUCLEAR_POWER",          # uranium, reactor builders, power generation
    "DEFENCE_AEROSPACE",      # military spend, drones, space
    "HEALTHCARE_INNOVATION",  # GLP-1, genomics, medtech, biotech
    "FINANCIAL_SERVICES",     # fintech disruption, payments, banking
    "RESHORING_MANUFACTURING",# supply chain repatriation, industrials
    "COMMODITIES_SUPERCYCLE", # copper, lithium, gold, oil
    "CONSUMER_STAPLES",       # defensive, brand moats
    "REAL_ESTATE_DATA",       # data centre REITs, cell towers
    "CYBERSECURITY",          # identity, endpoint, network security
    "AUTONOMOUS_VEHICLES",    # self-driving, LIDAR, fleet software
]

_client: anthropic.Anthropic | None = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _extract_themes(symbol: str, filing_summary: str, company_name: str = "") -> dict:
    """
    Ask Haiku to classify this company against the theme taxonomy.
    Returns structured dict.
    """
    taxonomy_str = "\n".join(f"  - {t}" for t in THEME_TAXONOMY)

    prompt = f"""You are a thematic equity analyst. Based on this summary of {symbol}'s ({company_name}) SEC filing, identify which macro investment themes this company is exposed to.

Filing summary:
{filing_summary[:3000]}

Available themes:
{taxonomy_str}

Return ONLY valid JSON:
{{
  "primary_themes": ["<theme1>", "<theme2>"],
  "secondary_themes": ["<theme3>"],
  "exposure_trend": "<GROWING|STABLE|DECLINING>",
  "catalyst": "<one sentence: the specific thing making this company interesting in the context of these themes, or null>",
  "second_order_note": "<one sentence: what macro trend drives these themes, and why this company benefits — the insight a smart investor would make, or null>"
}}

Rules:
- primary_themes: 1-2 themes where the company has direct, material revenue exposure
- secondary_themes: 0-2 themes with indirect or emerging exposure
- Only use themes from the list above
- exposure_trend: is exposure to these themes growing, stable, or declining?
- Be specific in catalyst — not generic ("benefits from AI growth") but precise ("70% of new server orders are AI-configured")
- Return empty lists if no clear theme exposure"""

    response = _get_client().messages.create(
        model=HAIKU,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip().strip("`").lstrip("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "primary_themes": [],
            "secondary_themes": [],
            "exposure_trend": "STABLE",
            "catalyst": None,
            "second_order_note": None,
        }


def run_theme_extraction(session: Session) -> dict:
    """
    For every company that has a 10-K/10-Q analysis in the DB,
    extract themes and store in the Fundamentals row.
    Skips companies already tagged.
    """
    # Get latest 10-K or 10-Q per symbol that has AI analysis
    from sqlalchemy import func
    subq = (
        session.query(
            Filing.symbol,
            func.max(Filing.filing_date).label("max_date")
        )
        .filter(
            Filing.filing_type.in_(["10-K", "10-Q"]),
            Filing.llm_analysis.isnot(None),
        )
        .group_by(Filing.symbol)
        .subquery()
    )

    filings = (
        session.query(Filing)
        .join(subq, (Filing.symbol == subq.c.symbol) & (Filing.filing_date == subq.c.max_date))
        .all()
    )

    done = 0
    skipped = 0

    for filing in filings:
        # Check if already tagged
        fund = session.query(Fundamentals).filter_by(symbol=filing.symbol).first()
        if fund and fund.quarterly_trends:  # use quarterly_trends as proxy for "has data"
            existing = json.loads(fund.quarterly_trends) if fund.quarterly_trends else {}
            if existing.get("_themes_extracted"):
                skipped += 1
                continue

        # Build summary from llm_analysis
        try:
            analysis = json.loads(filing.llm_analysis)
            summary_parts = []
            if analysis.get("summary"):
                summary_parts.append(analysis["summary"])
            if analysis.get("key_opportunities"):
                summary_parts.append("Key opportunities: " + "; ".join(analysis["key_opportunities"]))
            if analysis.get("financial_health"):
                summary_parts.append(analysis["financial_health"])
            summary = " ".join(summary_parts)
        except Exception:
            summary = filing.llm_analysis[:1000] if filing.llm_analysis else ""

        if not summary.strip():
            continue

        print(f"  [themes] {filing.symbol}...", end=" ", flush=True)
        themes = _extract_themes(filing.symbol, summary)

        # Store in Fundamentals
        if not fund:
            fund = Fundamentals(symbol=filing.symbol)
            session.add(fund)

        # Merge into quarterly_trends JSON (reuse existing field to avoid schema change)
        trends = {}
        if fund.quarterly_trends:
            try:
                trends = json.loads(fund.quarterly_trends)
            except Exception:
                pass

        trends["_themes"] = themes
        trends["_themes_extracted"] = True
        fund.quarterly_trends = json.dumps(trends)
        session.commit()

        primary = themes.get("primary_themes", [])
        trend = themes.get("exposure_trend", "")
        print(f"{', '.join(primary) or 'no themes'} [{trend}]")
        done += 1
        time.sleep(0.1)

    print(f"\nTheme extraction done: {done} tagged, {skipped} skipped.")
    return {"done": done, "skipped": skipped}


def get_themes(session: Session, symbol: str) -> dict:
    """Return extracted themes for a symbol."""
    fund = session.query(Fundamentals).filter_by(symbol=symbol).first()
    if not fund or not fund.quarterly_trends:
        return {}
    try:
        data = json.loads(fund.quarterly_trends)
        return data.get("_themes", {})
    except Exception:
        return {}


def run_theme_extraction_from_screener(session: Session) -> dict:
    """
    Fast theme extraction using screener one-liners (instead of full filings).
    For each stock, uses the AI-generated summary to classify macro themes.
    Much cheaper than filing analysis (short text → Haiku).
    Cost: ~$0.0005 per stock × ~400 stocks = ~$0.20 total.
    """
    from db.models import ScreenerResult
    from sqlalchemy import func

    # Find stocks without themes yet
    tagged = set()
    for fund in session.query(Fundamentals.symbol, Fundamentals.quarterly_trends).all():
        if fund.quarterly_trends:
            try:
                data = json.loads(fund.quarterly_trends)
                if data.get("_themes"):
                    tagged.add(fund.symbol)
            except Exception:
                pass

    # Get screener results for untagged stocks
    untagged = (
        session.query(ScreenerResult)
        .filter(~ScreenerResult.symbol.in_(tagged))
        .all()
    )

    if not untagged:
        return {"extracted": 0, "skipped": len(tagged)}

    print(f"\nExtracting themes for {len(untagged)} stocks (using screener summaries)...")
    print(f"Estimated cost: ~${len(untagged) * 0.0005:.2f}\n")

    extracted = 0
    errors = 0

    for i, sr in enumerate(untagged, 1):
        try:
            print(f"  [{i}/{len(untagged)}] {sr.symbol}...", end=" ", flush=True)

            # Use one_liner for theme extraction (very cheap)
            if not sr.one_liner or len(sr.one_liner) < 10:
                print("no summary")
                continue

            prompt = f"""Extract macro themes for {sr.symbol} from this summary:

"{sr.one_liner}"

Available themes: {', '.join(THEME_TAXONOMY)}

Return ONLY a JSON object (no markdown, no extra text):
{{
  "primary_themes": ["THEME1", "THEME2"],
  "secondary_themes": ["THEME3"],
  "exposure_trend": "GROWING|STABLE|DECLINING",
  "catalyst": "specific reason this matters",
  "second_order_note": "optional related insight"
}}

Guidelines:
- primary_themes: 1-2 themes with direct revenue impact
- secondary_themes: 0-2 themes with indirect impact
- Only use themes from the list
- Keep catalyst specific and brief
- Return empty lists if no clear theme match"""

            response = _get_client().messages.create(
                model=HAIKU,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip().strip("`").lstrip("json").strip()
            themes_data = json.loads(raw)

            # Store in Fundamentals.quarterly_trends
            fund = session.query(Fundamentals).filter_by(symbol=sr.symbol).first()
            if fund:
                existing = {}
                if fund.quarterly_trends:
                    try:
                        existing = json.loads(fund.quarterly_trends)
                    except Exception:
                        pass

                existing["_themes"] = themes_data
                existing["_themes_extracted"] = datetime.utcnow().isoformat()
                fund.quarterly_trends = json.dumps(existing)
                session.commit()

            extracted += 1
            primary = ", ".join(themes_data.get("primary_themes", [])[:2])
            print(f"✓ {primary or '—'}")
            time.sleep(0.05)  # polite to API

        except Exception as exc:
            errors += 1
            print(f"error: {exc}")
            session.rollback()

    print(f"\nTheme extraction complete: {extracted} extracted, {errors} errors, {len(tagged)} already tagged.")
    return {"extracted": extracted, "errors": errors, "skipped": len(tagged)}


def get_companies_by_theme(session: Session, theme: str) -> list[dict]:
    """Return all companies tagged with a given theme, with their fundamentals."""
    funds = session.query(Fundamentals).all()
    results = []
    for f in funds:
        if not f.quarterly_trends:
            continue
        try:
            data = json.loads(f.quarterly_trends)
            themes_data = data.get("_themes", {})
        except Exception:
            continue

        all_themes = (
            themes_data.get("primary_themes", []) +
            themes_data.get("secondary_themes", [])
        )
        if theme.upper() not in [t.upper() for t in all_themes]:
            continue

        results.append({
            "symbol": f.symbol,
            "primary": theme in themes_data.get("primary_themes", []),
            "exposure_trend": themes_data.get("exposure_trend"),
            "catalyst": themes_data.get("catalyst"),
            "second_order_note": themes_data.get("second_order_note"),
            "pe": float(f.pe_trailing) if f.pe_trailing else None,
            "peg": float(f.peg_ratio) if f.peg_ratio else None,
            "revenue_growth": float(f.revenue_growth_yoy) if f.revenue_growth_yoy else None,
            "roic": float(f.roic) if f.roic else None,
            "gross_margin": float(f.gross_margin) if f.gross_margin else None,
        })

    return sorted(results, key=lambda x: (x["primary"] is False, x["pe"] or 999))
