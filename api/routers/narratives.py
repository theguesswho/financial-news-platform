"""GET /narratives — the three-layer map (ui/pages/2_Themes.py port).

Layer 1: macro forces sized by CANONICAL BOARD CONVICTION (decision 7,
2026-08-11): sum over DISTINCT board companies of tier weight (3/2/1) x the
company's STRONGEST exposure anywhere in the narrative's subtree — colored by
momentum. Layer 2: salience-ranked cards from any level (board conviction +
recent ledger change + momentum bonus — deterministic, no LLM). Layer 3:
the complete parented tree. Company-scope narratives are excluded — they
are dossier material, not map material.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
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
              AND eh.op IN ('add','strengthen','weaken','remove','decay')
              AND eh.trigger != 'shadow'
            GROUP BY eh.narrative_id""")).fetchall())

    by_id = {n[0]: n for n in nars}
    kids: dict = {}
    for n in nars:
        # macros are roots by definition — never a child
        if n[4] in by_id and n[2] != "macro":
            kids.setdefault(n[4], []).append(n[0])

    gems_by_n: dict = {}
    links_by_n: dict = {}
    for nid, sym, ex, tier, score in expo:
        if nid not in by_id:
            continue
        gems_by_n.setdefault(nid, []).append(
            {"symbol": sym, "tier": tier, "score": ten(score)})
        links_by_n.setdefault(nid, []).append(
            (sym, TIER_W.get(tier, 0), float(ex)))

    # canonical board conviction: per DISTINCT symbol, tier weight x the
    # symbol's strongest exposure in the subtree (decision 7)
    def conviction(nid):
        best: dict = {}
        stack = [nid]
        while stack:
            x = stack.pop()
            stack.extend(kids.get(x, []))
            for sym, tw, ex in links_by_n.get(x, []):
                if sym not in best or ex > best[sym][1]:
                    best[sym] = (tw, ex)
        return sum(tw * ex for tw, ex in best.values())

    weight = {nid: sum(tw * ex for _, tw, ex in links_by_n.get(nid, []))
              for nid in by_id}
    rollup = conviction

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
        # Board conviction (canonical, same formula as the map).
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
                   COUNT(*) FILTER (WHERE op IN ('weaken','decay')),
                   COUNT(*) FILTER (WHERE op = 'remove')
            FROM exposure_history
            WHERE judged_at > NOW() - INTERVAL '30 days'
              AND trigger != 'shadow'
            GROUP BY narrative_id""")).fetchall()}

    by_id = {n[0]: n for n in nars}
    kids: dict = {}
    for n in nars:
        if n[3] in by_id and n[2] != "macro":
            kids.setdefault(n[3], []).append(n[0])

    gems_by_n: dict = {}
    links_by_n: dict = {}
    for nid, sym, ex, tier, score in expo:
        if nid not in by_id:
            continue
        gems_by_n.setdefault(nid, []).append(
            {"symbol": sym, "tier": tier, "score": ten(score)})
        links_by_n.setdefault(nid, []).append(
            (sym, TIER_W.get(tier, 0), float(ex)))

    syms_by_n: dict = {}
    for nid, sym in pairs:
        syms_by_n.setdefault(nid, set()).add(sym)

    def subtree(nid):
        yield nid
        for c in kids.get(nid, []):
            yield from subtree(c)

    def agg(nid):
        # canonical board conviction: per DISTINCT symbol, tier weight x
        # strongest exposure in the subtree (decision 7)
        best: dict = {}
        syms: set = set()
        for x in subtree(nid):
            syms |= syms_by_n.get(x, set())
            for sym, tw, ex in links_by_n.get(x, []):
                if sym not in best or ex > best[sym][1]:
                    best[sym] = (tw, ex)
        w = sum(tw * ex for tw, ex in best.values())
        return round(w, 1), len(syms), len(best)

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


def _tree(conn):
    """The map's narrative tree (company scope excluded, merged dropped):
    rows by id + the child index used for every subtree rollup here."""
    nars = conn.execute(text("""
        SELECT id, name, tier, parent_id,
               COALESCE(thesis, description), status, momentum, falsification
        FROM narratives
        WHERE status != 'merged' AND COALESCE(scope,'') != 'company'
    """)).fetchall()
    by_id = {n[0]: n for n in nars}
    kids: dict = {}
    for n in nars:
        # macros are roots by definition — never a child
        if n[3] in by_id and n[2] != "macro":
            kids.setdefault(n[3], []).append(n[0])
    return by_id, kids


def _subtree(kids, narrative_id):
    sub, stack = set(), [narrative_id]
    while stack:
        x = stack.pop()
        if x in sub:
            continue
        sub.add(x)
        stack.extend(kids.get(x, []))
    return sub


def _links(conn, ids):
    """Every exposure row under a set of narratives, plus the board
    snapshot — fetched ONCE per request. A force page needs a roster for
    the force and for each of its children; querying per child turned one
    page into a dozen round trips to a remote database."""
    rows = conn.execute(text("""
        SELECT ne.narrative_id, ne.symbol, ne.exposure, ne.direction,
               f.company_name
        FROM narrative_exposures ne
        LEFT JOIN fundamentals f ON f.symbol = ne.symbol
        WHERE ne.narrative_id = ANY(:ids)
    """), {"ids": list(ids)}).fetchall()
    snap = {r[0]: r[1:] for r in conn.execute(text("""
        SELECT symbol, COALESCE(assessed_tier, tier), gem_score
        FROM leaderboard_history
        WHERE date = (SELECT MAX(date) FROM leaderboard_history)
    """)).fetchall()}
    return rows, snap


def _roster(rows, snap, sub):
    """Every company carrying exposure anywhere in the subtree (deduped,
    STRONGEST link kept, with the direction that link carries — a force can
    be a headwind, and a roster row that hides "threatened" reads as a
    recommendation), split into on-board (by score) and the attached-but-
    off-board tail (by exposure) — the discovery product. Board membership
    comes from the snapshot keyed by symbol; the company↔force pairing is
    narrative_id throughout, never a name match."""
    best: dict = {}
    for nid, sym, ex, direction, company in rows:
        if nid not in sub:
            continue
        e = float(ex) if ex is not None else None
        cur = best.get(sym)
        if cur is None or (e or 0) > (cur[0] or 0):
            best[sym] = (e, direction, company)

    on_board, off_board = [], []
    for sym, (ex, direction, company) in best.items():
        tier, score = snap.get(sym, (None, None))
        row = {
            "symbol": sym, "company": company, "exposure": ex,
            "direction": direction, "tier": tier, "score": ten(score),
        }
        (on_board if tier else off_board).append(row)
    on_board.sort(key=lambda r: -(r["score"] or 0))
    off_board.sort(key=lambda r: -(r["exposure"] or 0))
    return {
        "covered": len(best),
        "on_board": on_board,
        "off_board": off_board[:25],
        "off_board_total": len(off_board),
    }


def _health(conn, narrative_id):
    """The pulse: narrative_health_history week by week (already rolled up
    through the subtree by pipeline/narrative_vital_signs.py, so no rollup
    happens here). Two honesty rules baked in:
    - `momentum_state` is NOT returned. It is a SHADOW column, NULL until
      NARRATIVE_SPEC Phase 2 passes its cutover gate; shipping it would
      put an unearned word on a product surface.
    - `seeding` rides on every week. Weeks before 2026-08-03 are backfill
      from the ledger's opening sweep — the instrument opening its eyes,
      not the world changing — and any surface charting them must say so.
      `observed_weeks` counts only the non-seeding ones.
    """
    rows = conn.execute(text("""
        SELECT week_start, support, erosion, breadth, active_exposures,
               exposed_board_weight, checkpoint_passes, checkpoint_fails,
               translation_share, seeding
        FROM narrative_health_history
        WHERE narrative_id = :n ORDER BY week_start
    """), {"n": narrative_id}).fetchall()
    f = lambda v: float(v) if v is not None else None
    weeks = [{
        "week_start": r[0], "support": r[1], "erosion": r[2],
        "breadth": r[3], "active_exposures": r[4],
        "board_weight": f(r[5]),
        "checkpoint_passes": r[6], "checkpoint_fails": r[7],
        "translation_share": f(r[8]), "seeding": r[9],
    } for r in rows]
    observed = [w for w in weeks if not w["seeding"]]
    return {
        "weeks": weeks,
        "observed_weeks": len(observed),
        "first_observed_week": observed[0]["week_start"] if observed else None,
    }


@router.get("/narratives/{narrative_id}")
def get_narrative(narrative_id: int):
    """One force, opened: identity + thesis + falsification, its place in
    the tree, the roster (on board / attached tail), and the health series.
    The Forces pages read THIS — everything is keyed by narrative_id, so
    no surface ever pairs a company to a story by matching names."""
    engine = get_engine()
    with engine.connect() as conn:
        by_id, kids = _tree(conn)
        if narrative_id not in by_id:
            raise HTTPException(404, "unknown narrative")
        sub = _subtree(kids, narrative_id)
        rows, snap = _links(conn, sub)
        roster = _roster(rows, snap, sub)
        health = _health(conn, narrative_id)
        child_rosters = {c: _roster(rows, snap, _subtree(kids, c))
                         for c in kids.get(narrative_id, [])}

    n = by_id[narrative_id]
    parent = by_id.get(n[3])
    board_weight = sum(
        TIER_W.get(r["tier"], 0) * (r["exposure"] or 0)
        for r in roster["on_board"])
    return {
        "id": narrative_id, "name": n[1], "level": n[2],
        "thesis": n[4], "status": n[5], "momentum": n[6] or "stable",
        "falsification": n[7],
        "parent": parent and {"id": parent[0], "name": parent[1]},
        "children": [{
            "id": c, "name": by_id[c][1], "level": by_id[c][2],
            "covered": child_rosters[c]["covered"],
            "on_board": len(child_rosters[c]["on_board"]),
        } for c in sorted(kids.get(narrative_id, []),
                          key=lambda c: -child_rosters[c]["covered"])],
        "board_weight": round(board_weight, 2),
        "roster": roster,
        "health": health,
    }


@router.get("/narratives/{narrative_id}/roster")
def get_narrative_roster(narrative_id: int):
    """The roster alone (kept: it is what the Forces page needed first).
    GET /narratives/{id} returns this same block plus thesis and health."""
    engine = get_engine()
    with engine.connect() as conn:
        by_id, kids = _tree(conn)
        if narrative_id not in by_id:
            raise HTTPException(404, "unknown narrative")
        sub = _subtree(kids, narrative_id)
        roster = _roster(*_links(conn, sub), sub)

    n = by_id[narrative_id]
    return {
        "id": narrative_id, "name": n[1], "level": n[2],
        "thesis": n[4], "status": n[5], **roster,
    }
