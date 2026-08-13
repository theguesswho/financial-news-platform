"""
Post-birth prediction minting — NARRATIVE_SPEC Phase 3.

Company narratives are born with 2-4 falsifiable predictions and then,
until now, never gained another: zero new checkpoints through peak
earnings season once the birth queue drained. This pass makes dossiers
breathe: each NEW earnings call after a narrative's birth yields typed
claims (earnings_claims, the extractor's feed), and the strongest of
those become new checkpoints in narrative_checkpoints — the same table,
same grader, same maturity machinery as birth predictions.

Discipline (spec + evidence-integrity rules):
- Judgment surfaces see their evidence: the minting judge receives the
  narrative's thesis, its OPEN checkpoints, and the candidate claims'
  full text — it never mints from counts or labels.
- Dedupe: a claim that restates an open checkpoint is skipped (the
  judge sees the open set); a claim already minted is excluded by
  source_claim_id before the judge is ever called.
- Cap: at most MINT_CAP new minted checkpoints per narrative per
  calendar quarter (birth checkpoints don't count against it).
- Candidates: post-birth calls only, confidence >= 0.8, timeframe
  present, claim_type != 'risk' (risks are falsification material for
  Phase 5, not predictions the narrative should earn credit for).
- Company scope only — outside live scoring; no freeze ritual. Still
  shadow-first: live=False (default) proposes and writes nothing.

Run:
  python -m pipeline.checkpoint_minting            # dry run, prints proposals
  python -m pipeline.checkpoint_minting --live     # writes checkpoints
"""
import argparse
import json
import re
import time
from datetime import date, timedelta

from sqlalchemy import text

SONNET = "claude-sonnet-4-6"
MINT_CAP = 2          # minted checkpoints per narrative per quarter
MIN_CONFIDENCE = 0.8
MAX_CLAIMS_PER_SYMBOL = 12   # newest first; judge sees at most this many
OVERLAP_SKIP = 0.5    # token-Jaccard vs an open checkpoint at/above this = restatement
MAX_DEADLINE_YEARS = 3

_STOP = {"the", "a", "an", "of", "to", "in", "for", "by", "on", "at", "and",
         "or", "with", "will", "be", "is", "are", "its", "it", "that", "this",
         "as", "from", "than", "into", "over", "per"}


def _tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9.%$]+", (s or "").lower())
            if w not in _STOP}


def _restates_open(claim: str, open_texts: list) -> bool:
    """Deterministic dedupe backstop: token-Jaccard overlap between the
    proposed claim and any open checkpoint (claim + observable)."""
    t = _tokens(claim)
    if not t:
        return False
    for o in open_texts:
        u = _tokens(o)
        if u and len(t & u) / len(t | u) >= OVERLAP_SKIP:
            return True
    return False


def _valid_deadline(d) -> bool:
    """today < deadline < today + MAX_DEADLINE_YEARS. One malformed date
    must skip its own row only, never abort the batch."""
    try:
        dd = date.fromisoformat(str(d).strip())
    except (ValueError, TypeError):
        return False
    today = date.today()
    return today < dd < today + timedelta(days=365 * MAX_DEADLINE_YEARS)

MINT_SYSTEM = """You maintain the PREDICTION LEDGER of an investment research platform. A company narrative (thesis below) carries falsifiable checkpoints: claim + observable + deadline. The company has since held a NEW earnings call; management made the typed claims listed below.

Select which claims deserve to become NEW checkpoints on which narrative. Rules:

1. FALSIFIABLE ONLY. A checkpoint needs a claim, an observable (the specific metric or disclosure a future filing would show), and a deadline (YYYY-MM-DD by which it should appear in filed material, derived from the claim's timeframe; use the quarter-end plus one reporting cycle when the timeframe names a quarter or year). If you cannot derive a real deadline, skip the claim.
2. NO DUPLICATES. If a claim restates, reaffirms, extends, updates, or builds on an OPEN checkpoint (same substance, even reworded, re-guided, or with a refreshed number or timeline), SKIP it. Never mint to "reinforce", "confirm", "check", or "track" an existing checkpoint — a reaffirmation is a skip, not a mint. Only a genuinely NEW promise qualifies.
3. RELEVANT NARRATIVE ONLY. Mint a claim onto a narrative only if it would genuinely test that narrative's thesis. A claim testing none of the listed narratives is skipped.
4. AT MOST {cap} mints per narrative. Prefer specific numbers over directional talk.
5. Write the checkpoint claim in plain words, self-contained (name the metric and the level), not as a quote.

Return ONLY a valid JSON array (empty array if nothing qualifies):
[{{"narrative_id": <int>, "source_claim_id": <int>, "claim": "...", "observable": "<metric/disclosure to watch>", "deadline": "YYYY-MM-DD", "why": "<one line: what this tests in the thesis>"}}]"""


def ensure_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE narrative_checkpoints
            ADD COLUMN IF NOT EXISTS source_claim_id INT NULL
        """))


def _candidates(engine) -> dict:
    """{symbol: {"narratives": [...], "claims": [...]}} for symbols with
    at least one unminted post-birth candidate claim."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ec.id, ec.symbol, ec.call_date, ec.claim_type,
                   ec.claim_text, ec.metric, ec.direction, ec.magnitude,
                   ec.timeframe, ec.confidence
            FROM earnings_claims ec
            WHERE ec.confidence >= :minc
              AND ec.timeframe IS NOT NULL
              AND ec.claim_type != 'risk'
              AND ec.id NOT IN (SELECT source_claim_id FROM narrative_checkpoints
                                WHERE source_claim_id IS NOT NULL)
              AND EXISTS (SELECT 1 FROM narratives n
                          WHERE n.symbol = ec.symbol AND n.scope = 'company'
                            AND n.status = 'active'
                            AND ec.call_date > n.created_at::date)
            ORDER BY ec.symbol, ec.call_date DESC, ec.confidence DESC
        """), {"minc": MIN_CONFIDENCE}).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            s = out.setdefault(r[1], {"claims": [], "narratives": []})
            if len(s["claims"]) < MAX_CLAIMS_PER_SYMBOL:
                s["claims"].append({
                    "claim_id": r[0], "call_date": str(r[2]), "type": r[3],
                    "text": r[4], "metric": r[5], "direction": r[6],
                    "magnitude": r[7], "timeframe": r[8], "confidence": r[9]})
        if not out:
            return out
        for sym, s in out.items():
            narrs = conn.execute(text("""
                SELECT n.id, n.name, n.thesis, n.created_at::date
                FROM narratives n
                WHERE n.symbol = :s AND n.scope = 'company' AND n.status = 'active'
            """), {"s": sym}).fetchall()
            for nid, title, thesis, born in narrs:
                minted_q = conn.execute(text("""
                    SELECT count(*) FROM narrative_checkpoints
                    WHERE narrative_id = :n AND source_claim_id IS NOT NULL
                      AND date_trunc('quarter', created_at) = date_trunc('quarter', now())
                """), {"n": nid}).scalar()
                room = MINT_CAP - (minted_q or 0)
                if room <= 0:
                    continue
                open_cps = conn.execute(text("""
                    SELECT claim, observable, deadline FROM narrative_checkpoints
                    WHERE narrative_id = :n AND status = 'pending'
                """), {"n": nid}).fetchall()
                s["narratives"].append({
                    "narrative_id": nid, "title": title, "thesis": thesis,
                    "born": str(born), "room": room,
                    "open_checkpoints": [
                        {"claim": c, "observable": o, "deadline": str(d)}
                        for c, o, d in open_cps]})
        return {s: v for s, v in out.items() if v["narratives"]}


def run_minting(engine, live: bool = False) -> dict:
    """Judge candidate claims into checkpoint proposals; insert only if
    live=True. Returns stats + proposals for the deliverable."""
    from anthropic import Anthropic
    from pipeline.llm_usage import record_usage

    ensure_schema(engine)
    cands = _candidates(engine)
    client = Anthropic()
    proposals, errors = [], 0
    for sym, s in sorted(cands.items()):
        payload = {"symbol": sym, "narratives": s["narratives"],
                   "new_claims": s["claims"]}
        try:
            resp = client.messages.create(
                model=SONNET, max_tokens=2000,
                system=MINT_SYSTEM.format(cap=MINT_CAP),
                messages=[{"role": "user",
                           "content": json.dumps(payload, default=str)}])
            record_usage(engine, "checkpoint_minting", SONNET, resp.usage)
            txt = resp.content[0].text.strip()
            txt = txt[txt.index("["):txt.rindex("]") + 1]
            mints = json.loads(txt)
        except Exception as e:
            print(f"  {sym}: mint judge failed: {e}")
            errors += 1
            continue
        rooms = {n["narrative_id"]: n["room"] for n in s["narratives"]}
        claim_ids = {c["claim_id"] for c in s["claims"]}
        # open checkpoint texts per narrative, for the deterministic
        # restatement filter; accepted proposals join the set so one batch
        # can't mint the same substance twice either
        open_texts = {n["narrative_id"]: [f"{c['claim']} {c['observable']}"
                                          for c in n["open_checkpoints"]]
                      for n in s["narratives"]}
        for m in mints:
            nid, cid = m.get("narrative_id"), m.get("source_claim_id")
            if nid not in rooms or cid not in claim_ids or rooms[nid] <= 0:
                continue
            if not (m.get("claim") and m.get("observable") and m.get("deadline")):
                continue
            if not _valid_deadline(m["deadline"]):
                print(f"  {sym} n{nid}: skipped, invalid deadline "
                      f"{m.get('deadline')!r}")
                continue
            if _restates_open(f"{m['claim']} {m['observable']}",
                              open_texts.get(nid, [])):
                print(f"  {sym} n{nid}: skipped, restates an open checkpoint: "
                      f"{m['claim'][:80]}")
                continue
            rooms[nid] -= 1
            open_texts.setdefault(nid, []).append(
                f"{m['claim']} {m['observable']}")
            proposals.append({"symbol": sym, **m})
        time.sleep(0.2)
    if live and proposals:
        with engine.begin() as conn:
            for p in proposals:
                conn.execute(text("""
                    INSERT INTO narrative_checkpoints
                        (narrative_id, claim, observable, deadline, source_claim_id)
                    VALUES (:n, :c, :o, :d, :s)
                """), {"n": p["narrative_id"], "c": p["claim"],
                       "o": p["observable"], "d": p["deadline"],
                       "s": p["source_claim_id"]})
    stats = {"symbols_judged": len(cands), "errors": errors,
             "minted" if live else "proposed": len(proposals),
             "proposals": proposals}
    return stats


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    from pipeline.narrative_db import get_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="write minted checkpoints (default: dry run)")
    args = ap.parse_args()
    stats = run_minting(get_engine(), live=args.live)
    mode = "LIVE" if args.live else "DRY RUN"
    print(f"[{mode}] symbols judged: {stats['symbols_judged']}, "
          f"errors: {stats['errors']}")
    for p in stats["proposals"]:
        print(f"  {p['symbol']} n{p['narrative_id']} due {p['deadline']}: "
              f"{p['claim']}  [{p['observable']}] — {p['why']}")
