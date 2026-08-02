"""
Narrative structure pass — light-touch containment for the organically
growing narrative library (user-approved 2026-08-03). Three duties, run
weekly after the lifecycle engine:

1. TAXONOMY  — every narrative carries a scope (macro/sector/subsector/
   company) and non-macro narratives attach to a parent. Classified in ONE
   Sonnet call for all unscoped narratives (cost-effective by design).
2. MERGE DISCIPLINE — near-duplicate detection: cheap token-overlap filter
   -> clusters via connected components -> one cached Sonnet judgment per
   cluster. 'Distinct' verdicts are REMEMBERED (never re-litigated).
   Only candidate/emerging narratives merge automatically; clusters touching
   sector/macro tiers are flagged for user review, never auto-executed.
   Max 5 merges per pass. Every merge is a logged lifecycle event; the
   absorbed narrative's evidence is appended to the survivor and exposure
   links re-point at max strength (the E-inflation fix).
3. CENSUS — weekly metrics to env_diagnostics: counts by scope, promotions,
   avg links per stock (E-dilution early warning), top fan-out.

No hard caps, no approval gate on creation — a skeleton, not a cage.
All LLM calls instrumented via llm_usage.
"""
import json
import re
import time

from sqlalchemy import text

SONNET = "claude-sonnet-4-6"
SIM_THRESHOLD = 0.33   # token-Jaccard on name+thesis; deliberately loose — the judge decides, a few cents per cluster
MAX_MERGES_PER_PASS = 5

_STOP = set("the a an of and or to in for with on by from as at is are be this that its "
            "their our it companies company narrative structural demand growth market".split())


def _tokens(*texts) -> set:
    words = re.findall(r"[a-z]{3,}", " ".join(t or "" for t in texts).lower())
    return {w for w in words if w not in _STOP}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ensure_schema(engine):
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE narratives ADD COLUMN IF NOT EXISTS scope VARCHAR(12)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS narrative_merge_decisions (
                id SERIAL PRIMARY KEY,
                narrative_ids INTEGER[] NOT NULL,
                verdict VARCHAR(12) NOT NULL,      -- 'merged' | 'distinct' | 'review'
                rationale TEXT,
                decided_at TIMESTAMP DEFAULT NOW()
            )"""))


def classify_scopes(engine) -> dict:
    """One Sonnet call classifies ALL unscoped narratives: scope + parent."""
    from anthropic import Anthropic
    from pipeline.llm_usage import record_usage

    with engine.connect() as conn:
        unscoped = conn.execute(text("""
            SELECT id, name, tier, COALESCE(thesis,'') FROM narratives
            WHERE status='active' AND scope IS NULL ORDER BY id""")).fetchall()
        parents = conn.execute(text("""
            SELECT id, name, tier FROM narratives
            WHERE status='active' AND tier IN ('macro','sector') ORDER BY tier, id""")).fetchall()
    if not unscoped:
        return {"classified": 0}

    # Trivial cases need no LLM
    trivial, needs_llm = [], []
    for nid, name, tier, thesis in unscoped:
        if tier in ("macro", "sector"):
            trivial.append((nid, tier, None))
        else:
            needs_llm.append((nid, name, thesis))

    llm_results = []
    if needs_llm:
        parent_block = "\n".join(f"{p[0]}. [{p[2]}] {p[1]}" for p in parents)
        items = "\n".join(f'{i[0]}. "{i[1]}": {i[2][:200]}' for i in needs_llm)
        prompt = (
            "Classify each narrative below.\n"
            "scope: 'subsector' (a niche within an industry, multiple companies) or "
            "'company' (one company's specific story).\n"
            "parent: the id of the closest PARENT from this list (or null if none fits):\n"
            f"{parent_block}\n\nNARRATIVES TO CLASSIFY:\n{items}\n\n"
            'Return ONLY a JSON array: [{"id": <int>, "scope": "subsector|company", '
            '"parent": <int or null>}]')
        client = Anthropic()
        for attempt in range(3):
            try:
                resp = client.messages.create(model=SONNET, max_tokens=2000, timeout=60,
                    messages=[{"role": "user", "content": prompt}])
                record_usage(engine, "narrative_structure", SONNET, resp.usage)
                raw = resp.content[0].text.strip()
                start = raw.index("[")
                llm_results = json.loads(raw[start:raw.rindex("]") + 1])
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)

    valid_parent_ids = {p[0] for p in parents}
    with engine.begin() as conn:
        for nid, scope, parent in trivial:
            conn.execute(text("UPDATE narratives SET scope=:s WHERE id=:i"),
                         {"s": scope, "i": nid})
        n_llm = 0
        for r in llm_results:
            if not isinstance(r, dict) or r.get("scope") not in ("subsector", "company"):
                continue
            parent = r.get("parent")
            parent = parent if parent in valid_parent_ids else None
            conn.execute(text("""UPDATE narratives SET scope=:s,
                parent_id=COALESCE(parent_id, :p) WHERE id=:i AND scope IS NULL"""),
                {"s": r["scope"], "p": parent, "i": r.get("id")})
            n_llm += 1
    print(f"  taxonomy: {len(trivial)} trivial + {n_llm} LLM-classified")
    return {"classified": len(trivial) + n_llm}


def find_merge_clusters(engine) -> list:
    """Token-overlap filter -> connected components. Remembered 'distinct'
    verdicts are excluded up front."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, tier, COALESCE(thesis,'') FROM narratives
            WHERE status='active'""")).fetchall()
        decided = conn.execute(text(
            "SELECT narrative_ids FROM narrative_merge_decisions WHERE verdict='distinct'"
        )).fetchall()
    decided_pairs = {tuple(sorted(d[0])) for d in decided if len(d[0]) == 2}

    toks = {r[0]: _tokens(r[1], r[3]) for r in rows}
    meta = {r[0]: (r[1], r[2]) for r in rows}
    cand_ids = [r[0] for r in rows if r[2] in ("candidate", "emerging")]
    all_ids = [r[0] for r in rows]

    edges = []
    for i, a in enumerate(cand_ids):
        for b in all_ids:
            if b <= a and b in cand_ids:
                continue
            if a == b:
                continue
            if tuple(sorted((a, b))) in decided_pairs:
                continue
            if _jaccard(toks[a], toks[b]) >= SIM_THRESHOLD:
                edges.append((a, b))

    # connected components
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        parent[find(x)] = find(y)
    for a, b in edges:
        union(a, b)
    clusters = {}
    for a, b in edges:
        clusters.setdefault(find(a), set()).update((a, b))
    out = [sorted(c) for c in clusters.values()]
    if out:
        for c in out:
            print(f"  merge suspect cluster: {[(i, meta[i][0][:40]) for i in c]}")
    return out


def adjudicate_and_merge(engine, clusters: list) -> dict:
    from anthropic import Anthropic
    from pipeline.llm_usage import record_usage
    stats = {"clusters": len(clusters), "merged": 0, "distinct": 0, "review": 0}
    if not clusters:
        return stats
    client = Anthropic()

    JUDGE_SYSTEM = ("You adjudicate whether narratives in a cluster describe the SAME "
        "underlying investment narrative or are genuinely DISTINCT. Same = one thesis "
        "wearing different names (merge them). Distinct = different economic mechanisms "
        "or different beneficiary sets, even if adjacent. Be conservative: when genuinely "
        "unsure, rule distinct.\nReturn ONLY JSON: "
        '{"verdict": "same" | "distinct", "survivor_id": <int, only if same — the '
        'broader/better-evidenced one>, "rationale": "one sentence"}')

    merges_done = 0
    for cluster in clusters:
        if merges_done >= MAX_MERGES_PER_PASS:
            break
        with engine.connect() as conn:
            details = conn.execute(text("""
                SELECT n.id, n.name, n.tier, COALESCE(n.thesis,''),
                       (SELECT COUNT(*) FROM narrative_evidence ev WHERE ev.narrative_id=n.id),
                       (SELECT COUNT(*) FROM narrative_exposures ne WHERE ne.narrative_id=n.id)
                FROM narratives n WHERE n.id = ANY(:ids)"""),
                {"ids": cluster}).fetchall()
        tiers = {d[2] for d in details}
        block = "\n\n".join(f"id {d[0]} [{d[2]}] \"{d[1]}\"\nthesis: {d[3][:300]}\n"
                            f"evidence rows: {d[4]}, exposed stocks: {d[5]}" for d in details)
        # Clusters touching sector/macro: flag for user review, never auto-merge
        if tiers & {"sector", "macro"}:
            with engine.begin() as conn:
                conn.execute(text("""INSERT INTO narrative_merge_decisions
                    (narrative_ids, verdict, rationale) VALUES (:ids, 'review',
                     'cluster touches sector/macro tier — user review required')"""),
                    {"ids": cluster})
            stats["review"] += 1
            continue

        verdict = None
        for attempt in range(3):
            try:
                resp = client.messages.create(model=SONNET, max_tokens=400, timeout=60,
                    system=[{"type": "text", "text": JUDGE_SYSTEM,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": block}])
                record_usage(engine, "narrative_structure", SONNET, resp.usage)
                raw = resp.content[0].text.strip()
                start = raw.index("{")
                verdict = json.loads(raw[start:raw.rindex("}") + 1])
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)
        if not verdict:
            continue

        if verdict.get("verdict") == "same" and verdict.get("survivor_id") in cluster:
            survivor = verdict["survivor_id"]
            absorbed = [i for i in cluster if i != survivor]
            with engine.begin() as conn:
                for aid in absorbed:
                    # evidence follows the survivor; exposures re-point at MAX strength
                    conn.execute(text(
                        "UPDATE narrative_evidence SET narrative_id=:s WHERE narrative_id=:a"),
                        {"s": survivor, "a": aid})
                    conn.execute(text("""
                        UPDATE narrative_exposures ne SET narrative_id=:s
                        WHERE ne.narrative_id=:a AND NOT EXISTS (
                            SELECT 1 FROM narrative_exposures x
                            WHERE x.symbol=ne.symbol AND x.narrative_id=:s)"""),
                        {"s": survivor, "a": aid})
                    conn.execute(text("""
                        UPDATE narrative_exposures x SET exposure=GREATEST(x.exposure, d.exposure)
                        FROM narrative_exposures d
                        WHERE x.narrative_id=:s AND d.narrative_id=:a AND d.symbol=x.symbol"""),
                        {"s": survivor, "a": aid})
                    conn.execute(text(
                        "DELETE FROM narrative_exposures WHERE narrative_id=:a"), {"a": aid})
                    conn.execute(text("""
                        UPDATE narratives SET status='merged', parent_id=:s WHERE id=:a"""),
                        {"s": survivor, "a": aid})
                    conn.execute(text("""
                        INSERT INTO narrative_events (narrative_id, event_type, reason)
                        VALUES (:a, 'merged_into', :d)"""),
                        {"a": aid, "d": f"merged into narrative {survivor}: "
                                        f"{verdict.get('rationale','')[:300]}"})
                conn.execute(text("""INSERT INTO narrative_merge_decisions
                    (narrative_ids, verdict, rationale) VALUES (:ids, 'merged', :r)"""),
                    {"ids": cluster, "r": verdict.get("rationale", "")[:400]})
            stats["merged"] += len(absorbed)
            merges_done += 1
            print(f"  MERGED {absorbed} -> {survivor}: {verdict.get('rationale','')[:80]}")
        else:
            with engine.begin() as conn:
                conn.execute(text("""INSERT INTO narrative_merge_decisions
                    (narrative_ids, verdict, rationale) VALUES (:ids, 'distinct', :r)"""),
                    {"ids": cluster, "r": (verdict.get("rationale") or "")[:400]})
            stats["distinct"] += 1
    return stats


def census(engine) -> dict:
    with engine.connect() as conn:
        c = conn.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE tier='macro') AS macro,
              COUNT(*) FILTER (WHERE tier='sector') AS sector,
              COUNT(*) FILTER (WHERE tier IN ('emerging','candidate')) AS growing,
              COUNT(*) FILTER (WHERE momentum='accelerating') AS accelerating
            FROM narratives WHERE status='active'""")).fetchone()
        links = conn.execute(text("""
            SELECT ROUND(AVG(n),2) FROM (
              SELECT COUNT(*) AS n FROM narrative_exposures GROUP BY symbol) x""")).scalar()
        top = conn.execute(text("""
            SELECT n.name, COUNT(*) FROM narrative_exposures ne
            JOIN narratives n ON n.id=ne.narrative_id
            GROUP BY n.name ORDER BY COUNT(*) DESC LIMIT 1""")).fetchone()
        promos = conn.execute(text("""
            SELECT COUNT(*) FROM narrative_events
            WHERE created_at > NOW() - INTERVAL '7 days'""")).fetchone()
    result = {"macro": c[0], "sector": c[1], "growing": c[2], "accelerating": c[3],
              "avg_links_per_stock": float(links or 0),
              "top_fanout": f"{top[0]} ({top[1]} stocks)" if top else None,
              "lifecycle_events_7d": promos[0] if promos else 0}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO env_diagnostics (source, result) VALUES ('narrative_census', :r)"),
            {"r": json.dumps(result)})
    print(f"  census: {result}")
    return result


def run_structure_pass(engine) -> dict:
    ensure_schema(engine)
    out = {"taxonomy": classify_scopes(engine)}
    out["merge"] = adjudicate_and_merge(engine, find_merge_clusters(engine))
    out["census"] = census(engine)
    return out


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    run_structure_pass(get_engine())
