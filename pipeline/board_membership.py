"""THE single definition of board membership and final tier.

Extracted from api/routers/board.py on 2026-08-19 (FIXPACK A2 / V3 #14:
daily_report's masthead ran its own bare-COALESCE membership query and
counted 36 the same morning /board showed 41). Any surface that says
"on the board" derives it from THIS module — api imports pipeline (the
allowed direction); pipeline never imports api.

Two resolution sources, one merge rule:
- live (as_of=None): today's qual_assessments + narrative_overrides
  layered on the latest snapshot — exactly what /board renders.
- dated (as_of=<date>): the snapshot's OWN stored stamps (assessed_tier,
  qual_promoted, gem_adjusted). A regenerated edition must judge with
  THAT day's assessments — the live tables have moved on, and resolving
  an 08-18 paper against them would stamp today's board onto it.
Verified 2026-08-19: both sources resolve the latest snapshot to the
identical 46-member board.
"""
from datetime import date

from sqlalchemy import text

from pipeline.tiers import tier_for

TIER_ORDER = {"Strong Buy": 0, "Buy": 1, "Watch": 2}
_TIERS = ("Strong Buy", "Buy", "Watch")


def _ten(v, dp: int = 1):
    # api.deps.ten convention (10-point display scale, None passes
    # through) — duplicated because pipeline cannot import api.
    if v is None:
        return None
    return round(float(v) * 10, dp)


def _load_rows(conn, as_of: date | None = None):
    if as_of is None:
        where = "date = (SELECT MAX(date) FROM leaderboard_history)"
    else:
        where = ("date = (SELECT MAX(date) FROM leaderboard_history "
                 "WHERE date <= :as_of)")
    return conn.execute(text(f"""
        SELECT symbol, gem_score,
               narrative_score, value_score, quality_score, gap_score,
               COALESCE(qual_promoted, FALSE), gem_adjusted, assessed_tier,
               tier, final_rank
        FROM leaderboard_history
        WHERE {where}
    """), {"as_of": as_of}).fetchall()


def _resolve_tier(row, qual, overrides):
    """THE single definition of a symbol's final tier + display score.
    Extracted 2026-08-16 (external review): the force-page roster was
    classifying on-board membership with a bare COALESCE while this
    merge (override -> qual-with-raw-floor-guard -> raw) is what /board
    actually shows — INTU/PCG/EIX appeared 'on the board' on force
    pages while absent from /board. Any surface that says 'on the
    board' derives it from THIS function, never from a parallel query."""
    (sym, gem, ns, vs, qs, gs, promoted, gem_adj, assessed_tier,
     raw_board_tier, final_rank) = row
    gem = float(gem)
    raw_tier = tier_for(gem)
    q = qual.get(sym)
    ov = overrides.get(sym) if promoted else None
    if ov and assessed_tier in _TIERS:
        tier = assessed_tier
        display = float(gem_adj) if gem_adj is not None else gem
    elif q and raw_tier:
        tier = q[1] if q[1] in _TIERS else None
        display = gem
    else:
        tier = raw_tier
        display = gem
    return tier, display, raw_tier


def effective_tier(stamp, raw_tier, promoted=False):
    """_resolve_tier's merge computed from a snapshot row's own stored
    stamp — the dated twin of the live-table resolution. The assessor
    writes 'None' (a STRING) to rule a name off the board: it resolves
    to off here and must never be printed to a reader."""
    if promoted and stamp in _TIERS:
        return stamp
    if stamp is not None and raw_tier:
        return stamp if stamp in _TIERS else None
    return raw_tier


def _stamp_resolve(row):
    (sym, gem, ns, vs, qs, gs, promoted, gem_adj, stamp,
     raw_board_tier, final_rank) = row
    gem = float(gem)
    raw_tier = tier_for(gem)
    tier = effective_tier(stamp, raw_tier, promoted)
    display = (float(gem_adj) if gem_adj is not None else gem) \
        if (promoted and stamp in _TIERS) else gem
    return tier, display, raw_tier


def board_membership(conn, as_of: date | None = None) -> dict:
    """{symbol: {'tier','score'}} for every symbol on the board — the
    shared membership set for /board, rosters, mastheads and any other
    surface. as_of=None resolves the latest snapshot against the live
    assessment tables (what /board shows); a date resolves THAT date's
    snapshot against its own stored stamps."""
    rows = _load_rows(conn, as_of)
    if as_of is None:
        qual = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, adjusted_tier, direction, rationale,
                   key_bull, key_bear, assessed_at
            FROM qual_assessments""")).fetchall()}
        overrides = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, narrative_raw, narrative_adjusted, rationale,
                   evidence, key_bull, key_bear
            FROM narrative_overrides WHERE promoted""")).fetchall()}
        resolve = lambda row: _resolve_tier(row, qual, overrides)
    else:
        resolve = _stamp_resolve
    out = {}
    for row in rows:
        tier, display, _ = resolve(row)
        if tier:
            out[row[0]] = {"tier": tier, "score": _ten(display)}
    return out
