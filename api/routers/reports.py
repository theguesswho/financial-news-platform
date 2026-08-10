"""GET /reports/latest, /reports/{date} — session-indexed daily editions.

Ports ui/report_page.py's loader: stored daily_report rows grouped into
masthead / week grid / top story / sections, board standings chips, and —
for the LATEST edition only — the live race numbers (the stored masthead
value is the 6am snapshot and drifts stale during the day; archived dates
keep their morning numbers).
"""
import json
from datetime import date as date_t

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from api.deps import get_engine

router = APIRouter()


def _standings(conn):
    rows = conn.execute(text("""
        SELECT symbol, COALESCE(assessed_tier, tier),
               ROUND(gem_score * 10, 1), COALESCE(final_rank, rank)
        FROM leaderboard_history
        WHERE date = (SELECT MAX(date) FROM leaderboard_history)
    """)).fetchall()
    return {r[0]: {"tier": r[1],
                   "score": float(r[2]) if r[2] is not None else None,
                   "rank": r[3]}
            for r in rows}


def _live_race(engine):
    try:
        from pipeline.track_record import get_scorecard
        sc = get_scorecard(engine) or {}
        return {"us_pct": sc.get("portfolio_return_pct"),
                "spy_pct": sc.get("spy_return_pct"),
                "positions": sc.get("open_lots", sc.get("n_lots"))}
    except Exception:
        return None


def _report(for_date):
    engine = get_engine()
    with engine.connect() as conn:
        dates = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT date FROM daily_report ORDER BY date DESC LIMIT 30"
        )).fetchall()]
        if not dates:
            raise HTTPException(404, "No editions stored yet")
        d = for_date if for_date in dates else dates[0]
        if for_date is not None and for_date not in dates:
            raise HTTPException(404, f"No edition for {for_date}")
        rows = conn.execute(text("""
            SELECT section, kind, symbol, headline, body, payload
            FROM daily_report WHERE date = :d ORDER BY position"""),
            {"d": d}).fetchall()
        standings = _standings(conn)

    is_latest = d == dates[0]
    live = _live_race(engine) if is_latest else None

    masthead, week, sections = None, [], []
    scoreboard, top_story = None, None
    for section, kind, symbol, headline, body, payload in rows:
        p = json.loads(payload) if payload else {}
        if section == "masthead":
            if live:
                p = {**p, **{k: v for k, v in live.items() if v is not None}}
            masthead = p
        elif section == "week_ahead":
            week.append({"kind": kind, "symbol": symbol, "payload": p})
        elif section == "scoreboard":
            if live:
                p = {**p, **{k: v for k, v in live.items() if v is not None}}
            scoreboard = p
        elif section == "top_story":
            top_story = {"kind": kind, "symbol": symbol,
                         "headline": headline, "body": body, "payload": p}
        else:
            sections.append({"section": section, "kind": kind,
                             "symbol": symbol, "headline": headline,
                             "body": body, "payload": p})

    return {
        "date": d,
        "is_latest": is_latest,
        "dates": dates,
        "masthead": masthead,
        "top_story": top_story,
        "week_ahead": week,
        "sections": sections,
        "scoreboard": scoreboard,
        "standings": standings,
    }


@router.get("/reports/latest")
def latest_report():
    return _report(None)


@router.get("/reports/{d}")
def report_by_date(d: date_t):
    return _report(d)
