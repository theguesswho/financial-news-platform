"""
Company Narrative Layer — birth judge, dossiers, evidence ledger.
Spec: COMPANY_NARRATIVE_SPEC.md (user-approved 2026-08-04).

The strictest evidentiary bar in the platform:
  - A narrative is A CHANGE, NOT A DESCRIPTION (composite stories fine).
  - Company-specific causality; evidence ONLY from the company's filings.
  - Falsifiable checkpoints (claim + observable + deadline) or no birth.
  - ONE active company narrative per company.
  - Two-vote birth: both votes must accept; the dossier is built from the
    intersection of agreement, checkpoints unioned.
  - Births recorded in narrative_births (accepts AND rejects, with reasons)
    — the layer's founding and growth are fully auditable.
  - Negative-control audits measure the judge's false-positive rate
    (see run_negative_controls); FP rate > 10% should freeze births.
  - Maturity born at 0.25 (seasoning); scoring reads it only in P4.

Cost discipline: cached static system prompt; one call per vote; all usage
recorded via llm_usage.
"""
import json
import time

from sqlalchemy import text

SONNET = "claude-sonnet-4-6"
BIRTH_MATURITY = 0.25
MAX_BIRTHS_PER_WEEK = 5

BIRTH_SYSTEM = """You are the birth judge for a platform's COMPANY NARRATIVE layer — the strictest gate in the system. You decide whether a company has ONE genuine company-specific narrative worth tracking as a living dossier.

THE BAR (all four required — any failure means REJECT):
1. A CHANGE, NOT A DESCRIPTION. "This company has a moat / a flywheel / a monopoly" is a business description — timeless, unfalsifiable, REJECT. A narrative has direction and a timeline: an acquisition being integrated, a platform shift underway, a mix transformation, a regulatory unlock approaching. Composite stories are fine (multiple dynamic elements in one narrative).
2. COMPANY-SPECIFIC CAUSALITY. The story arises from this company's own actions or unique position — not a sector tailwind it shares with peers.
3. FALSIFIABLE CHECKPOINTS. You must state 2-4 testable claims, each with an observable metric and a deadline (a quarter/date by which it should show in filings). If you cannot write real checkpoints, there is no narrative — REJECT.
4. EVIDENCE FROM THE COMPANY'S OWN FILINGS/CALLS ONLY — quoted from the material provided. Price action and analyst opinion are NOT evidence. If the provided material does not evidence the story, REJECT regardless of how plausible it sounds.

Be strict. Most candidates should fail. A rejected real story costs little (it can be reborn when its next catalyst files); a false narrative pollutes scoring. When unsure, REJECT.

Return ONLY valid JSON:
{"verdict": "accept" | "reject",
 "name": "<narrative name, specific, <60 chars>",            // accept only
 "thesis": "<full paragraph: the story, the mechanism, what is changing, what the market appears to miss — synthesized from the provided material>",
 "checkpoints": [{"claim": "...", "observable": "<metric/disclosure to watch>", "deadline": "YYYY-MM-DD"}],
 "evidence": [{"source": "<filing type + date>", "excerpt": "<short quote/paraphrase from the material>"}],
 "reject_reason": "<why it fails the bar>"                    // reject only
}"""


def _stock_material(engine, symbol: str) -> str:
    """The totality of recent source material for one company."""
    with engine.connect() as conn:
        themes = conn.execute(text("""
            SELECT f.filing_type, f.filing_date::date, ft.raw_themes, ft.catalysts,
                   ft.trajectory, ft.management_tone
            FROM filing_themes ft JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :s AND f.filing_date > NOW() - INTERVAL '18 months'
            ORDER BY f.filing_date DESC LIMIT 8
        """), {"s": symbol}).fetchall()
        trend = conn.execute(text("""
            SELECT period_end, revenue, op_margin, roic FROM fundamentals_history
            WHERE symbol = :s AND period_type = 'A' ORDER BY period_end DESC LIMIT 5
        """), {"s": symbol}).fetchall()
        eightks = conn.execute(text("""
            SELECT filing_date::date, LEFT(llm_analysis, 300) FROM filings
            WHERE symbol = :s AND filing_type = '8-K' AND llm_analysis IS NOT NULL
              AND filing_date > NOW() - INTERVAL '6 months'
            ORDER BY filing_date DESC LIMIT 4
        """), {"s": symbol}).fetchall()

    lines = []
    for ftype, fdate, raw, cats, traj, tone in themes:
        bits = [f"[{ftype} {fdate}]"]
        for blob in (raw, cats):
            try:
                items = blob if isinstance(blob, list) else (json.loads(blob) if blob else [])
                bits.extend(str(x) for x in items[:4])
            except Exception:
                pass
        if traj: bits.append(f"trajectory={traj}")
        if tone: bits.append(f"tone={tone}")
        lines.append(" | ".join(bits))
    if trend:
        lines.append("ANNUAL TREND (newest first): " + "; ".join(
            f"{str(r[0])[:4]}: rev {float(r[1] or 0)/1e6:,.0f}M, opm "
            f"{float(r[2] or 0)*100:.1f}%, roic {float(r[3] or 0)*100:.1f}%" for r in trend))
    for d, summ in eightks:
        lines.append(f"[8-K {d}] {summ}")
    return "\n".join(lines) or "(no material available)"


def _judge_once(client, engine, symbol: str, seed_thesis: str | None) -> dict | None:
    material = _stock_material(engine, symbol)
    seed = (f"\n\nPRIOR THESIS POINTER (from an earlier screening — verify it against "
            f"the material above; do NOT trust it blindly): {seed_thesis[:500]}"
            if seed_thesis else "")
    user = f"Company: {symbol}\n\nSOURCE MATERIAL (filings, calls, delivered numbers):\n{material}{seed}"
    from pipeline.llm_usage import record_usage
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=SONNET, max_tokens=1500, timeout=60,
                system=[{"type": "text", "text": BIRTH_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}])
            record_usage(engine, "company_narrative", SONNET, resp.usage)
            raw = resp.content[0].text.strip()
            start = raw.index("{")
            return json.loads(raw[start:raw.rindex("}") + 1])
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def birth_judge(engine, symbol: str, seed_thesis: str | None = None,
                source: str = "override") -> dict:
    """Two-vote birth. Both votes must ACCEPT for a birth; checkpoints are
    unioned, thesis taken from vote 1, evidence unioned. Every verdict is
    recorded in narrative_births."""
    from anthropic import Anthropic
    client = Anthropic()

    # One-per-company: an existing active company narrative blocks a new birth
    with engine.connect() as conn:
        existing = conn.execute(text("""
            SELECT id, name FROM narratives
            WHERE symbol = :s AND scope = 'company' AND status IN ('active','candidate')
        """), {"s": symbol}).fetchone()
    if existing:
        return {"verdict": "blocked", "reason": f"active company narrative exists: {existing[1]}"}

    v1 = _judge_once(client, engine, symbol, seed_thesis)
    v2 = _judge_once(client, engine, symbol, seed_thesis)

    def _ok(v):
        return (isinstance(v, dict) and v.get("verdict") == "accept"
                and v.get("thesis") and len(v.get("checkpoints") or []) >= 2)

    if not (_ok(v1) and _ok(v2)):
        reason = "; ".join(filter(None, [
            (v1 or {}).get("reject_reason") if not _ok(v1) else None,
            (v2 or {}).get("reject_reason") if not _ok(v2) else None,
        ])) or "one or both votes failed to produce a qualifying narrative"
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO narrative_births (symbol, source, verdict, reason)
                VALUES (:s, :src, 'rejected', :r)"""),
                {"s": symbol, "src": source, "r": reason[:800]})
        return {"verdict": "rejected", "reason": reason}

    # Birth: create the dossier
    checkpoints = (v1.get("checkpoints") or []) + [
        c for c in (v2.get("checkpoints") or [])
        if not any(c.get("claim") == d.get("claim") for d in v1.get("checkpoints") or [])]
    evidence = (v1.get("evidence") or []) + (v2.get("evidence") or [])

    with engine.connect() as conn:
        parent = conn.execute(text("""
            SELECT n.parent_id FROM narratives n
            JOIN narrative_exposures ne ON ne.narrative_id = n.id
            WHERE ne.symbol = :s AND n.tier = 'sector' LIMIT 1
        """), {"s": symbol}).fetchone()
    with engine.begin() as conn:
        nid = conn.execute(text("""
            INSERT INTO narratives (name, tier, status, thesis, scope, symbol,
                                    maturity, parent_id, momentum, falsification, created_at)
            VALUES (:n, 'candidate', 'active', :t, 'company', :s, :m, :p, 'stable',
                    :f, NOW())
            RETURNING id"""),
            {"n": v1["name"][:120], "t": v1["thesis"], "s": symbol,
             "m": BIRTH_MATURITY, "p": parent[0] if parent else None,
             "f": json.dumps({"checkpoints": [c.get("claim") for c in checkpoints]})}
        ).scalar()
        for c in checkpoints[:4]:
            conn.execute(text("""
                INSERT INTO narrative_checkpoints (narrative_id, claim, observable, deadline)
                VALUES (:n, :c, :o, NULLIF(:d,'')::date)"""),
                {"n": nid, "c": (c.get("claim") or "")[:500],
                 "o": (c.get("observable") or "")[:400], "d": (c.get("deadline") or "")[:10]})
        for e in evidence[:8]:
            conn.execute(text("""
                INSERT INTO narrative_evidence (narrative_id, symbol, source, stance,
                                                excerpt, weight, evidence_date)
                VALUES (:n, :s, :src, 'support', :x, 1.0, CURRENT_DATE)"""),
                {"n": nid, "s": symbol, "src": (e.get("source") or "birth")[:100],
                 "x": (e.get("excerpt") or "")[:600]})
        conn.execute(text("""
            INSERT INTO narrative_births (symbol, source, verdict, narrative_id, reason)
            VALUES (:s, :src, 'accepted', :n, :nm)"""),
            {"s": symbol, "src": source, "n": nid, "nm": v1["name"][:200]})
    return {"verdict": "accepted", "narrative_id": nid, "name": v1["name"],
            "checkpoints": len(checkpoints)}


def run_migration(engine) -> dict:
    """One-time: every override-corpus thesis through the birth judge with
    full source material. All verdicts recorded. (User-delegated curation.)"""
    with engine.connect() as conn:
        corpus = conn.execute(text("""
            SELECT symbol, rationale || ' Evidence: ' || COALESCE(evidence,'')
            FROM narrative_overrides
            WHERE rationale IS NOT NULL AND narrative_adjusted IS NOT NULL
            ORDER BY promoted DESC, assessed_at DESC""")).fetchall()
    stats = {"judged": 0, "accepted": 0, "rejected": 0, "blocked": 0}
    for symbol, seed in corpus:
        r = birth_judge(engine, symbol, seed_thesis=seed, source="migration")
        stats["judged"] += 1
        stats[{"accepted": "accepted", "rejected": "rejected",
               "blocked": "blocked"}[r["verdict"]]] += 1
        tag = r.get("name") or r.get("reason", "")[:70]
        print(f"  {symbol:<6} {r['verdict'].upper():<9} {tag}")
    print(f"migration: {stats}")
    return stats


def run_negative_controls(engine, controls: list[str]) -> dict:
    """Feed the judge stocks chosen for having NO plausible company story.
    Any accept = measured false positive. Does NOT create narratives —
    dry-run judging only (votes recorded to narrative_births as control)."""
    from anthropic import Anthropic
    client = Anthropic()
    fp = 0
    for sym in controls:
        v = _judge_once(client, engine, sym, None)
        accepted = (isinstance(v, dict) and v.get("verdict") == "accept")
        fp += accepted
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO narrative_births (symbol, source, verdict, reason)
                VALUES (:s, 'control', :v, :r)"""),
                {"s": sym, "v": "accepted" if accepted else "rejected",
                 "r": ("CONTROL FALSE POSITIVE: " + (v.get("name") or ""))[:300]
                      if accepted else "control correctly rejected"})
        print(f"  control {sym}: {'FALSE POSITIVE' if accepted else 'correctly rejected'}")
    rate = fp / max(1, len(controls))
    print(f"negative controls: {fp}/{len(controls)} false positives ({rate:.0%})")
    return {"controls": len(controls), "false_positives": fp, "fp_rate": rate}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    if "--migrate" in sys.argv:
        run_migration(get_engine())
