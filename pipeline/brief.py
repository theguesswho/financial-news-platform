"""
Daily Intelligence Brief — synthesises all signals into a curated brief.

Reads recent 8-Ks, insider trades, screener scores, and watchlist activity,
then asks Claude to write a concise, opinionated brief worth reading every morning.

Cost: ~$0.01 per brief using claude-haiku. Generated once per day.
"""
import json
import os
from datetime import date, datetime, timedelta

import anthropic
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from db.models import DailyBrief, EodPrice, Filing, InsiderTrade, ScreenerResult, WatchlistEntry

HAIKU = "claude-haiku-4-5-20251001"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def _gather_signals(session: Session, watchlist: list[str]) -> dict:
    today = date.today()

    # Recent 8-K events (last 48h)
    cutoff_48h = datetime.utcnow() - timedelta(hours=48)
    recent_events = (
        session.query(Filing)
        .filter(
            Filing.filing_type.in_(["8-K", "8-K/A"]),
            Filing.filing_date >= cutoff_48h,
            Filing.llm_analysis.isnot(None),
        )
        .order_by(desc(Filing.filing_date))
        .limit(15)
        .all()
    )

    # Widen to 7 days if nothing recent
    if not recent_events:
        cutoff_7d = datetime.utcnow() - timedelta(days=7)
        recent_events = (
            session.query(Filing)
            .filter(
                Filing.filing_type.in_(["8-K", "8-K/A"]),
                Filing.filing_date >= cutoff_7d,
                Filing.llm_analysis.isnot(None),
            )
            .order_by(desc(Filing.filing_date))
            .limit(15)
            .all()
        )

    # Insider cluster buys (2+ insiders, last 14 days)
    cutoff_14d = today - timedelta(days=14)
    clusters = (
        session.query(
            InsiderTrade.symbol,
            func.count(InsiderTrade.id).label("count"),
            func.sum(InsiderTrade.total_value).label("total"),
        )
        .filter(
            InsiderTrade.transaction_type == "BUY",
            InsiderTrade.transaction_date >= cutoff_14d,
        )
        .group_by(InsiderTrade.symbol)
        .having(func.count(InsiderTrade.id) >= 2)
        .order_by(desc("total"))
        .all()
    )

    # Notable individual insider buys (last 14 days, >$50k)
    notable_buys = (
        session.query(InsiderTrade)
        .filter(
            InsiderTrade.transaction_type == "BUY",
            InsiderTrade.transaction_date >= cutoff_14d,
            InsiderTrade.total_value >= 50_000,
        )
        .order_by(desc(InsiderTrade.total_value))
        .limit(10)
        .all()
    )

    # Notable sells (>$500k — executives sell for many reasons, so high bar)
    notable_sells = (
        session.query(InsiderTrade)
        .filter(
            InsiderTrade.transaction_type == "SELL",
            InsiderTrade.transaction_date >= cutoff_14d,
            InsiderTrade.total_value >= 500_000,
        )
        .order_by(desc(InsiderTrade.total_value))
        .limit(5)
        .all()
    )

    # Top and bottom screener scores
    top = (
        session.query(ScreenerResult)
        .filter(ScreenerResult.v2_mismatch_score.isnot(None))
        .order_by(desc(ScreenerResult.v2_mismatch_score))
        .limit(5)
        .all()
    )
    bottom = (
        session.query(ScreenerResult)
        .filter(ScreenerResult.v2_mismatch_score.isnot(None))
        .order_by(ScreenerResult.v2_mismatch_score)
        .limit(3)
        .all()
    )

    # Watchlist signals
    watchlist_data = []
    for sym in watchlist:
        screener = session.query(ScreenerResult).filter_by(symbol=sym).first()
        latest_event = (
            session.query(Filing)
            .filter(Filing.symbol == sym, Filing.filing_type.in_(["8-K", "8-K/A"]))
            .order_by(desc(Filing.filing_date))
            .first()
        )
        recent_buy = (
            session.query(InsiderTrade)
            .filter(
                InsiderTrade.symbol == sym,
                InsiderTrade.transaction_type == "BUY",
                InsiderTrade.transaction_date >= today - timedelta(days=30),
            )
            .order_by(desc(InsiderTrade.total_value))
            .first()
        )
        watchlist_data.append(
            {
                "symbol": sym,
                "screener": screener,
                "latest_event": latest_event,
                "recent_buy": recent_buy,
            }
        )

    return {
        "recent_events": recent_events,
        "clusters": clusters,
        "notable_buys": notable_buys,
        "notable_sells": notable_sells,
        "top_screener": top,
        "bottom_screener": bottom,
        "watchlist_data": watchlist_data,
    }


def _build_prompt(signals: dict, watchlist: list[str]) -> str:
    lines = []

    if signals["recent_events"]:
        lines.append("RECENT 8-K MATERIAL EVENTS:")
        for e in signals["recent_events"]:
            try:
                a = json.loads(e.llm_analysis)
            except Exception:
                a = {}
            lines.append(
                f"  {e.symbol} ({e.filing_date.strftime('%b %d') if e.filing_date else ''}): "
                f"{a.get('headline', e.title)} [{a.get('impact', 'NEUTRAL')}]"
            )
            if a.get("summary"):
                lines.append(f"    {a['summary']}")

    if signals["clusters"]:
        lines.append("\nINSIDER CLUSTER BUYING (2+ insiders, last 14 days):")
        for row in signals["clusters"]:
            val = float(row.total) if row.total else 0
            lines.append(f"  {row.symbol}: {row.count} insiders, USD {val:,.0f} combined")

    if signals["notable_buys"]:
        lines.append("\nNOTABLE OPEN-MARKET PURCHASES (last 14 days):")
        for t in signals["notable_buys"]:
            val = float(t.total_value) if t.total_value else 0
            lines.append(
                f"  {t.symbol}: {t.person_name} ({t.person_title or 'Insider'})"
                f" bought USD {val:,.0f}"
            )

    if signals["notable_sells"]:
        lines.append("\nNOTABLE INSIDER SALES (last 14 days):")
        for t in signals["notable_sells"]:
            val = float(t.total_value) if t.total_value else 0
            lines.append(
                f"  {t.symbol}: {t.person_name} ({t.person_title or 'Insider'})"
                f" sold USD {val:,.0f}"
            )

    if signals["top_screener"]:
        lines.append("\nHIGHEST V2 MISMATCH SCORES (quality + value + trajectory):")
        for s in signals["top_screener"]:
            v2 = f"{float(s.v2_mismatch_score):.3f}" if s.v2_mismatch_score else "—"
            lines.append(f"  {s.symbol}: {v2} — {s.one_liner}")

    if signals["bottom_screener"]:
        lines.append("\nLOWEST V2 MISMATCH SCORES:")
        for s in signals["bottom_screener"]:
            v2 = f"{float(s.v2_mismatch_score):.3f}" if s.v2_mismatch_score else "—"
            lines.append(f"  {s.symbol}: {v2} — {s.one_liner}")

    if watchlist:
        lines.append(f"\nUSER WATCHLIST: {', '.join(watchlist)}")
        for item in signals["watchlist_data"]:
            sym = item["symbol"]
            parts = []
            if item["screener"] and item["screener"].v2_mismatch_score is not None:
                v2 = f"{float(item['screener'].v2_mismatch_score):.3f}"
                parts.append(f"v2={v2}")
            if item["latest_event"]:
                try:
                    a = json.loads(item["latest_event"].llm_analysis or "{}")
                    parts.append(f"recent 8-K: {a.get('headline', item['latest_event'].title)}")
                except Exception:
                    pass
            if item["recent_buy"]:
                val = float(item["recent_buy"].total_value or 0)
                parts.append(f"insider buy USD {val:,.0f}")
            if parts:
                lines.append(f"  {sym}: {' | '.join(parts)}")

    data_str = "\n".join(lines) or "Limited data available — only a small number of stocks have been ingested so far."

    return f"""You are a financial intelligence analyst writing a daily brief for retail investors who want an edge without paying for professional research.

Today: {date.today().strftime('%A, %B %d, %Y')}

SIGNALS FROM SEC FILINGS AND FORM 4 INSIDER TRADES:
{data_str}

Write a daily intelligence brief. Return ONLY valid JSON — no markdown fences, no extra text:

{{
  "top_signal": {{
    "symbol": "<ticker or null if no clear leader>",
    "title": "<punchy 8-12 word headline>",
    "body": "<2-3 sentences. What happened, with specific numbers. Write USD amounts as 'USD X billion' — never use dollar signs>",
    "why_it_matters": "<1-2 opinionated sentences on what a retail investor should think about this. Don't hedge — have a view.>"
  }},
  "watch_list": [
    {{
      "symbol": "<ticker>",
      "headline": "<8-12 words>",
      "detail": "<2 sentences of context. No dollar signs.>",
      "stance": "<POSITIVE|NEGATIVE|NEUTRAL>",
      "action": "<one concrete thing to watch for next>"
    }}
  ],
  "on_radar": [
    {{
      "symbol": "<ticker>",
      "pattern": "<brief label for the signal pattern, e.g. 'Cluster buy + earnings beat'>",
      "detail": "<1-2 sentences on why this is interesting. No dollar signs.>",
      "watch_for": "<specific catalyst or trigger>"
    }}
  ]
}}

Rules:
- watch_list: 2-4 items max. Prioritise watchlist stocks and negative signals (bad news travels fast)
- on_radar: 2-3 items. Focus on convergence — when 2+ signals point to the same stock
- Be direct. "This is worth watching because X" not "Investors may wish to consider"
- If data is limited, say so honestly but still extract the most useful signal available"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_or_generate_brief(session: Session, force: bool = False) -> dict:
    """
    Return today's brief from DB, or generate a fresh one.
    Pass force=True to regenerate even if one exists.
    """
    today = date.today()

    if not force:
        existing = session.query(DailyBrief).filter_by(date=today).first()
        if existing:
            return json.loads(existing.content)

    # Gather watchlist
    watchlist = [w.symbol for w in session.query(WatchlistEntry).all()]

    signals = _gather_signals(session, watchlist)
    prompt = _build_prompt(signals, watchlist)

    response = _get_client().messages.create(
        model=HAIKU,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip().strip("`").lstrip("json").strip()

    try:
        brief = json.loads(raw)
    except json.JSONDecodeError:
        brief = {
            "top_signal": {
                "symbol": None,
                "title": "Brief generation error",
                "body": raw[:300],
                "why_it_matters": "Please regenerate.",
            },
            "watch_list": [],
            "on_radar": [],
        }

    # Upsert into DB
    row = session.query(DailyBrief).filter_by(date=today).first()
    if not row:
        row = DailyBrief(date=today)
        session.add(row)
    row.content = json.dumps(brief)
    row.generated_at = datetime.utcnow()
    session.commit()

    return brief
