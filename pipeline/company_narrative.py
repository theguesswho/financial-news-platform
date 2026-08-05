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
# Amendment 2026-08-05 (data-linked maturity): the two-vote judge is the
# filter, not a quota. The weekly cap is a COST CIRCUIT-BREAKER only.
MAX_BIRTHS_PER_WEEK = 25
DAILY_JUDGE_LIMIT = 8
FP_FREEZE_RATE = 0.10      # grounding-audit failure rate that freezes births
CONTROL_WINDOW_DAYS = 45   # audits newer than this govern the freeze
GROUNDING_MIN_OVERLAP = 0.50   # per-excerpt token overlap vs source material
GROUNDED_DOSSIER_MIN = 0.50    # dossier fails audit below this grounded ratio
# Provisional corroboration curve — shadow lane (P3) calibrates these:
MATURITY_BASE = 0.10           # a born story with zero delivered numbers
MATURITY_PER_DELIVERED = 0.10  # per grounded delivered-evidence row
MATURITY_BIRTH_CAP = 0.40      # delivered-at-birth can't exceed this
CHECKPOINT_CONFIRM_BONUS = 0.15
CHECKPOINT_MISS_PENALTY = 0.25
# Story-scarcity controls RETIRED 2026-08-05 (see spec §A): every "boring"
# pick except ED/FAST turned out to carry a real filed story. The control
# question is now evidence-grounding — see run_grounding_audit.

BIRTH_SYSTEM = """You are the birth judge for a platform's COMPANY NARRATIVE layer — the strictest gate in the system. You decide whether a company has ONE genuine company-specific narrative worth tracking as a living dossier.

THE BAR (all four required — any failure means REJECT):
1. A CHANGE, NOT A DESCRIPTION. "This company has a moat / a flywheel / a monopoly" is a business description — timeless, unfalsifiable, REJECT. A narrative has direction and a timeline: an acquisition being integrated, a platform shift underway, a mix transformation, a regulatory unlock approaching. Composite stories are fine (multiple dynamic elements in one narrative).
2. COMPANY-SPECIFIC CAUSALITY. The story arises from this company's own actions or unique position — not a sector tailwind it shares with peers.
3. FALSIFIABLE CHECKPOINTS. You must state 2-4 testable claims, each with an observable metric and a deadline (a quarter/date by which it should show in filings). If you cannot write real checkpoints, there is no narrative — REJECT.
4. EVIDENCE FROM THE COMPANY'S OWN FILINGS/CALLS ONLY — quoted from the material provided. Price action and analyst opinion are NOT evidence. If the provided material does not evidence the story, REJECT regardless of how plausible it sounds. Excerpts must closely follow the wording of the provided material (they are mechanically checked against it) — never supply facts from your own knowledge of the company.

EVIDENCE TYPING (required): label every evidence row "type": "delivered" or "claim".
- "delivered" = filed, already-happened numbers: segment revenue/growth, backlog, closed transactions, margins, signed contracts with amounts.
- "claim" = management assertion, strategy language, targets, guidance, plans.
The distinction matters: management's view is not proof (a CEO is a salesman); only delivered numbers give a story weight. A story evidenced ONLY by claims can still be accepted (it will be tracked at near-zero weight until data confirms it) — but say so honestly in the typing.

Be strict. Most candidates should fail. A rejected real story costs little (it can be reborn when its next catalyst files); a false narrative pollutes scoring. When unsure, REJECT.

Return ONLY valid JSON — no preamble, no reasoning outside the JSON, start your response with {:
{"verdict": "accept" | "reject",
 "name": "<narrative name, specific, <60 chars>",            // accept only
 "thesis": "<full paragraph: the story, the mechanism, what is changing, what the market appears to miss — synthesized from the provided material>",
 "checkpoints": [{"claim": "...", "observable": "<metric/disclosure to watch>", "deadline": "YYYY-MM-DD"}],
 "evidence": [{"source": "<filing type + date>", "excerpt": "<short quote closely following the material's wording>", "type": "delivered" | "claim"}],
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


_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "over",
         "through", "their", "will", "have", "has", "are", "was", "were"}


def _norm_tokens(s: str) -> set:
    import re
    return {t for t in re.sub(r"[^a-z0-9%$.]+", " ", (s or "").lower()).split()
            if len(t) > 3 and t not in _STOP}


def excerpt_grounded(excerpt: str, material: str,
                     min_overlap: float = GROUNDING_MIN_OVERLAP) -> bool:
    """Deterministic quote-guard: the excerpt's distinctive tokens must
    materially overlap the source text. Kills world-knowledge fabrication
    (an invented merger shares almost no tokens with the real filings)
    while tolerating light paraphrase."""
    ex = _norm_tokens(excerpt)
    if not ex:
        return False
    mat = _norm_tokens(material)
    return len(ex & mat) / len(ex) >= min_overlap


def _type_and_ground(evidence: list, material: str) -> list:
    """Stamp each evidence row with grounded (deterministic) and a sanitized
    type; drop rows with no excerpt."""
    out = []
    for e in evidence:
        if not isinstance(e, dict) or not e.get("excerpt"):
            continue
        etype = "delivered" if str(e.get("type", "")).lower().startswith("d") else "claim"
        out.append({**e, "type": etype,
                    "grounded": excerpt_grounded(e["excerpt"], material)})
    return out


def birth_maturity(evidence: list) -> float:
    """Corroboration at birth: claims contribute NOTHING; only grounded
    delivered rows lift the floor. Provisional curve — P3 calibrates."""
    delivered = sum(1 for e in evidence
                    if e.get("type") == "delivered" and e.get("grounded"))
    return round(min(MATURITY_BIRTH_CAP,
                     MATURITY_BASE + MATURITY_PER_DELIVERED * delivered), 2)


def _judge_once(client, engine, symbol: str, seed_thesis: str | None,
                material: str | None = None) -> dict | None:
    material = material if material is not None else _stock_material(engine, symbol)
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
    """Amendment 2026-08-05: the freeze is governed by the GROUNDING AUDIT
    (source='audit' rows — does every dossier's evidence trace to filings?),
    not the retired story-scarcity controls. Failure rate above threshold =
    no new narratives until the judge is tightened and re-audited."""
    with engine.connect() as conn:
        total, fails = conn.execute(text("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE reason LIKE 'GROUNDING FAILURE%')
            FROM narrative_births
            WHERE source = 'audit'
              AND judged_at > NOW() - make_interval(days => :w)
        """), {"w": CONTROL_WINDOW_DAYS}).fetchone()
    return total >= 3 and (fails / total) > FP_FREEZE_RATE


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

    material = _stock_material(engine, symbol)
    v1 = _judge_once(client, engine, symbol, seed_thesis, material=material)
    v2 = _judge_once(client, engine, symbol, seed_thesis, material=material)

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
    evidence = _type_and_ground(
        (v1.get("evidence") or []) + (v2.get("evidence") or []), material)
    # Grounded and delivered rows first, so the [:8] slice keeps the best
    evidence.sort(key=lambda e: (not e["grounded"], e["type"] != "delivered"))
    if not any(e["grounded"] for e in evidence):
        # Quote-guard: both votes accepted but NO excerpt traces to the
        # provided material — the story is not evidenced, it is remembered.
        reason = "quote-guard: no cited evidence traces to the source material"
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO narrative_births (symbol, source, verdict, reason)
                VALUES (:s, :src, 'rejected', :r)"""),
                {"s": symbol, "src": source, "r": reason})
        return {"verdict": "rejected", "reason": reason}
    maturity = birth_maturity(evidence)

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
             "m": maturity, "p": parent[0] if parent else None,
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
                                                excerpt, weight, evidence_date,
                                                evidence_type, grounded)
                VALUES (:n, :s, :src, 'support', :x, 1.0, CURRENT_DATE, :et, :g)"""),
                {"n": nid, "s": symbol, "src": (e.get("source") or "birth")[:30],
                 "x": (e.get("excerpt") or "")[:600],
                 "et": e["type"], "g": e["grounded"]})
        conn.execute(text("""
            INSERT INTO narrative_births (symbol, source, verdict, narrative_id, reason)
            VALUES (:s, :src, 'accepted', :n, :nm)"""),
            {"s": symbol, "src": source, "n": nid, "nm": v1["name"][:200]})
    return {"verdict": "accepted", "narrative_id": nid, "name": v1["name"],
            "checkpoints": len(checkpoints), "maturity": maturity,
            "delivered": sum(1 for e in evidence
                             if e["type"] == "delivered" and e["grounded"]),
            "ungrounded": sum(1 for e in evidence if not e["grounded"])}


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


def process_birth_queue(engine, limit: int = DAILY_JUDGE_LIMIT) -> dict:
    """Drain pending nominations through the birth judge, oldest first.
    The two-vote judge is the filter (user 2026-08-05); MAX_BIRTHS_PER_WEEK
    is only a cost circuit-breaker — above it, nominations WAIT in the
    queue, never discarded. No-op while births are frozen."""
    create_queue_table(engine)
    stats = {"judged": 0, "accepted": 0, "rejected": 0, "blocked": 0, "waiting": 0}
    if births_frozen(engine):
        print("birth queue: FROZEN (control FP rate above threshold) — nothing judged")
        stats["frozen"] = True
        return stats
    with engine.connect() as conn:
        week_births = conn.execute(text("""
            SELECT COUNT(*) FROM narrative_births
            WHERE verdict = 'accepted' AND source IN ('override', 'event')
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


def run_grounding_audit(engine, days: int = 45) -> dict:
    """Amendment 2026-08-05: the control question is no longer 'does the
    judge invent stories for boring stocks?' (story-scarcity doesn't exist —
    LNT/AWK/WEC/CMS all had real filed stories) but 'does every dossier's
    evidence trace to the filings?'. Deterministic, no LLM: re-run the
    quote-guard over each recent birth's evidence against CURRENT source
    material. A dossier under GROUNDED_DOSSIER_MIN grounded rows fails.
    Failure rate above FP_FREEZE_RATE freezes births."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT n.id, n.symbol, array_agg(ev.excerpt)
            FROM narratives n
            JOIN narrative_evidence ev ON ev.narrative_id = n.id
            WHERE n.scope = 'company' AND n.status IN ('active','candidate')
              AND n.created_at > NOW() - make_interval(days => :d)
            GROUP BY n.id, n.symbol"""), {"d": days}).fetchall()
    if not rows:
        print("grounding audit: no recent births to audit")
        return {"audited": 0, "failures": 0, "fail_rate": 0.0}
    failures = 0
    for nid, sym, excerpts in rows:
        material = _stock_material(engine, sym)
        grounded = sum(1 for x in excerpts if excerpt_grounded(x or "", material))
        ratio = grounded / max(1, len(excerpts))
        failed = ratio < GROUNDED_DOSSIER_MIN
        failures += failed
        reason = (f"GROUNDING FAILURE: narrative {nid} only {grounded}/{len(excerpts)} "
                  f"excerpts trace to filings" if failed else
                  f"grounding ok: {grounded}/{len(excerpts)} excerpts trace to filings")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO narrative_births (symbol, source, verdict, reason)
                VALUES (:s, 'audit', :v, :r)"""),
                {"s": sym, "v": "rejected" if failed else "accepted",
                 "r": reason[:300]})
        if failed:
            print(f"  AUDIT FAIL {sym} (narrative {nid}): {grounded}/{len(excerpts)} grounded")
    rate = failures / len(rows)
    print(f"grounding audit: {failures}/{len(rows)} dossiers fail ({rate:.0%})"
          + (" — BIRTHS FROZEN" if rate > FP_FREEZE_RATE else ""))
    return {"audited": len(rows), "failures": failures, "fail_rate": round(rate, 3)}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    if "--migrate" in sys.argv:
        run_migration(get_engine())
    elif "--audit" in sys.argv:
        run_grounding_audit(get_engine())
    elif "--queue" in sys.argv:
        process_birth_queue(get_engine())
