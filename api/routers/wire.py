"""GET /wire, /wire/{date} — the News Wire: earnings/filings feed only.

Read-only port of the Streamlit reference (ui/pages/6_News_Wire.py
load_filings_intelligence, FIXPACK_2026-08-19 B1): noteworthy narrative
filings (strength >= 0.60 or a shift >= 0.12) from the last 14 days,
plus high-impact 8-Ks (|sentiment| >= 2) from the last 7 days, merged
newest-first, capped at 14. Board moves and insiders are NOT here —
board moves are What changed's content; insiders stay off.

Boundary rules: synopses come ONLY from the stored llm_analysis cache —
this endpoint never generates one (read endpoints never write; the
machinery does the writing). narrative_strength crosses on the 10-point
scale via ten(). Dates are the observed filing dates, date-only.
Board tier/score chips resolve through the shared
pipeline.board_membership resolver — live for the latest view, the
requested date's own snapshot for archive views (a dated page must
never wear today's board).
"""
import json
from datetime import date as date_t, datetime, time, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from api.deps import get_engine, ten
from pipeline.board_membership import board_membership

router = APIRouter()

TYPE_LABELS = {
    "EARN_CALL": "Earnings call",
    "10-K": "10-K annual report",
    "10-Q": "10-Q quarterly report",
    "8-K": "8-K event",
    "8-K/A": "8-K event (amended)",
}


def _parse_analysis(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _clean(s):
    return s.lstrip("# ").strip() if s else None


def _items(conn, end: datetime):
    cutoff = end - timedelta(days=14)
    cutoff8k = end - timedelta(days=7)

    rows = conn.execute(text("""
        WITH ranked AS (
            SELECT f.id, f.symbol, f.filing_type, f.filing_date, f.title,
                   f.llm_analysis,
                   ft.narrative_strength, ft.trajectory, ft.management_tone,
                   LAG(ft.narrative_strength) OVER (
                       PARTITION BY f.symbol ORDER BY f.filing_date
                   ) AS prev_narrative
            FROM filings f
            JOIN filing_themes ft ON ft.filing_id = f.id
            WHERE f.filing_date >= :cutoff AND f.filing_date <= :end
              AND ft.narrative_strength IS NOT NULL
        )
        SELECT id, symbol, filing_type, filing_date, title, llm_analysis,
               narrative_strength, trajectory, management_tone,
               COALESCE(narrative_strength - prev_narrative, 0) AS delta
        FROM ranked
        WHERE narrative_strength >= 0.60
           OR ABS(COALESCE(narrative_strength - prev_narrative, 0)) >= 0.12
        ORDER BY filing_date DESC, narrative_strength DESC
        LIMIT 12
    """), {"cutoff": cutoff, "end": end}).fetchall()

    eightks = conn.execute(text("""
        SELECT id, symbol, filing_type, filing_date, title, llm_analysis,
               sentiment_score
        FROM filings
        WHERE filing_type IN ('8-K', '8-K/A')
          AND filing_date >= :cutoff8k AND filing_date <= :end
          AND llm_analysis IS NOT NULL
          AND ABS(COALESCE(sentiment_score, 0)) >= 2
        ORDER BY filing_date DESC, ABS(sentiment_score) DESC
        LIMIT 8
    """), {"cutoff8k": cutoff8k, "end": end}).fetchall()

    items = []
    for (fid, sym, ftype, fdate, title, raw, strength, trajectory,
         tone, delta) in rows:
        ana = _parse_analysis(raw)
        items.append({
            "id": fid,
            "symbol": sym,
            "type": ftype,
            "type_label": TYPE_LABELS.get(ftype, ftype),
            "date": fdate.date().isoformat() if fdate else None,
            "headline": title,
            # cached synopsis only; None when the machinery hasn't
            # written one yet (the UI falls back to the headline)
            "synopsis": _clean(ana.get("synopsis")),
            "signal": ten(strength),
            "signal_delta": ten(delta) if abs(delta or 0) >= 0.05 else None,
            "trajectory": trajectory,
            "tone": tone,
            "impact": None,
        })
    for fid, sym, ftype, fdate, title, raw, _sent in eightks:
        ana = _parse_analysis(raw)
        impact = ana.get("impact")
        items.append({
            "id": fid,
            "symbol": sym,
            "type": ftype,
            "type_label": TYPE_LABELS.get(ftype, ftype),
            "date": fdate.date().isoformat() if fdate else None,
            "headline": ana.get("headline") or title,
            "synopsis": _clean(ana.get("summary")),
            "signal": None,
            "signal_delta": None,
            "trajectory": None,
            "tone": None,
            "impact": impact.title() if isinstance(impact, str) else None,
        })

    items.sort(key=lambda i: (i["date"] or "", i["signal"] or 0),
               reverse=True)
    return items[:14]


def _wire(for_date: date_t | None):
    engine = get_engine()
    with engine.connect() as conn:
        dates = [r[0].isoformat() for r in conn.execute(text("""
            SELECT DISTINCT d FROM (
                WITH ranked AS (
                    SELECT f.filing_date, ft.narrative_strength,
                           LAG(ft.narrative_strength) OVER (
                               PARTITION BY f.symbol ORDER BY f.filing_date
                           ) AS prev
                    FROM filings f
                    JOIN filing_themes ft ON ft.filing_id = f.id
                    WHERE f.filing_date >= :d45
                      AND ft.narrative_strength IS NOT NULL
                )
                SELECT filing_date::date AS d FROM ranked
                WHERE narrative_strength >= 0.60
                   OR ABS(COALESCE(narrative_strength - prev, 0)) >= 0.12
                UNION
                SELECT filing_date::date AS d FROM filings
                WHERE filing_type IN ('8-K', '8-K/A')
                  AND filing_date >= :d45
                  AND llm_analysis IS NOT NULL
                  AND ABS(COALESCE(sentiment_score, 0)) >= 2
            ) q ORDER BY d DESC LIMIT 30
        """), {"d45": datetime.utcnow() - timedelta(days=45)}).fetchall()]

        end = (datetime.combine(for_date, time.max) if for_date
               else datetime.utcnow())
        items = _items(conn, end)
        if for_date is not None and not items:
            raise HTTPException(404, f"No wire items on or before {for_date}")

        names = dict(conn.execute(text(
            "SELECT symbol, company_name FROM fundamentals "
            "WHERE company_name IS NOT NULL")).fetchall())
        membership = board_membership(conn, as_of=for_date)

    for it in items:
        it["company"] = names.get(it["symbol"])
        it["board"] = membership.get(it["symbol"])  # {'tier','score'} | None

    return {
        "date": (for_date or (date_t.fromisoformat(items[0]["date"])
                              if items and items[0]["date"]
                              else datetime.utcnow().date())).isoformat(),
        "is_latest": for_date is None,
        "dates": dates,
        "items": items,
    }


@router.get("/wire")
def latest_wire():
    return _wire(None)


@router.get("/wire/{d}")
def wire_by_date(d: date_t):
    return _wire(d)
