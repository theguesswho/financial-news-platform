"""
Narrative lifecycle engine — the brain's growth and pruning.

Runs weekly (after exposure scoring). Four passes:

1. METRICS   — snapshot each narrative's footprint into narrative_history:
               breadth (stocks exposed), avg exposure, cohort fundamentals
               vs the universe. This is the time series everything else reads.
2. CANDIDATES — bottom-up clusters (meta_themes) that map to no existing
               narrative become tier='candidate' narratives automatically.
               The data flags them; nobody waits for a quarterly review.
3. PROMOTION — earned by data, evaluated every run:
               candidate → emerging : survives 2+ snapshots, breadth >= 4
               emerging  → sector   : breadth >= 8 AND cohort revenue growth
                                      beats the universe median (2 snapshots)
               sector    → macro    : breadth >= 25 across 3+ sectors
4. DECLINE   — each narrative's own falsification conditions are checked by
               Sonnet against recent evidence from its exposed cohort. A
               triggered condition sets momentum 'decelerating'; two
               consecutive triggered runs set status 'declining' (which cuts
               its weight in the gem score to 0.20). Recovery flips it back.

Every transition is logged to narrative_events and surfaces in the daily brief.
"""
import json
from datetime import date

from anthropic import Anthropic
from sqlalchemy import text

from pipeline.narrative_brain import log_event

SONNET = "claude-sonnet-4-6"


def ensure_history_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS narrative_history (
                id            SERIAL PRIMARY KEY,
                narrative_id  INTEGER NOT NULL REFERENCES narratives(id),
                snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
                breadth       INTEGER,            -- stocks with exposure >= 0.40
                avg_exposure  NUMERIC(5,3),
                sector_count  INTEGER,
                cohort_rev_growth  NUMERIC(10,4), -- median of exposed cohort
                universe_rev_growth NUMERIC(10,4),
                momentum      VARCHAR(20),
                falsification_verdict JSONB,
                UNIQUE (narrative_id, snapshot_date)
            )
        """))


# ── Pass 1: metrics ──────────────────────────────────────────────────────────

def snapshot_metrics(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO narrative_history
                (narrative_id, snapshot_date, breadth, avg_exposure, sector_count,
                 cohort_rev_growth, universe_rev_growth, momentum)
            SELECT nar.id, CURRENT_DATE,
                   COUNT(*) FILTER (WHERE ne.exposure >= 0.40),
                   AVG(ne.exposure),
                   COUNT(DISTINCT f.sector) FILTER (WHERE ne.exposure >= 0.40),
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.revenue_growth_yoy)
                       FILTER (WHERE ne.exposure >= 0.40),
                   (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue_growth_yoy)
                    FROM fundamentals WHERE revenue_growth_yoy IS NOT NULL),
                   nar.momentum
            FROM narratives nar
            LEFT JOIN narrative_exposures ne ON ne.narrative_id = nar.id
            LEFT JOIN fundamentals f ON f.symbol = ne.symbol
            WHERE nar.status IN ('active', 'declining')
            GROUP BY nar.id
            ON CONFLICT (narrative_id, snapshot_date) DO UPDATE SET
                breadth = EXCLUDED.breadth, avg_exposure = EXCLUDED.avg_exposure,
                sector_count = EXCLUDED.sector_count,
                cohort_rev_growth = EXCLUDED.cohort_rev_growth,
                universe_rev_growth = EXCLUDED.universe_rev_growth
        """))
    print("  ✓ Narrative metrics snapshotted")


# ── Pass 2: candidate detection ──────────────────────────────────────────────

def detect_candidates(engine, client):
    """Bottom-up clusters that map to no existing narrative become candidates."""
    with engine.connect() as conn:
        clusters = conn.execute(text("""
            SELECT name, description FROM meta_themes
            WHERE COALESCE(status,'active') = 'active'
              AND name NOT ILIKE '%idiosyncratic%'
        """)).fetchall()
        existing = [r[0] for r in conn.execute(text(
            "SELECT name || COALESCE(': ' || description, '') FROM narratives WHERE status != 'retired'"
        )).fetchall()]

    if not clusters:
        return 0

    cluster_block = "\n".join(f"- {c[0]}: {c[1]}" for c in clusters)
    prompt = f"""Our narrative knowledge base tracks these narratives:
{chr(10).join('- ' + e for e in existing)}

Below are theme clusters detected bottom-up from recent SEC filings. Identify which
represent a STRUCTURAL FORCE (a why-the-world-is-changing tailwind or headwind) that is
GENUINELY NOT COVERED by any existing narrative above. Corporate events (spin-offs,
deleveraging, single-company product cycles) are NOT narratives — skip those.

Clusters:
{cluster_block}

Return ONLY a JSON array (empty [] if nothing new) of genuinely new forces:
[{{"name": "<3-6 word force name>", "thesis": "<2 sentences>",
   "description": "<one display sentence>", "sector_scope": "<sector or null>",
   "falsification": ["<3 concrete checkable kill conditions>", "...", "..."]}}]"""

    resp = client.messages.create(model=SONNET, max_tokens=3000,
                                  messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        new = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except Exception:
        return 0

    created = 0
    for n in new:
        with engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO narratives (name, tier, status, thesis, description,
                                        sector_scope, falsification, momentum)
                VALUES (:name, 'candidate', 'active', :thesis, :desc, :scope, :fals, 'stable')
                ON CONFLICT (name) DO NOTHING
                RETURNING id
            """), {"name": n["name"], "thesis": n.get("thesis", ""),
                   "desc": n.get("description", ""), "scope": n.get("sector_scope"),
                   "fals": json.dumps(n.get("falsification", []))}).fetchone()
        if row:
            log_event(engine, row[0], "created", to_tier="candidate",
                      reason="Auto-detected from bottom-up filing clusters")
            created += 1
    print(f"  ✓ {created} new candidate narratives detected")
    return created


# ── Pass 3: promotion ────────────────────────────────────────────────────────

def evaluate_promotions(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT nar.id, nar.name, nar.tier,
                   COUNT(nh.id) AS snapshots,
                   MAX(nh.breadth) AS breadth,
                   MAX(nh.sector_count) AS sectors,
                   BOOL_AND(nh.cohort_rev_growth > nh.universe_rev_growth)
                       FILTER (WHERE nh.snapshot_date >= CURRENT_DATE - 21) AS growth_beats,
                   COALESCE(nar.promoted_at, nar.created_at) < NOW() - INTERVAL '28 days'
                       AS seasoned
            FROM narratives nar
            JOIN narrative_history nh ON nh.narrative_id = nar.id
            WHERE nar.status = 'active' AND nar.tier != 'macro'
            GROUP BY nar.id, nar.name, nar.tier
        """)).fetchall()

    # A narrative must be SEASONED at its current tier (28+ days since last
    # promotion) before moving up — data promotes, but not on a single snapshot.
    promotions = []
    for nid, name, tier, snaps, breadth, sectors, growth_beats, seasoned in rows:
        breadth = breadth or 0
        if tier == "candidate" and snaps >= 2 and breadth >= 4:
            promotions.append((nid, name, tier, "emerging",
                               f"{breadth} stocks exposed across {snaps} snapshots"))
        elif tier == "emerging" and seasoned and breadth >= 8 and growth_beats:
            promotions.append((nid, name, tier, "sector",
                               f"breadth {breadth}, cohort growth beats universe"))
        elif tier == "sector" and seasoned and breadth >= 40 and (sectors or 0) >= 5 and growth_beats:
            promotions.append((nid, name, tier, "macro",
                               f"breadth {breadth} across {sectors} sectors, cohort growth confirms"))

    for nid, name, from_t, to_t, reason in promotions:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE narratives SET tier=:t, promoted_at=NOW(), updated_at=NOW()
                WHERE id=:id
            """), {"t": to_t, "id": nid})
        log_event(engine, nid, "promoted", from_tier=from_t, to_tier=to_t, reason=reason)
        print(f"  ⬆ {name}: {from_t} → {to_t} ({reason})")
    if not promotions:
        print("  ✓ No promotions this run")
    return promotions


# ── Pass 4: decline / falsification check ────────────────────────────────────

def check_falsifications(engine, client):
    with engine.connect() as conn:
        narratives = conn.execute(text("""
            SELECT id, name, thesis, falsification, status, momentum
            FROM narratives
            WHERE status IN ('active', 'declining') AND tier IN ('macro', 'sector')
        """)).fetchall()

    declined, recovered = [], []
    for nid, name, thesis, fals, status, momentum in narratives:
        with engine.connect() as conn:
            evidence = conn.execute(text("""
                SELECT f.symbol, f.filing_date::date, f.title,
                       f.llm_analysis::jsonb->>'summary'
                FROM filings f
                JOIN narrative_exposures ne ON ne.symbol = f.symbol AND ne.narrative_id = :nid
                WHERE f.filing_date >= NOW() - INTERVAL '45 days'
                  AND f.llm_analysis IS NOT NULL AND ne.exposure >= 0.40
                ORDER BY f.filing_date DESC LIMIT 12
            """), {"nid": nid}).fetchall()
            cohort = conn.execute(text("""
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.revenue_growth_yoy),
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.earnings_growth_yoy)
                FROM fundamentals f
                JOIN narrative_exposures ne ON ne.symbol = f.symbol AND ne.narrative_id = :nid
                WHERE ne.exposure >= 0.40
            """), {"nid": nid}).fetchone()

        ev_block = "\n".join(f"[{r[1]}] {r[0]}: {r[3] or r[2]}" for r in evidence) or "no recent filings"
        try:
            fals_list = fals if isinstance(fals, list) else json.loads(fals or "[]")
        except Exception:
            fals_list = []

        prompt = f"""Narrative: {name}
Thesis: {thesis}

FALSIFICATION CONDITIONS (would disprove this narrative):
{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(fals_list))}

RECENT EVIDENCE from the exposed cohort's filings (45 days):
{ev_block}

Cohort medians: revenue growth {cohort[0]}, earnings growth {cohort[1]}

For each falsification condition judge: triggered (clear evidence it has occurred),
warning (partial/early evidence), or clear (no evidence). Be strict — absence of
evidence is 'clear', not 'warning'.

Return ONLY JSON:
{{"verdicts": [{{"condition": 1, "status": "triggered|warning|clear", "evidence": "<one sentence or empty>"}}],
  "overall": "healthy|warning|falsified"}}"""

        try:
            resp = client.messages.create(model=SONNET, max_tokens=800,
                                          messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            verdict = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except Exception as exc:
            print(f"  ⚠ Falsification check failed for {name}: {exc}")
            continue

        overall = verdict.get("overall", "healthy")
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE narrative_history SET falsification_verdict = :v
                WHERE narrative_id = :nid AND snapshot_date = CURRENT_DATE
            """), {"v": json.dumps(verdict), "nid": nid})

        if overall == "falsified":
            # two consecutive falsified verdicts → declining
            with engine.connect() as conn:
                prev = conn.execute(text("""
                    SELECT falsification_verdict->>'overall' FROM narrative_history
                    WHERE narrative_id = :nid AND snapshot_date < CURRENT_DATE
                    ORDER BY snapshot_date DESC LIMIT 1
                """), {"nid": nid}).scalar()
            if prev == "falsified" and status != "declining":
                with engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE narratives SET status='declining', momentum='decelerating', updated_at=NOW() WHERE id=:id"
                    ), {"id": nid})
                log_event(engine, nid, "declining", reason=json.dumps(verdict)[:500])
                declined.append(name)
                print(f"  ⬇ {name}: DECLINING (falsification confirmed twice)")
            else:
                with engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE narratives SET momentum='decelerating', updated_at=NOW() WHERE id=:id"
                    ), {"id": nid})
                print(f"  ⚠ {name}: falsification triggered — watching")
        elif status == "declining" and overall == "healthy":
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE narratives SET status='active', momentum='stable', updated_at=NOW() WHERE id=:id"
                ), {"id": nid})
            log_event(engine, nid, "recovered", reason="Falsification conditions cleared")
            recovered.append(name)
            print(f"  ⬆ {name}: recovered to active")

    print(f"  ✓ Falsification checks done ({len(declined)} declining, {len(recovered)} recovered)")
    return {"declined": declined, "recovered": recovered}


# ── Entry point ──────────────────────────────────────────────────────────────

def run_lifecycle(engine=None):
    if engine is None:
        from pipeline.hidden_gem_scorer import get_engine
        engine = get_engine()
    client = Anthropic()

    print("=" * 60)
    print("NARRATIVE LIFECYCLE ENGINE")
    print("=" * 60)
    ensure_history_table(engine)
    snapshot_metrics(engine)
    detect_candidates(engine, client)
    evaluate_promotions(engine)
    check_falsifications(engine, client)
    print("✅ Lifecycle run complete")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    run_lifecycle()
