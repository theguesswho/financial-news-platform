"""
Daily Intelligence Brief — synthesises all signals into a curated brief.

Reads the hidden-gems leaderboard, qual assessments, tier changes, recent
8-Ks, and insider trades, then asks Claude to write a concise, opinionated
brief worth reading every morning.

Cost: ~$0.01 per brief using claude-haiku. Generated once per day; the
scheduler calls get_or_generate_brief() from every daily job, so a missed
run self-heals at the next one.
"""
import json
import os
from datetime import date, datetime, timedelta

import anthropic
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import DailyBrief

HAIKU = "claude-haiku-4-5-20251001"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# Data gathering — all from tables the Railway scheduler keeps fresh
# ---------------------------------------------------------------------------

def _gather_signals(session: Session) -> dict:
    # Current board with qual overlay
    board = session.execute(text("""
        SELECT lh.symbol, COALESCE(lh.assessed_tier, lh.tier) AS tier,
               lh.gem_score, qa.direction, qa.rationale
        FROM leaderboard_history lh
        LEFT JOIN qual_assessments qa ON qa.symbol = lh.symbol
        WHERE lh.date = (SELECT MAX(date) FROM leaderboard_history)
          AND lh.tier IS NOT NULL
        ORDER BY lh.gem_score DESC
    """)).fetchall()

    # Tier changes vs the previous snapshot
    tier_moves = session.execute(text("""
        SELECT t.symbol,
               COALESCE(y.assessed_tier, y.tier) AS prev_tier,
               COALESCE(t.assessed_tier, t.tier) AS new_tier,
               t.gem_score
        FROM leaderboard_history t
        LEFT JOIN leaderboard_history y
            ON y.symbol = t.symbol
            AND y.date = (SELECT MAX(date) FROM leaderboard_history
                          WHERE date < (SELECT MAX(date) FROM leaderboard_history))
        WHERE t.date = (SELECT MAX(date) FROM leaderboard_history)
          AND COALESCE(t.assessed_tier, t.tier) IS DISTINCT FROM COALESCE(y.assessed_tier, y.tier)
          AND (t.tier IS NOT NULL OR y.tier IS NOT NULL)
        ORDER BY t.gem_score DESC
    """)).fetchall()

    # Recent 8-K events (48h, widened to 7d if quiet — e.g. weekends)
    def _events(hours):
        return session.execute(text("""
            SELECT symbol, filing_date, title, llm_analysis
            FROM filings
            WHERE filing_type IN ('8-K', '8-K/A')
              AND filing_date >= :cutoff
              AND llm_analysis IS NOT NULL
            ORDER BY filing_date DESC LIMIT 15
        """), {"cutoff": datetime.utcnow() - timedelta(hours=hours)}).fetchall()

    recent_events = _events(48) or _events(24 * 7)

    # Insider cluster buys (2+ insiders, last 14 days)
    clusters = session.execute(text("""
        SELECT symbol, COUNT(*) AS cnt, SUM(total_value) AS total
        FROM insider_trades
        WHERE transaction_type = 'BUY' AND transaction_date >= :cutoff
        GROUP BY symbol HAVING COUNT(*) >= 2
        ORDER BY SUM(total_value) DESC NULLS LAST LIMIT 8
    """), {"cutoff": date.today() - timedelta(days=14)}).fetchall()

    # Notable individual buys (> USD 50k) and sells (> USD 500k)
    notable_buys = session.execute(text("""
        SELECT symbol, person_name, person_title, total_value
        FROM insider_trades
        WHERE transaction_type = 'BUY' AND transaction_date >= :cutoff
          AND total_value >= 50000
        ORDER BY total_value DESC LIMIT 10
    """), {"cutoff": date.today() - timedelta(days=14)}).fetchall()

    notable_sells = session.execute(text("""
        SELECT symbol, person_name, person_title, total_value
        FROM insider_trades
        WHERE transaction_type = 'SELL' AND transaction_date >= :cutoff
          AND total_value >= 500000
        ORDER BY total_value DESC LIMIT 5
    """), {"cutoff": date.today() - timedelta(days=14)}).fetchall()

    return {
        "board": board,
        "tier_moves": tier_moves,
        "recent_events": recent_events,
        "clusters": clusters,
        "notable_buys": notable_buys,
        "notable_sells": notable_sells,
    }


def _build_prompt(signals: dict) -> str:
    lines = []

    if signals["tier_moves"]:
        lines.append("TIER CHANGES SINCE LAST SNAPSHOT:")
        for m in signals["tier_moves"]:
            lines.append(f"  {m.symbol}: {m.prev_tier or 'off board'} -> {m.new_tier or 'off board'}"
                         f" (gem score {float(m.gem_score or 0):.3f})")

    if signals["board"]:
        lines.append("\nCURRENT HIDDEN GEMS BOARD (top 10 by gem score, with qual view):")
        for b in signals["board"][:10]:
            qual = f" | qual: {b.direction}" if b.direction else ""
            lines.append(f"  {b.symbol}: {b.tier}, score {float(b.gem_score):.3f}{qual}")
            if b.rationale:
                lines.append(f"    {str(b.rationale)[:220]}")

    if signals["recent_events"]:
        lines.append("\nRECENT 8-K MATERIAL EVENTS:")
        for e in signals["recent_events"]:
            try:
                a = json.loads(e.llm_analysis) if isinstance(e.llm_analysis, str) else (e.llm_analysis or {})
            except Exception:
                a = {}
            fdate = e.filing_date.strftime("%b %d") if e.filing_date else ""
            lines.append(f"  {e.symbol} ({fdate}): {a.get('headline', e.title)} [{a.get('impact', 'NEUTRAL')}]")
            if a.get("summary"):
                lines.append(f"    {a['summary']}")

    if signals["clusters"]:
        lines.append("\nINSIDER CLUSTER BUYING (2+ insiders, last 14 days):")
        for row in signals["clusters"]:
            val = float(row.total) if row.total else 0
            lines.append(f"  {row.symbol}: {row.cnt} insiders, USD {val:,.0f} combined")

    if signals["notable_buys"]:
        lines.append("\nNOTABLE OPEN-MARKET PURCHASES (last 14 days):")
        for t in signals["notable_buys"]:
            val = float(t.total_value) if t.total_value else 0
            lines.append(f"  {t.symbol}: {t.person_name} ({t.person_title or 'Insider'}) bought USD {val:,.0f}")

    if signals["notable_sells"]:
        lines.append("\nNOTABLE INSIDER SALES (last 14 days):")
        for t in signals["notable_sells"]:
            val = float(t.total_value) if t.total_value else 0
            lines.append(f"  {t.symbol}: {t.person_name} ({t.person_title or 'Insider'}) sold USD {val:,.0f}")

    data_str = "\n".join(lines) or "No fresh signals — likely a quiet weekend."

    return f"""You are a financial intelligence analyst writing the morning brief for the Hidden Gems research platform. The reader runs a quant+qual system that scores 505 stocks daily; your job is to tell them what changed and what deserves attention today.

Today: {date.today().strftime('%A, %B %d, %Y')}

SIGNALS (leaderboard, qual assessments, SEC filings, Form 4 insider trades):
{data_str}

Write a daily intelligence brief. Return ONLY valid JSON — no markdown fences, no extra text:

{{
  "top_signal": {{
    "symbol": "<ticker or null if no clear leader>",
    "title": "<punchy 8-12 word headline>",
    "body": "<2-3 sentences. What happened, with specific numbers. Write USD amounts as 'USD X billion' — never use dollar signs>",
    "why_it_matters": "<1-2 opinionated sentences. Don't hedge — have a view.>"
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
      "pattern": "<brief label, e.g. 'Cluster buy + tier upgrade'>",
      "detail": "<1-2 sentences on why this is interesting. No dollar signs.>",
      "watch_for": "<specific catalyst or trigger>"
    }}
  ]
}}

Rules:
- Lead with tier changes and qual downgrades — the reader cares most about what moved on their board
- watch_list: 2-4 items max. Prioritise negative signals (bad news travels fast)
- on_radar: 2-3 items. Focus on convergence — when 2+ signals point to the same stock
- Be direct. "This is worth watching because X" not "Investors may wish to consider"
- If it's a quiet day, say so honestly but still extract the most useful signal available"""


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

    signals = _gather_signals(session)
    prompt = _build_prompt(signals)

    response = _get_client().messages.create(
        model=HAIKU,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    # Trim any prose around the JSON object
    if "{" in raw:
        raw = raw[raw.index("{"): raw.rindex("}") + 1]

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

    row = session.query(DailyBrief).filter_by(date=today).first()
    if not row:
        row = DailyBrief(date=today)
        session.add(row)
    row.content = json.dumps(brief)
    row.generated_at = datetime.utcnow()
    session.commit()

    return brief
