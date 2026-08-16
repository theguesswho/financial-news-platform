"""GET /stocks/{symbol} — the dossier behind one board row.

Ports the queries of ui/pages/5_Stock_Detail.py: latest snapshot scores
(single source of truth: leaderboard_history, never a live re-score),
score + band history, qual assessment, fundamentals, the annual
fundamentals road (triptych raw material), earnings calls, SEC filings,
forward-looking claims, per-person-per-day insider decisions, prices,
theme alignments, and theme-relative valuation gaps.
"""
import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from api.deps import get_engine, ten
from pipeline.tiers import tier_for

router = APIRouter()


def _json_list(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (ValueError, TypeError):
        return [str(val)]


def _rows(conn, sql, **params):
    return conn.execute(text(sql), params).fetchall()


@router.get("/stocks/{symbol}")
def get_stock(symbol: str):
    symbol = symbol.upper()
    engine = get_engine()
    with engine.connect() as conn:
        snap = conn.execute(text("""
            SELECT lh.gem_score, lh.narrative_score, lh.value_score,
                   lh.quality_score, lh.gap_score, lh.priced_in, lh.ng_score,
                   COALESCE(lh.assessed_tier, lh.tier), lh.final_rank,
                   lh.date, f.sector, f.industry, f.company_name
            FROM leaderboard_history lh
            LEFT JOIN fundamentals f ON f.symbol = lh.symbol
            WHERE lh.date = (SELECT MAX(date) FROM leaderboard_history)
              AND lh.symbol = :s
        """), {"s": symbol}).fetchone()
        if snap is None:
            raise HTTPException(404, f"{symbol} is not in the covered universe")

        qa = conn.execute(text("""
            SELECT gem_score, raw_tier, adjusted_tier, direction,
                   rationale, key_bull, key_bear, assessed_at
            FROM qual_assessments WHERE symbol = :s
        """), {"s": symbol}).fetchone()

        fund = conn.execute(text("""
            SELECT peg_ratio, pe_forward, pe_trailing, revenue_growth_yoy,
                   earnings_growth_yoy, roic, gross_margin, operating_margin,
                   net_margin, fcf_margin, debt_to_equity, market_cap,
                   fifty_two_week_high, fifty_two_week_low, price_vs_52w_high,
                   analyst_rating, analyst_target_price, analysts_count
            FROM fundamentals WHERE symbol = :s
        """), {"s": symbol}).fetchone()

        # The 10y road: annual rows for the triptych's history pane
        annuals = _rows(conn, """
            SELECT fiscal_year AS period_end, revenue, gross_margin,
                   op_margin, net_margin, fcf, roic
            FROM fundamentals_annual
            WHERE symbol = :s
            ORDER BY fiscal_year DESC LIMIT 10""", s=symbol)

        # Score + band history — every date carries the FINAL tier, so the
        # band-transition memory rule is satisfiable from this one series.
        history = _rows(conn, """
            SELECT date, gem_score, narrative_score, value_score,
                   quality_score, gap_score, COALESCE(assessed_tier, tier),
                   final_rank
            FROM leaderboard_history WHERE symbol = :s ORDER BY date""",
            s=symbol)

        calls = _rows(conn, """
            SELECT f.filing_date, ft.narrative_strength, ft.trajectory,
                   ft.management_tone, ft.raw_themes, ft.catalysts, ft.risks
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :s AND f.filing_type = 'EARN_CALL'
            ORDER BY f.filing_date DESC LIMIT 6""", s=symbol)

        filings = _rows(conn, """
            SELECT f.filing_date, f.filing_type, ft.narrative_strength,
                   ft.trajectory, ft.management_tone, ft.raw_themes,
                   ft.catalysts, ft.risks, f.url
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :s AND f.filing_type IN ('10-K','10-Q')
            ORDER BY f.filing_date DESC LIMIT 4""", s=symbol)

        filing_events = _rows(conn, """
            SELECT filing_date::date, filing_type, title FROM filings
            WHERE symbol = :s AND filing_date >= NOW() - INTERVAL '8 months'
            ORDER BY filing_date""", s=symbol)

        claims = _rows(conn, """
            SELECT claim_type, claim_text, confidence, call_date, direction
            FROM earnings_claims
            WHERE symbol = :s AND confidence >= 0.75
            ORDER BY call_date DESC, confidence DESC LIMIT 12""", s=symbol)

        # One executive's day is ONE decision, not 40 10b5-1 lot rows
        # (Kurtz/CRWD 2026-08-04); entity filers excluded.
        trades = _rows(conn, """
            SELECT person_name, MIN(person_title), transaction_date,
                   transaction_type, SUM(shares),
                   ROUND(SUM(COALESCE(total_value,0)) / NULLIF(SUM(shares),0), 2),
                   SUM(total_value)
            FROM insider_trades
            WHERE symbol = :s
              AND transaction_type IN ('BUY','SELL')
              AND NOT (UPPER(person_name) ~ '(L\\.P|LLC|FUND|PARTNERS|CAPITAL|HOLDINGS|TRUST|MANAGEMENT|SPV| L P|LP$)')
            GROUP BY person_name, transaction_date, transaction_type
            ORDER BY transaction_date DESC LIMIT 30""", s=symbol)

        prices = _rows(conn, """
            SELECT date, close FROM eod_prices
            WHERE symbol = :s ORDER BY date""", s=symbol)

        # The narrative brain's own link table, keyed by narrative_id —
        # this is what the company page pairs stories with. The
        # theme_alignments below are the LEGACY meta-themes system
        # (frozen since 2026-07-12, retired at the NARRATIVE_SPEC Phase 2
        # gate); never pair a company to a force by matching their names.
        exposures = _rows(conn, """
            SELECT ne.narrative_id, n.name, n.tier, COALESCE(n.scope,''),
                   n.parent_id, p.name, ne.exposure, ne.direction,
                   ne.linkage, ne.status, ne.misses, ne.decays,
                   ne.first_seen, ne.last_confirmed
            FROM narrative_exposures ne
            JOIN narratives n ON n.id = ne.narrative_id
            LEFT JOIN narratives p ON p.id = n.parent_id
            WHERE ne.symbol = :s AND n.status != 'merged'
            ORDER BY ne.exposure DESC NULLS LAST""", s=symbol)

        themes = _rows(conn, """
            SELECT mt.name, sta.alignment_score, sta.trajectory
            FROM stock_theme_alignment sta
            JOIN meta_themes mt ON mt.id = sta.meta_theme_id
            WHERE sta.symbol = :s
            ORDER BY sta.alignment_score DESC LIMIT 8""", s=symbol)

        # theme_valuation_gaps.meta_theme_id is a LEGACY COLUMN NAME holding
        # a narrative_id — verified in pipeline/theme_valuation_gap.py, which
        # writes it from narrative_exposures.narrative_id (and confirmed in
        # data: all 15 distinct id/name pairs match narratives, none match
        # meta_themes). It crosses the API under its true name so surfaces
        # can link a peer set to its force by id, never by name.
        gaps = _rows(conn, """
            SELECT theme_name, alignment_score, peer_count,
                   stock_pe_fwd, peer_median_pe, pe_discount,
                   stock_ev_ebitda, peer_median_ev, ev_discount,
                   meta_theme_id
            FROM theme_valuation_gaps
            WHERE symbol = :s
            ORDER BY GREATEST(COALESCE(pe_discount, -9),
                              COALESCE(ev_discount, -9)) DESC""", s=symbol)

    f = lambda v: float(v) if v is not None else None
    return {
        "symbol": symbol,
        "company": snap[12],
        "sector": snap[10],
        "industry": snap[11],
        "as_of": snap[9],
        "score": ten(snap[0]),
        "tier": snap[7],
        "quant_tier": tier_for(float(snap[0])),
        "final_rank": snap[8],
        "components": {
            "exposure": ten(snap[1]), "value": ten(snap[2]),
            "quality": ten(snap[3]), "gap": ten(snap[4]),
        },
        "priced_in": f(snap[5]),
        "ng_score": f(snap[6]),
        "assessment": qa and {
            "score_at_assessment": ten(qa[0]),
            "raw_tier": qa[1], "adjusted_tier": qa[2], "direction": qa[3],
            "rationale": qa[4], "key_bull": qa[5], "key_bear": qa[6],
            "assessed_at": qa[7],
        },
        "fundamentals": fund and {
            "peg_ratio": f(fund[0]), "pe_forward": f(fund[1]),
            "pe_trailing": f(fund[2]), "revenue_growth_yoy": f(fund[3]),
            "earnings_growth_yoy": f(fund[4]), "roic": f(fund[5]),
            "gross_margin": f(fund[6]), "operating_margin": f(fund[7]),
            "net_margin": f(fund[8]), "fcf_margin": f(fund[9]),
            "debt_to_equity": f(fund[10]), "market_cap": f(fund[11]),
            "week52_high": f(fund[12]), "week52_low": f(fund[13]),
            "price_vs_52w_high": f(fund[14]), "analyst_rating": fund[15],
            "analyst_target_price": f(fund[16]), "analysts_count": fund[17],
        },
        "annual_history": [{
            "period_end": r[0], "revenue": f(r[1]), "gross_margin": f(r[2]),
            "op_margin": f(r[3]), "net_margin": f(r[4]), "fcf": f(r[5]),
            "roic": f(r[6]),
        } for r in annuals],
        "history": [{
            "date": r[0], "score": ten(r[1]),
            "components": {"exposure": ten(r[2]), "value": ten(r[3]),
                           "quality": ten(r[4]), "gap": ten(r[5])},
            "tier": r[6], "final_rank": r[7],
        } for r in history],
        "earnings_calls": [{
            "date": r[0], "narrative_strength": f(r[1]), "trajectory": r[2],
            "management_tone": r[3], "themes": _json_list(r[4]),
            "catalysts": _json_list(r[5]), "risks": _json_list(r[6]),
        } for r in calls],
        "filings": [{
            "date": r[0], "type": r[1], "narrative_strength": f(r[2]),
            "trajectory": r[3], "management_tone": r[4],
            "themes": _json_list(r[5]), "catalysts": _json_list(r[6]),
            "risks": _json_list(r[7]), "url": r[8],
        } for r in filings],
        "filing_events": [{"date": r[0], "type": r[1], "title": r[2]}
                          for r in filing_events],
        "claims": [{
            "type": r[0], "text": r[1], "confidence": f(r[2]),
            "call_date": r[3], "direction": r[4],
        } for r in claims],
        "insider_trades": [{
            "person": r[0], "title": r[1], "date": r[2], "type": r[3],
            "shares": f(r[4]), "avg_price": f(r[5]), "total_value": f(r[6]),
        } for r in trades],
        "prices": [{"date": r[0], "close": f(r[1])} for r in prices],
        "exposures": [{
            "narrative_id": r[0], "name": r[1], "level": r[2],
            "scope": r[3],
            "parent": r[4] and {"id": r[4], "name": r[5]},
            "exposure": f(r[6]), "direction": r[7], "linkage": r[8],
            "status": r[9], "misses": r[10], "decays": r[11],
            "first_seen": r[12], "last_confirmed": r[13],
        } for r in exposures],
        "theme_alignments": [{
            "theme": r[0], "alignment": f(r[1]), "trajectory": r[2],
        } for r in themes],
        "valuation_gaps": [{
            "narrative_id": r[9],
            "theme": r[0], "alignment": f(r[1]), "peer_count": r[2],
            "pe_forward": f(r[3]), "peer_median_pe": f(r[4]),
            "pe_discount": f(r[5]), "ev_ebitda": f(r[6]),
            "peer_median_ev": f(r[7]), "ev_discount": f(r[8]),
        } for r in gaps],
    }
