"""GET /board — the current leaderboard, fully merged.

Ports the merge logic of ui/pages/1_Hidden_Gems.py: latest board snapshot
from leaderboard_history (single source of truth), qual assessments layered
on top, narrative-override promotions, movement metadata (first-ever NEW,
final-tier transitions, rank deltas vs yesterday's FINAL positions), and
the exit-hysteresis countdown state.

Scores cross this boundary on the 10-point display scale (fmt10 rule);
internal 0-1 math never leaves the API.
"""
from fastapi import APIRouter
from sqlalchemy import text

from api.deps import get_engine, ten
from pipeline.tiers import tier_for, WATCH

router = APIRouter()

TIER_ORDER = {"Strong Buy": 0, "Buy": 1, "Watch": 2}


def _load_rows(conn):
    return conn.execute(text("""
        SELECT symbol, gem_score,
               narrative_score, value_score, quality_score, gap_score,
               COALESCE(qual_promoted, FALSE), gem_adjusted, assessed_tier,
               tier, final_rank
        FROM leaderboard_history
        WHERE date = (SELECT MAX(date) FROM leaderboard_history)
    """)).fetchall()


@router.get("/board")
def get_board():
    engine = get_engine()
    with engine.connect() as conn:
        rows = _load_rows(conn)
        snap_date = conn.execute(text(
            "SELECT MAX(date) FROM leaderboard_history")).scalar()
        qual = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, adjusted_tier, direction, rationale,
                   key_bull, key_bear, assessed_at
            FROM qual_assessments""")).fetchall()}
        overrides = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, narrative_raw, narrative_adjusted, rationale,
                   evidence, key_bull, key_bear
            FROM narrative_overrides WHERE promoted""")).fetchall()}
        companies = dict(conn.execute(text(
            "SELECT symbol, company_name FROM fundamentals "
            "WHERE company_name IS NOT NULL")).fetchall())
        buffett = {r[0]: {"tier": r[1], "rationale": r[2]}
                   for r in conn.execute(text("""
            SELECT symbol, content_json->>'buffett_tier',
                   content_json->>'buffett_rationale'
            FROM deep_dives""")).fetchall() if r[1]}
        # First-EVER board appearance (V2 #11): NEW = first time on the
        # board, full stop — a veteran flapping off for a day is not new.
        first_dates = dict(conn.execute(text("""
            SELECT symbol, MIN(date) FROM leaderboard_history
            WHERE tier IS NOT NULL GROUP BY symbol""")).fetchall())
        # Yesterday's FINAL positions — movement badges compare against what
        # the reader saw yesterday, not the raw quant rank (ACM 2026-08-03).
        prev_final = {r[0]: (r[1], r[2]) for r in conn.execute(text("""
            SELECT symbol, COALESCE(assessed_tier, tier), final_rank
            FROM leaderboard_history
            WHERE date = (SELECT MAX(date) FROM leaderboard_history
                          WHERE date < (SELECT MAX(date) FROM leaderboard_history))
              AND COALESCE(assessed_tier, tier) IN ('Strong Buy','Buy','Watch')
        """)).fetchall()}

    stocks = []
    for (sym, gem, ns, vs, qs, gs, promoted, gem_adj, assessed_tier,
         raw_board_tier, final_rank) in rows:
        gem = float(gem)
        raw_tier = tier_for(gem)
        q = qual.get(sym)
        ov = overrides.get(sym) if promoted else None
        display_score = gem
        entry = {
            "symbol": sym,
            "company": companies.get(sym),
            "components": {
                "exposure": ten(ns), "value": ten(vs),
                "quality": ten(qs), "gap": ten(gs),
            },
            "assessed": False,
            "direction": "hold",
            "rationale": None,
            "key_bull": None,
            "key_bear": None,
            "qual_promoted": False,
            "buffett": buffett.get(sym),
        }
        if ov and assessed_tier in ("Strong Buy", "Buy", "Watch"):
            # Narrative-override promotion — adjusted score drives display,
            # raw score stays visible.
            entry.update(
                tier=assessed_tier, assessed=True, qual_promoted=True,
                direction="promoted", rationale=ov[3], key_bull=ov[5],
                key_bear=ov[6], evidence=ov[4],
                narrative_raw=ten(ov[1]), narrative_adjusted=ten(ov[2]))
            display_score = float(gem_adj) if gem_adj is not None else gem
        elif q and raw_tier:
            # Qual verdict applies only while the raw score still clears the
            # Watch floor; assessor's 'None' string = off board.
            adj = q[1] if q[1] in ("Strong Buy", "Buy", "Watch") else None
            entry.update(tier=adj, assessed=True, direction=q[2],
                         rationale=q[3], key_bull=q[4], key_bear=q[5])
        else:
            entry["tier"] = raw_tier
        # Disagreement computed from DATA, not the model's self-reported
        # direction (LHX 2026-08-03).
        t = entry["tier"]
        if entry["assessed"] and not entry["qual_promoted"] and t and raw_tier != t:
            entry["disagreement"] = {
                "kind": ("raised" if TIER_ORDER.get(t, 3) < TIER_ORDER.get(raw_tier, 3)
                         else "restrained"),
                "quant_tier": raw_tier,
            }
        else:
            entry["disagreement"] = None
        # Exit-hysteresis countdown: on the board (tier set) but raw score at
        # or below the Watch entry line — holding a grace seat, leaves for
        # real below BOARD_EXIT.
        entry["exit_grace"] = bool(raw_board_tier and gem <= WATCH)
        entry["score"] = ten(display_score)
        entry["score_raw"] = ten(gem)
        entry["final_rank"] = final_rank
        stocks.append(entry)

    # Display order + movement metadata vs yesterday's final board
    ranked = sorted([s for s in stocks if s["tier"]],
                    key=lambda s: (TIER_ORDER.get(s["tier"], 3), -s["score"]))
    cur_rank = {s["symbol"]: i + 1 for i, s in enumerate(ranked)}
    for s in stocks:
        sym = s["symbol"]
        rank = cur_rank.get(sym)
        s["rank"] = rank
        s["is_new"] = bool(rank and snap_date
                           and first_dates.get(sym) == snap_date)
        s["tier_move"] = None
        s["rank_change"] = None
        if rank is None:
            continue
        pf = prev_final.get(sym)
        if pf and pf[0] and s["tier"] and pf[0] != s["tier"]:
            s["tier_move"] = {
                "direction": ("up" if TIER_ORDER.get(s["tier"], 3)
                              < TIER_ORDER.get(pf[0], 3) else "down"),
                "from": pf[0], "to": s["tier"],
            }
        elif pf and pf[1] is not None and not s["is_new"]:
            s["rank_change"] = pf[1] - rank   # positive = moved up

    board = [s for s in stocks if s["tier"]]
    board.sort(key=lambda s: (TIER_ORDER.get(s["tier"], 3), -s["score"]))
    off_board = sorted((s for s in stocks if not s["tier"]),
                       key=lambda s: -s["score_raw"])
    return {
        "date": snap_date,
        "counts": {
            "strong_buy": sum(1 for s in board if s["tier"] == "Strong Buy"),
            "buy": sum(1 for s in board if s["tier"] == "Buy"),
            "watch": sum(1 for s in board if s["tier"] == "Watch"),
            "assessed": sum(1 for s in stocks if s["assessed"]),
            "new": sum(1 for s in board if s["is_new"]),
            "universe": len(stocks),
        },
        "board": board,
        "off_board": off_board,
    }


@router.get("/board/scorecard")
def get_board_scorecard():
    """Track record: weekly $1,000 Strong Buy lots vs paired SPY twins."""
    from pipeline.track_record import get_scorecard
    sc = get_scorecard(get_engine())
    return sc or {"n_lots": 0}
