"""GET /narratives — the three-layer map (ui/pages/2_Themes.py port).

Layer 1: macro forces sized by rolled-up exposed board weight, colored by
momentum. Layer 2: salience-ranked cards from any level (board weight +
recent ledger change + momentum bonus — deterministic, no LLM). Layer 3:
the complete parented tree. Company-scope narratives are excluded — they
are dossier material, not map material.
"""
from fastapi import APIRouter
from sqlalchemy import text

from api.deps import get_engine, ten

router = APIRouter()

TIER_W = {"Strong Buy": 3.0, "Buy": 2.0, "Watch": 1.0}


@router.get("/narratives")
def get_narratives():
    engine = get_engine()
    with engine.connect() as conn:
        nars = conn.execute(text("""
            SELECT id, name, tier, COALESCE(scope,''), parent_id, momentum,
                   COALESCE(thesis, description), falsification
            FROM narratives
            WHERE status IN ('active', 'declining')
              AND COALESCE(scope, '') != 'company'
            ORDER BY id""")).fetchall()
        expo = conn.execute(text("""
            SELECT ne.narrative_id, ne.symbol, ne.exposure,
                   COALESCE(lh.assessed_tier, lh.tier), lh.gem_score
            FROM narrative_exposures ne
            JOIN leaderboard_history lh ON lh.symbol = ne.symbol
                AND lh.date = (SELECT MAX(date) FROM leaderboard_history)
            WHERE COALESCE(lh.assessed_tier, lh.tier) IS NOT NULL
            ORDER BY lh.gem_score DESC""")).fetchall()
        changes = dict(conn.execute(text("""
            SELECT eh.narrative_id, COUNT(*) FROM exposure_history eh
            WHERE eh.judged_at > NOW() - INTERVAL '7 days'
              AND eh.op IN ('add','strengthen','weaken','remove')
            GROUP BY eh.narrative_id""")).fetchall())

    by_id = {n[0]: n for n in nars}
    kids: dict = {}
    for n in nars:
        # macros are roots by definition — never a child
        if n[4] in by_id and n[2] != "macro":
            kids.setdefault(n[4], []).append(n[0])

    gems_by_n: dict = {}
    weight: dict = {}
    for nid, sym, ex, tier, score in expo:
        if nid not in by_id:
            continue
        gems_by_n.setdefault(nid, []).append(
            {"symbol": sym, "tier": tier, "score": ten(score)})
        weight[nid] = weight.get(nid, 0) + TIER_W.get(tier, 0) * float(ex)

    def rollup(nid):
        return weight.get(nid, 0) + sum(rollup(c) for c in kids.get(nid, []))

    def salience(nid):
        mom_bonus = 5 if (by_id[nid][5] or "") == "accelerating" else 0
        return weight.get(nid, 0) + 2 * changes.get(nid, 0) + mom_bonus

    def node(nid):
        n = by_id[nid]
        return {
            "id": nid, "name": n[1], "level": n[2], "scope": n[3],
            "momentum": n[5] or "stable",
            "weight": round(weight.get(nid, 0), 2),
            "rollup_weight": round(rollup(nid), 2),
            "board_stocks": gems_by_n.get(nid, []),
            "changes_7d": changes.get(nid, 0),
            "children": [node(c) for c in
                         sorted(kids.get(nid, []), key=lambda x: -rollup(x))],
        }

    macros = sorted((n for n in nars if n[2] == "macro"),
                    key=lambda n: -rollup(n[0]))

    ranked = sorted(nars, key=lambda n: -salience(n[0]))[:8]
    what_moved = []
    for n in ranked:
        nid = n[0]
        parent = by_id.get(n[4])
        what_moved.append({
            "id": nid, "name": n[1], "level": n[2],
            "parent": parent[1] if parent else None,
            "momentum": n[5] or "stable",
            "thesis": n[6],
            "falsification": n[7],
            "weight": round(weight.get(nid, 0), 2),
            "changes_7d": changes.get(nid, 0),
            "salience": round(salience(nid), 2),
            "top_stocks": gems_by_n.get(nid, [])[:5],
        })

    return {
        "map": [{
            "id": m[0], "name": m[1], "momentum": m[5] or "stable",
            "rollup_weight": round(rollup(m[0]), 2),
            "n_children": len(kids.get(m[0], [])),
        } for m in macros],
        "what_moved": what_moved,
        "library": [node(m[0]) for m in macros],
    }
