"""
Prediction grader — the machinery that makes company narratives EARN weight
(P3 prerequisite; spec amendment 2026-08-05: claims never move a score,
only delivered numbers and confirmed predictions do).

Every company narrative is born with 2-4 falsifiable predictions
(narrative_checkpoints: claim + observable + deadline). This pass grades
the ones that have come due against the company's own filed material:

  confirmed          -> maturity +0.15 (the story is proving out)
  missed             -> maturity -0.25 (fast decay on falsification)
  not_yet_disclosed  -> stays pending; deterministic overdue rule: past
                        deadline by >45 days with still nothing filed = missed
                        (a story whose proof never arrives is a missed story)

Verdicts come ONLY from filed material (never price, never analyst views,
never model world-knowledge). Two misses put the narrative into 'declining'.
Cost discipline: only due checkpoints are graded (deadline <= today+2),
one cached-system Sonnet call per SYMBOL (not per checkpoint), usage
recorded to llm_usage.
"""
import json
import time

from sqlalchemy import text

SONNET = "claude-sonnet-4-6"
OVERDUE_GRACE_DAYS = 45
DUE_HORIZON_DAYS = 2      # grade predictions due within this many days

GRADER_SYSTEM = """You grade PREDICTIONS that an investment platform made about a company. Each prediction was written months ago with a claim, an observable (the metric or disclosure to watch), and a deadline. You decide each verdict STRICTLY from the company's own filed material provided below.

Verdicts:
- "confirmed": the filed material shows the observable at or beyond the claimed level. Cite the number/disclosure.
- "missed": the filed material shows the observable clearly fell short, or shows the claim's premise was abandoned (program cancelled, deal dead, target withdrawn). Cite it.
- "not_yet_disclosed": the material contains no disclosure that can settle the claim either way. This is common and honest — quarterly data may not be out yet. Do NOT guess.

Rules:
- Judge ONLY from the provided material. Your own knowledge of the company is NOT evidence. Price moves and analyst opinions are NOT evidence.
- Be strict about "confirmed": partial progress toward a specific number is not confirmation unless the claim's threshold is met. If a claim says 16,000 tons/day and the filing shows 14,500 ramping, that is "not_yet_disclosed" (deadline pending) or "missed" (deadline passed).
- Every confirmed/missed verdict must cite the specific disclosure in "evidence".

Return ONLY a valid JSON array:
[{"checkpoint_id": <int>, "verdict": "confirmed" | "missed" | "not_yet_disclosed", "evidence": "<cited disclosure, or why nothing settles it>"}]"""

CONFIRM_BONUS = 0.15
MISS_PENALTY = 0.25
MATURITY_FLOOR = 0.05


def _due_checkpoints(engine) -> dict:
    """{symbol: [checkpoint rows]} for pending predictions due within the
    horizon (including long-overdue ones)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT n.symbol, c.id, c.claim, c.observable, c.deadline, n.id
            FROM narrative_checkpoints c
            JOIN narratives n ON n.id = c.narrative_id
            WHERE c.status = 'pending' AND n.scope = 'company'
              AND n.status IN ('active', 'candidate', 'declining')
              AND c.deadline IS NOT NULL
              AND c.deadline <= CURRENT_DATE + make_interval(days => :h)
            ORDER BY n.symbol, c.deadline
        """), {"h": DUE_HORIZON_DAYS}).fetchall()
    out: dict[str, list] = {}
    for sym, cid, claim, obs, deadline, nid in rows:
        out.setdefault(sym, []).append(
            {"cid": cid, "claim": claim, "observable": obs,
             "deadline": deadline, "nid": nid})
    return out


def grade_due_checkpoints(engine) -> dict:
    """Grade all due predictions; apply maturity deltas; flip narratives
    with 2+ misses to 'declining'. Returns stats."""
    from anthropic import Anthropic
    from pipeline.company_narrative import _stock_material
    from pipeline.llm_usage import record_usage

    due = _due_checkpoints(engine)
    stats = {"symbols": len(due), "graded": 0, "confirmed": 0, "missed": 0,
             "not_yet": 0, "overdue_missed": 0, "failed": 0}
    if not due:
        print("prediction grader: nothing due")
        return stats

    client = Anthropic()
    for sym, cps in due.items():
        material = _stock_material(engine, sym)
        cp_block = "\n".join(
            f'- checkpoint_id {c["cid"]} (deadline {c["deadline"]}): '
            f'CLAIM: {c["claim"]} | OBSERVABLE: {c["observable"]}' for c in cps)
        user = (f"Company: {sym}\n\nPREDICTIONS DUE:\n{cp_block}\n\n"
                f"FILED MATERIAL (the only admissible evidence):\n{material}")
        verdicts = None
        for attempt in range(3):
            try:
                resp = client.messages.create(
                    model=SONNET, max_tokens=1500, timeout=90,
                    system=[{"type": "text", "text": GRADER_SYSTEM,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user}])
                record_usage(engine, "checkpoint_grader", SONNET, resp.usage)
                raw = resp.content[0].text.strip()
                verdicts = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)
        if not isinstance(verdicts, list):
            stats["failed"] += 1
            continue

        vmap = {v.get("checkpoint_id"): v for v in verdicts if isinstance(v, dict)}
        with engine.begin() as conn:
            for c in cps:
                v = vmap.get(c["cid"])
                verdict = (v or {}).get("verdict")
                evidence = ((v or {}).get("evidence") or "")[:600]
                # Deterministic overdue rule: proof that never arrives = miss
                if verdict not in ("confirmed", "missed"):
                    overdue = conn.execute(text(
                        "SELECT CURRENT_DATE - :d > :g"),
                        {"d": c["deadline"], "g": OVERDUE_GRACE_DAYS}).scalar()
                    if overdue:
                        verdict = "missed"
                        evidence = (f"no confirming disclosure within "
                                    f"{OVERDUE_GRACE_DAYS} days of deadline. "
                                    + evidence)[:600]
                        stats["overdue_missed"] += 1
                    else:
                        stats["not_yet"] += 1
                        conn.execute(text("""
                            UPDATE narrative_checkpoints
                            SET status_evidence = :e, status_updated = NOW()
                            WHERE id = :i"""), {"e": evidence, "i": c["cid"]})
                        continue
                stats["graded"] += 1
                stats[verdict] += 1
                conn.execute(text("""
                    UPDATE narrative_checkpoints
                    SET status = :s, status_evidence = :e, status_updated = NOW()
                    WHERE id = :i"""),
                    {"s": verdict, "e": evidence, "i": c["cid"]})
                delta = CONFIRM_BONUS if verdict == "confirmed" else -MISS_PENALTY
                conn.execute(text("""
                    UPDATE narratives
                    SET maturity = GREATEST(:f, LEAST(1.0, maturity + :d)),
                        updated_at = NOW()
                    WHERE id = :n"""),
                    {"f": MATURITY_FLOOR, "d": delta, "n": c["nid"]})
                print(f"  {sym} checkpoint {c['cid']}: {verdict.upper()} "
                      f"(maturity {'+' if delta > 0 else ''}{delta})")
            # Two misses = the story is failing its own tests
            conn.execute(text("""
                UPDATE narratives SET status = 'declining'
                WHERE id IN (SELECT narrative_id FROM narrative_checkpoints
                             WHERE narrative_id = ANY(:nids) AND status = 'missed'
                             GROUP BY narrative_id HAVING COUNT(*) >= 2)
                  AND status IN ('active', 'candidate')"""),
                {"nids": list({c["nid"] for c in cps})})
    print(f"prediction grader: {stats}")
    return stats


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    grade_due_checkpoints(get_engine())
