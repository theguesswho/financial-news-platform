"""GET /narratives — the three-layer map (ui/pages/2_Themes.py port).

Layer 1: macro forces sized by rolled-up exposed board weight, colored by
momentum. Layer 2: salience-ranked cards from any level (board weight +
recent ledger change + momentum bonus — deterministic, no LLM). Layer 3:
the complete parented tree. Company-scope narratives are excluded — they
are dossier material, not map material.
"""
from datetime import datetime, timezone

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


@router.get("/narratives/landing")
def get_narratives_landing():
    """The landing page's narrative lens (DESIGN_BRIEF.md, front door
    2026-08-10): forces / emerging / weakening, shaped for a first-time
    visitor. Weakness is drawn from the exposure LEDGER (weaken/remove
    ops, misses), never from the momentum word alone."""
    engine = get_engine()
    with engine.connect() as conn:
        nars = conn.execute(text("""
            SELECT id, name, tier, parent_id, momentum,
                   COALESCE(thesis, description), created_at, status
            FROM narratives
            WHERE status != 'merged' AND COALESCE(scope,'') != 'company'
        """)).fetchall()
        # Breadth: every company carrying exposure, board or not — raw
        # (narrative, symbol) pairs so subtree counts can dedupe symbols.
        pairs = conn.execute(text("""
            SELECT narrative_id, symbol FROM narrative_exposures""")).fetchall()
        misses_by_n = {r[0]: int(r[1] or 0) for r in conn.execute(text("""
            SELECT narrative_id, SUM(misses)
            FROM narrative_exposures GROUP BY narrative_id""")).fetchall()}
        # Board-weighted exposure (same weighting as the map).
        expo = conn.execute(text("""
            SELECT ne.narrative_id, ne.symbol, ne.exposure,
                   COALESCE(lh.assessed_tier, lh.tier), lh.gem_score
            FROM narrative_exposures ne
            JOIN leaderboard_history lh ON lh.symbol = ne.symbol
                AND lh.date = (SELECT MAX(date) FROM leaderboard_history)
            WHERE COALESCE(lh.assessed_tier, lh.tier) IS NOT NULL
            ORDER BY lh.gem_score DESC""")).fetchall()
        # The ledger, 30 days, split by direction of the operation.
        ledger = {r[0]: r[1:] for r in conn.execute(text("""
            SELECT narrative_id,
                   COUNT(*) FILTER (WHERE op IN ('add','strengthen')),
                   COUNT(*) FILTER (WHERE op = 'weaken'),
                   COUNT(*) FILTER (WHERE op = 'remove')
            FROM exposure_history
            WHERE judged_at > NOW() - INTERVAL '30 days'
            GROUP BY narrative_id""")).fetchall()}

    by_id = {n[0]: n for n in nars}
    kids: dict = {}
    for n in nars:
        if n[3] in by_id and n[2] != "macro":
            kids.setdefault(n[3], []).append(n[0])

    gems_by_n: dict = {}
    weight: dict = {}
    for nid, sym, ex, tier, score in expo:
        if nid not in by_id:
            continue
        gems_by_n.setdefault(nid, []).append(
            {"symbol": sym, "tier": tier, "score": ten(score)})
        weight[nid] = weight.get(nid, 0) + TIER_W.get(tier, 0) * float(ex)

    syms_by_n: dict = {}
    for nid, sym in pairs:
        syms_by_n.setdefault(nid, set()).add(sym)

    def subtree(nid):
        yield nid
        for c in kids.get(nid, []):
            yield from subtree(c)

    def agg(nid):
        w = 0.0
        syms: set = set()
        board: set = set()
        for x in subtree(nid):
            w += weight.get(x, 0)
            syms |= syms_by_n.get(x, set())
            board |= {g["symbol"] for g in gems_by_n.get(x, [])}
        return round(w, 1), len(syms), len(board)

    def top_board(nid, k=4):
        seen, out = set(), []
        for x in subtree(nid):
            for g in gems_by_n.get(x, []):
                if g["symbol"] not in seen:
                    seen.add(g["symbol"])
                    out.append(g)
        return sorted(out, key=lambda g: -(g["score"] or 0))[:k]

    macros = sorted((n for n in nars if n[2] == "macro"),
                    key=lambda n: -agg(n[0])[0])
    forces = []
    for m in macros:
        w, comp, brd = agg(m[0])
        forces.append({
            "id": m[0], "name": m[1], "thesis": m[5],
            "momentum": m[4] or "stable",
            "board_weight": w, "companies": comp, "board_companies": brd,
            "top_stocks": top_board(m[0]),
        })

    emerging = []
    for n in nars:
        if n[2] not in ("emerging", "candidate"):
            continue
        comp = len(syms_by_n.get(n[0], ()))
        adds = ledger.get(n[0], (0, 0, 0))[0]
        parent = by_id.get(n[3])
        emerging.append({
            "id": n[0], "name": n[1], "maturity": n[2],
            "parent": parent[1] if parent else None,
            "age_days": (n[6] and
                         ((datetime.now(timezone.utc) if n[6].tzinfo
                           else datetime.utcnow()) - n[6]).days),
            "companies": comp, "adds_30d": adds,
        })
    emerging.sort(key=lambda e: (-(e["adds_30d"]), -(e["companies"])))

    # Losing support = the ledger says so on NET (or lifecycle says
    # declining) — never just "had some weaken ops while growing".
    weakening = []
    for n in nars:
        grew, weak, rem = ledger.get(n[0], (0, 0, 0))
        misses = misses_by_n.get(n[0], 0)
        net = grew - weak - rem
        losing = (weak + rem > 0 and net <= 0) or n[7] == "declining" \
            or misses > 0
        if not losing:
            continue
        weakening.append({
            "id": n[0], "name": n[1], "level": n[2],
            "status": n[7],
            "strengthened_30d": grew, "weakened_30d": weak,
            "removed_30d": rem, "misses": misses,
            "net_30d": net,
            "companies": len(syms_by_n.get(n[0], ())),
        })
    weakening.sort(key=lambda x: x["net_30d"])

    return {
        "forces": forces,
        "emerging": emerging[:10],
        "weakening": weakening[:10],
    }
