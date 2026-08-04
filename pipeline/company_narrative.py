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
FP_FREEZE_RATE = 0.10      # control false-positive rate that freezes births
CONTROL_WINDOW_DAYS = 45   # controls newer than this govern the freeze
# Negative controls: stocks chosen for having no plausible company-specific
# change story. ATO deliberately excluded (Texas rate-case thesis was a real
# corpus entry). LNT removed 2026-08-04 after the baseline run: its filings
# contain an executed 3.4GW data-center load story (control-selection error;
# the judge's accept was CORRECT — row marked INVALIDATED in narrative_births,
# never silently deleted). Lesson: regulated utilities are no longer
# automatically story-free. Rotate only with a note here and in the spec.
CONTROLS = ["AWK", "ED", "WEC", "FAST", "CMS"]

BIRTH_SYSTEM = """You are the birth judge for a platform's COMPANY NARRATIVE layer — the strictest gate in the system. You decide whether a company has ONE genuine company-specific narrative worth tracking as a living dossier.

THE BAR (all four required — any failure means REJECT):
1. A CHANGE, NOT A DESCRIPTION. "This company has a moat / a flywheel / a monopoly" is a business description — timeless, unfalsifiable, REJECT. A narrative has direction and a timeline: an acquisition being integrated, a platform shift underway, a mix transformation, a regulatory unlock approaching. Composite stories are fine (multiple dynamic elements in one narrative).
2. COMPANY-SPECIFIC CAUSALITY. The story arises from this company's own actions or unique position — not a sector tailwind it shares with peers.
3. FALSIFIABLE CHECKPOINTS. You must state 2-4 testable claims, each with an observable metric and a deadline (a quarter/date by which it should show in filings). If you cannot write real checkpoints, there is no narrative — REJECT.
4. EVIDENCE FROM THE COMPANY'S OWN FILINGS/CALLS ONLY — quoted from the material provided. Price action and analyst opinion are NOT evidence. If the provided material does not evidence the story, REJECT regardless of how plausible it sounds.

Be strict. Most candidates should fail. A rejected real story costs little (it can be reborn when its next catalyst files); a false narrative pollutes scoring. When unsure, REJECT.

Return ONLY valid JSON — no preamble, no reasoning outside the JSON, start your response with {:
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
            # 2500 not 1500: a truncated rich ACCEPT parses as a failed vote,
            # i.e. a silent reject — the third max_tokens lesson (qual 600→
            # 1200, verify 900→2000). Rich dossiers are the expensive ones
            # to lose.
            resp = client.messages.create(
                model=SONNET, max_tokens=2500, timeout=90,
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


def births_frozen(engine) -> bool:
    """Births freeze when the negative-control false-positive rate exceeds
    FP_FREEZE_RATE over the recent control window (min 3 controls to judge).
    The judge's error rate is a measured number; above threshold, no new
    narratives are born until the prompt is tightened and controls re-run."""
    with engine.connect() as conn:
        total, fp = conn.execute(text("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE reason LIKE 'CONTROL FALSE POSITIVE%')
            FROM narrative_births
            WHERE source = 'control'
              AND judged_at > NOW() - make_interval(days => :w)
        """), {"w": CONTROL_WINDOW_DAYS}).fetchone()
    return total >= 3 and (fp / total) > FP_FREEZE_RATE


def _vote_verdict(v, ok: bool) -> str | None:
    """A per-vote label so rejections are auditable (founding-report gap)."""
    if ok:
        return None
    if v is None:
        return "vote failed (no response after retries)"
    if v.get("verdict") == "accept":
        return "accepted but dossier too thin (<2 checkpoints or no thesis)"
    return v.get("reject_reason") or "rejected without stated reason"


def birth_judge(engine, symbol: str, seed_thesis: str | None = None,
                source: str = "override") -> dict:
    """Two-vote birth. Both votes must ACCEPT for a birth; checkpoints are
    unioned, thesis taken from vote 1, evidence unioned. Every verdict is
    recorded in narrative_births."""
    from anthropic import Anthropic
    client = Anthropic()

    if source != "migration" and births_frozen(engine):
        return {"verdict": "frozen",
                "reason": "births frozen: control FP rate above threshold"}

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
        parts = []
        for label, v, ok in (("vote1", v1, _ok(v1)), ("vote2", v2, _ok(v2))):
            vr = _vote_verdict(v, ok)
            parts.append(f"{label}: {vr}" if vr else f"{label}: accepted")
        reason = " | ".join(parts)
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


def create_queue_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS narrative_birth_queue (
                id          SERIAL PRIMARY KEY,
                symbol      VARCHAR(10) NOT NULL,
                seed_thesis TEXT,
                source      VARCHAR(20) NOT NULL,
                status      VARCHAR(12) DEFAULT 'pending',
                result      TEXT,
                created_at  TIMESTAMP DEFAULT NOW(),
                judged_at   TIMESTAMP
            )"""))


def enqueue_birth(engine, symbol: str, seed_thesis: str | None, source: str) -> bool:
    """Nominate a symbol for a company-narrative birth. Cheap and idempotent:
    no LLM call here — judging happens in process_birth_queue under the
    weekly cap. Skips symbols already pending or already holding an active
    company narrative. Returns True if enqueued."""
    create_queue_table(engine)
    with engine.connect() as conn:
        dup = conn.execute(text("""
            SELECT 1 FROM narrative_birth_queue
            WHERE symbol = :s AND status = 'pending'
            UNION ALL
            SELECT 1 FROM narratives
            WHERE symbol = :s AND scope = 'company' AND status IN ('active','candidate')
            UNION ALL
            -- 30-day cooldown: a recently judged (and rejected) symbol is not
            -- re-judged daily on the same standing nomination; its next shot
            -- comes with genuinely new material or after the cooldown.
            SELECT 1 FROM narrative_births
            WHERE symbol = :s AND source != 'control'
              AND judged_at > NOW() - INTERVAL '30 days'
            LIMIT 1"""), {"s": symbol}).fetchone()
    if dup:
        return False
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO narrative_birth_queue (symbol, seed_thesis, source)
            VALUES (:s, :t, :src)"""),
            {"s": symbol, "t": (seed_thesis or "")[:1500] or None, "src": source})
    return True


def process_birth_queue(engine, limit: int = 2) -> dict:
    """Drain pending nominations through the birth judge, oldest first,
    respecting MAX_BIRTHS_PER_WEEK (accepted non-migration births in the
    last 7 days) — above the cap, nominations WAIT in the queue, they are
    not discarded. Also a no-op while births are frozen."""
    create_queue_table(engine)
    stats = {"judged": 0, "accepted": 0, "rejected": 0, "blocked": 0, "waiting": 0}
    if births_frozen(engine):
        print("birth queue: FROZEN (control FP rate above threshold) — nothing judged")
        stats["frozen"] = True
        return stats
    with engine.connect() as conn:
        week_births = conn.execute(text("""
            SELECT COUNT(*) FROM narrative_births
            WHERE verdict = 'accepted' AND source != 'migration'
              AND judged_at > NOW() - INTERVAL '7 days'""")).scalar()
        pending = conn.execute(text("""
            SELECT id, symbol, seed_thesis, source FROM narrative_birth_queue
            WHERE status = 'pending' ORDER BY id""")).fetchall()
    budget = max(0, MAX_BIRTHS_PER_WEEK - week_births)
    if not pending:
        return stats
    if budget == 0:
        stats["waiting"] = len(pending)
        print(f"birth queue: weekly cap reached ({week_births} births); "
              f"{len(pending)} nominations waiting")
        return stats

    for qid, symbol, seed, source in pending[:limit]:
        if stats["accepted"] >= budget:
            break
        r = birth_judge(engine, symbol, seed_thesis=seed, source=source)
        stats["judged"] += 1
        key = r["verdict"] if r["verdict"] in ("accepted", "rejected", "blocked") else "rejected"
        stats[key] += 1
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE narrative_birth_queue
                SET status = :st, result = :r, judged_at = NOW()
                WHERE id = :i"""),
                {"st": r["verdict"], "i": qid,
                 "r": (r.get("name") or r.get("reason") or "")[:500]})
        print(f"  birth queue {symbol} ({source}): {r['verdict'].upper()} "
              f"{r.get('name') or r.get('reason','')[:70]}")
    stats["waiting"] = max(0, len(pending) - stats["judged"])
    print(f"birth queue: {stats}")
    return stats


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


def run_negative_controls(engine, controls: list[str] | None = None) -> dict:
    """Feed the judge stocks chosen for having NO plausible company story,
    through the SAME two-vote bar as a real birth. Both votes accepting =
    a measured false positive (a control that would have been born).
    Single-vote accepts are recorded in the reason as a leading indicator.
    Does NOT create narratives — dry-run judging only. FP rate above
    FP_FREEZE_RATE freezes births (see births_frozen)."""
    from anthropic import Anthropic
    client = Anthropic()
    controls = controls or CONTROLS
    fp = 0

    def _ok(v):
        return (isinstance(v, dict) and v.get("verdict") == "accept"
                and v.get("thesis") and len(v.get("checkpoints") or []) >= 2)

    for sym in controls:
        v1 = _judge_once(client, engine, sym, None)
        v2 = _judge_once(client, engine, sym, None)
        births = _ok(v1) and _ok(v2)
        vote_accepts = int(_ok(v1)) + int(_ok(v2))
        fp += births
        if births:
            reason = ("CONTROL FALSE POSITIVE: " + (v1.get("name") or ""))[:300]
        elif vote_accepts == 1:
            reason = "control rejected at birth bar (but 1 of 2 votes accepted)"
        else:
            reason = "control correctly rejected (0/2 votes)"
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO narrative_births (symbol, source, verdict, reason)
                VALUES (:s, 'control', :v, :r)"""),
                {"s": sym, "v": "accepted" if births else "rejected", "r": reason})
        print(f"  control {sym}: {'FALSE POSITIVE' if births else 'rejected'} "
              f"({vote_accepts}/2 votes accepted)")
    rate = fp / max(1, len(controls))
    print(f"negative controls: {fp}/{len(controls)} false positives ({rate:.0%})"
          + (" — BIRTHS FROZEN" if rate > FP_FREEZE_RATE else ""))
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
    elif "--controls" in sys.argv:
        run_negative_controls(get_engine())
    elif "--queue" in sys.argv:
        process_birth_queue(get_engine())
