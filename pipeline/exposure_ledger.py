"""
Stateful exposure ledger — the brain's synapses get memory (user directive
2026-07-27 after the LDOS wipe: "narrative builds and shifts over time, not
start from scratch").

Replaces the weekly delete-and-rewrite exposure pass with an UPDATE pass:
  - Stocks with NO new evidence since their links were last judged: nothing
    happens. No LLM call, no change. Silence is confirmation.
  - Stocks WITH new evidence (new 10-K/Q, earnings call, classified 8-K):
    Sonnet sees the CURRENT links + ONLY the new evidence and returns change
    operations — confirm / strengthen / weaken / add / propose_remove — each
    citing the new evidence.
  - Removal requires TWO consecutive propose_remove passes (misses counter)
    or nothing is deleted. One flaky reading can weaken, never erase.
  - Stocks with no links at all still get the from-scratch judge (new
    onboardings) — narrative_exposure.run_exposure_scoring, per symbol.
Every operation is appended to exposure_history (auditable mind-changes).

Guardrails (checked by the caller after a pass): >15% of established links
changed, or any stock losing >0.3 total exposure without an earnings event,
should be surfaced loudly in the brief's SYSTEM HEALTH section.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from sqlalchemy import text

SONNET = "claude-sonnet-4-6"
MAX_WORKERS = 4

UPDATE_PROMPT = """You maintain a LIVING LEDGER of which structural narratives a company is genuinely exposed to. The ledger below is the accumulated, previously-verified state. New evidence has arrived. Your job is to UPDATE the ledger — not rebuild it.

Company: {sym} | Sector: {sector}

CURRENT LEDGER (previously verified links):
{ledger_block}

NEW EVIDENCE since the ledger was last confirmed (this is ALL that is new — judge changes ONLY from this):
{evidence_block}

AVAILABLE NARRATIVES (for 'add' operations only):
{narrative_block}

Operations you may return, one per existing/new link:
- "confirm": new evidence is consistent with the link (or says nothing about it). Silence about a link = confirm, NOT removal.
- "strengthen"/"weaken": new evidence materially changes the link's strength — give new_exposure and cite the specific new evidence.
- "add": new evidence establishes a NEW genuine, material link (bar is money, not mentions) — new_exposure 0.25-1.0, direction (beneficiary/adapting/threatened), linkage (direct/secondary/incidental), cite evidence.
- "propose_remove": new evidence CONTRADICTS the link (segment sold, program cancelled, thesis explicitly refuted). You must state what contradicts it. Absence of mention is NOT contradiction.

Rules:
- Most passes should be mostly "confirm". The ledger has memory; respect it.
- Never propose_remove because the new evidence doesn't discuss the link.
- direction/linkage changes only with cited cause.

Return ONLY a valid JSON array:
[{{"narrative_id": <int>, "op": "confirm|strengthen|weaken|add|propose_remove", "new_exposure": <float, only for strengthen/weaken/add>, "direction": "...", "linkage": "...", "evidence": "<cited from NEW evidence; required for any op except confirm>"}}]"""


def find_stocks_with_new_evidence(engine, symbols=None) -> dict:
    """{symbol: [evidence lines]} for stocks whose filings/calls are newer than
    their ledger's last_evidence_at. Stocks with no new evidence are absent."""
    sym_filter = "AND ne.symbol = ANY(:syms)" if symbols else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            WITH ledger AS (
                SELECT symbol, MIN(last_evidence_at) AS since
                FROM narrative_exposures ne2 GROUP BY symbol
            )
            SELECT ne.symbol, f.filing_type, f.filing_date::date,
                   ft.raw_themes, ft.catalysts, ft.trajectory, ft.management_tone
            FROM ledger ne
            JOIN filings f ON f.symbol = ne.symbol
                AND f.filing_date > ne.since
                AND (f.filing_type IN ('10-K','10-Q','EARN_CALL')
                     OR (f.filing_type = '8-K' AND f.event_type IS NOT NULL))
            LEFT JOIN filing_themes ft ON ft.filing_id = f.id
            WHERE 1=1 {sym_filter}
            ORDER BY ne.symbol, f.filing_date DESC
        """), {"syms": symbols} if symbols else {}).fetchall()

    out: dict[str, list] = {}
    for sym, ftype, fdate, themes, cats, traj, tone in rows:
        lines = out.setdefault(sym, [])
        if len(lines) >= 10:
            continue
        bits = [f"[{ftype} {fdate}]"]
        for blob, label in ((themes, "themes"), (cats, "catalysts")):
            try:
                items = blob if isinstance(blob, list) else (json.loads(blob) if blob else [])
                if items:
                    bits.append(f"{label}: " + "; ".join(str(x) for x in items[:4]))
            except Exception:
                pass
        if traj: bits.append(f"trajectory: {traj}")
        if tone: bits.append(f"tone: {tone}")
        lines.append(" ".join(bits))
    return out


def _load_ledger(engine, symbols) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ne.symbol, n.id, n.name, ne.exposure, ne.direction,
                   ne.linkage, ne.first_seen::date, ne.misses
            FROM narrative_exposures ne JOIN narratives n ON n.id = ne.narrative_id
            WHERE ne.symbol = ANY(:s)
        """), {"s": symbols}).fetchall()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r[0], []).append({
            "nid": r[1], "name": r[2], "exposure": float(r[3]),
            "direction": r[4] or "?", "linkage": r[5] or "?",
            "since": str(r[6]), "misses": r[7] or 0})
    return out


def run_update_pass(engine, shadow: bool = False, symbols=None) -> dict:
    """The stateful weekly pass. shadow=True: judge and record ops to
    exposure_history (trigger='shadow') but change NOTHING."""
    from anthropic import Anthropic

    new_ev = find_stocks_with_new_evidence(engine, symbols)
    if not new_ev:
        print("update pass: no stocks with new evidence")
        return {"judged": 0, "ops": {}}
    ledger = _load_ledger(engine, list(new_ev))

    with engine.connect() as conn:
        narratives = conn.execute(text(
            "SELECT id, name, tier, thesis FROM narratives WHERE status='active' ORDER BY id")).fetchall()
        sectors = dict(conn.execute(text(
            "SELECT symbol, sector FROM fundamentals WHERE symbol = ANY(:s)"),
            {"s": list(new_ev)}).fetchall())
    nar_block = "\n".join(f"{n[0]}. {n[1]} ({n[2]}): {(n[3] or '')[:160]}" for n in narratives)
    valid_ids = {n[0] for n in narratives}

    client = Anthropic()
    lock = Lock()
    stats = {"judged": 0, "confirm": 0, "strengthen": 0, "weaken": 0,
             "add": 0, "propose_remove": 0, "removed": 0, "failed": 0}

    def judge(sym):
        links = ledger.get(sym, [])
        if not links:
            return sym, None   # no ledger — from-scratch judge handles separately
        lb = "\n".join(f'- id {l["nid"]}: "{l["name"]}" exposure {l["exposure"]:.2f} '
                       f'{l["direction"]}/{l["linkage"]} (established {l["since"]}'
                       + (f', {l["misses"]} pending removal vote)' if l["misses"] else ')')
                       for l in links)
        eb = "\n".join(new_ev[sym])
        prompt = UPDATE_PROMPT.format(sym=sym, sector=sectors.get(sym),
                                      ledger_block=lb, evidence_block=eb,
                                      narrative_block=nar_block)
        for attempt in range(3):
            try:
                resp = client.messages.create(model=SONNET, max_tokens=1600, timeout=60,
                    messages=[{"role": "user", "content": prompt}])
                raw = resp.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1].removeprefix("json").rsplit("```", 1)[0]
                start = raw.index("[")
                return sym, json.loads(raw[start:raw.rindex("]") + 1])
            except Exception:
                if attempt < 2: time.sleep(2 ** attempt)
        return sym, "FAILED"

    DIRS = ("beneficiary", "adapting", "threatened")
    LNKS = ("direct", "secondary", "incidental")

    def _san_dir(v):
        """Judges sometimes return 'beneficiary/direct' — take the valid part."""
        if not v: return None
        for part in str(v).replace("/", " ").split():
            if part in DIRS: return part
        return None

    def _san_lnk(v):
        if not v: return None
        for part in str(v).replace("/", " ").split():
            if part in LNKS: return part
        return None

    def apply_ops(sym, ops):
        links = {l["nid"]: l for l in ledger.get(sym, [])}
        rows_hist, changes = [], []
        seen_ids = set()
        for o in ops:
            if not isinstance(o, dict): continue
            nid = o.get("narrative_id")
            op = o.get("op")
            if nid not in valid_ids or op not in (
                    "confirm", "strengthen", "weaken", "add", "propose_remove"):
                continue
            seen_ids.add(nid)
            cur = links.get(nid)
            if op == "add" and cur is None:
                exp = max(0.25, min(1.0, float(o.get("new_exposure") or 0)))
                if exp < 0.25: continue
                stats["add"] += 1
                rows_hist.append((sym, nid, "add", None, exp, None,
                                  _san_dir(o.get("direction")), o.get("evidence", "")))
                if not shadow:
                    changes.append(("add", nid, exp, _san_dir(o.get("direction")), _san_lnk(o.get("linkage")),
                                    o.get("evidence", "")))
            elif cur is None:
                continue
            elif op == "confirm":
                stats["confirm"] += 1
                if not shadow:
                    changes.append(("confirm", nid, None, None, None, None))
            elif op in ("strengthen", "weaken"):
                ne_val = o.get("new_exposure")
                if ne_val is None: continue
                exp = max(0.10, min(1.0, float(ne_val)))
                stats[op] += 1
                rows_hist.append((sym, nid, op, cur["exposure"], exp,
                                  cur["direction"], _san_dir(o.get("direction")) or cur["direction"],
                                  o.get("evidence", "")))
                if not shadow:
                    changes.append((op, nid, exp, _san_dir(o.get("direction")) or cur["direction"],
                                    _san_lnk(o.get("linkage")) or cur["linkage"], o.get("evidence", "")))
            elif op == "propose_remove":
                stats["propose_remove"] += 1
                will_remove = cur["misses"] + 1 >= 2
                rows_hist.append((sym, nid, "remove" if will_remove else "propose_remove",
                                  cur["exposure"], None, cur["direction"], None,
                                  o.get("evidence", "")))
                if not shadow:
                    changes.append(("remove" if will_remove else "propose_remove",
                                    nid, None, None, None, o.get("evidence", "")))
        # Links the judge didn't mention at all = implicit confirm
        for nid in links:
            if nid not in seen_ids:
                stats["confirm"] += 1
                if not shadow:
                    changes.append(("confirm", nid, None, None, None, None))

        with engine.begin() as conn:
            for (s_, n_, op_, oe, ne_, od, nd, ev) in rows_hist:
                conn.execute(text("""
                    INSERT INTO exposure_history
                        (symbol, narrative_id, op, old_exposure, new_exposure,
                         old_direction, new_direction, evidence, trigger)
                    VALUES (:s,:n,:op,:oe,:ne,:od,:nd,:ev,:tr)
                """), {"s": s_, "n": n_, "op": op_, "oe": oe, "ne": ne_,
                       "od": od, "nd": nd, "ev": (ev or "")[:500],
                       "tr": "shadow" if shadow else "update_pass"})
            if not shadow:
                now_ev = text("""UPDATE narrative_exposures SET last_confirmed=NOW(),
                    last_evidence_at=NOW(), misses=0 WHERE symbol=:s AND narrative_id=:n""")
                for (op_, nid, exp, d, l, ev) in changes:
                    if op_ == "confirm":
                        conn.execute(now_ev, {"s": sym, "n": nid})
                    elif op_ in ("strengthen", "weaken"):
                        conn.execute(text("""UPDATE narrative_exposures
                            SET exposure=:e, direction=COALESCE(:d,direction),
                                linkage=COALESCE(:l,linkage), last_confirmed=NOW(),
                                last_evidence_at=NOW(), misses=0, updated_at=NOW()
                            WHERE symbol=:s AND narrative_id=:n"""),
                            {"e": exp, "d": d, "l": l, "s": sym, "n": nid})
                    elif op_ == "add":
                        conn.execute(text("""INSERT INTO narrative_exposures
                            (symbol, narrative_id, exposure, direction, linkage, evidence,
                             updated_at, signed_at, first_seen, last_confirmed, last_evidence_at,
                             status, misses)
                            VALUES (:s,:n,:e,:d,:l,:ev,NOW(),NOW(),NOW(),NOW(),NOW(),'active',0)
                            ON CONFLICT (symbol, narrative_id) DO NOTHING"""),
                            {"s": sym, "n": nid, "e": exp, "d": d or "beneficiary",
                             "l": l or "secondary", "ev": (ev or "")[:600]})
                    elif op_ == "propose_remove":
                        conn.execute(text("""UPDATE narrative_exposures
                            SET misses=misses+1, status='waning', last_evidence_at=NOW()
                            WHERE symbol=:s AND narrative_id=:n"""), {"s": sym, "n": nid})
                    elif op_ == "remove":
                        stats["removed"] += 1
                        conn.execute(text("""DELETE FROM narrative_exposures
                            WHERE symbol=:s AND narrative_id=:n"""), {"s": sym, "n": nid})

    syms = [s for s in new_ev if ledger.get(s)]
    print(f"update pass ({'SHADOW' if shadow else 'LIVE'}): {len(syms)} stocks with "
          f"new evidence AND existing ledger")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(judge, s): s for s in syms}
        for fut in as_completed(futures):
            sym, ops = fut.result()
            with lock:
                if ops == "FAILED" or ops is None:
                    if ops == "FAILED": stats["failed"] += 1
                    continue
                stats["judged"] += 1
                apply_ops(sym, ops)

    print(f"update pass done: {stats}")
    return stats


VERIFY_PROMPT = """You are verifying the narrative-exposure ledger for a company against its own filed evidence. The ledger below was seeded by a less reliable process; your verified output replaces it.

Company: {sym} | Sector: {sector}

CURRENT (UNVERIFIED) LEDGER:
{ledger_block}

FULL EVIDENCE from this company's filings and earnings calls (most recent first):
{evidence_block}

NARRATIVES:
{narrative_block}

For each CURRENT link, and any link the evidence supports that is missing, return one op:
- "confirm" — evidence supports the link as stated
- "strengthen"/"weaken" — evidence supports it at a different strength (give new_exposure)
- "add" — evidence establishes a missing link (bar is money, not mentions; exposure 0.25-1.0)
- "remove_candidate" — the evidence does NOT support this link's existence (be strict but honest: a company scaling cruise-missile production IS a defence-rearmament beneficiary even if phrased differently)
Every op except confirm must cite specific evidence. direction: beneficiary/adapting/threatened; linkage: direct/secondary/incidental.

Return ONLY a valid JSON array:
[{{"narrative_id": <int>, "op": "...", "new_exposure": <float>, "direction": "...", "linkage": "...", "evidence": "..."}}]"""


def verify_universe(engine, symbols=None, max_workers=4) -> dict:
    """One-time (and onboarding-time) Sonnet verification of the ledger.
    Additions/strength changes apply on one vote; REMOVALS — including an
    empty verdict on a stock that has links — require a SECOND independent
    Sonnet vote to agree (the LDOS lesson: one strict reading is a coin flip).
    """
    from anthropic import Anthropic
    from pipeline.narrative_exposure import _load_narratives, _load_stock_context

    nars = _load_narratives(engine)
    nar_block = "\n".join(f"{n['id']}. {n['name']} ({n['tier']}): {(n['thesis'] or '')[:160]}"
                          for n in nars)
    valid_ids = {n["id"] for n in nars}
    ctx = _load_stock_context(engine, symbols)
    if not ctx:
        return {"verified": 0}
    ledger = _load_ledger(engine, list(ctx))
    with engine.connect() as conn:
        sectors = dict(conn.execute(text(
            "SELECT symbol, sector FROM fundamentals WHERE symbol = ANY(:s)"),
            {"s": list(ctx)}).fetchall())

    client = Anthropic()
    lock = Lock()
    stats = {"verified": 0, "confirm": 0, "strengthen": 0, "weaken": 0, "add": 0,
             "remove_confirmed": 0, "remove_vetoed": 0, "failed": 0, "second_votes": 0}
    DIRS = ("beneficiary", "adapting", "threatened")
    LNKS = ("direct", "secondary", "incidental")

    def _san(v, allowed, default):
        if not v: return default
        for part in str(v).replace("/", " ").split():
            if part in allowed: return part
        return default

    def _call(sym):
        links = ledger.get(sym, [])
        lb = "\n".join(f'- id {l["nid"]}: "{l["name"]}" exposure {l["exposure"]:.2f} '
                       f'{l["direction"]}/{l["linkage"]}' for l in links) or "(no links recorded)"
        eb = "\n".join(ctx[sym]["themes"]) or "no extracted themes"
        prompt = VERIFY_PROMPT.format(sym=sym, sector=sectors.get(sym),
                                      ledger_block=lb, evidence_block=eb,
                                      narrative_block=nar_block)
        for attempt in range(3):
            try:
                resp = client.messages.create(model=SONNET, max_tokens=2000, timeout=60,
                    messages=[{"role": "user", "content": prompt}])
                raw = resp.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1].removeprefix("json").rsplit("```", 1)[0]
                start = raw.index("[")
                out = json.loads(raw[start:raw.rindex("]") + 1])
                return out if isinstance(out, list) else None
            except Exception:
                if attempt < 2: time.sleep(2 ** attempt)
        return None

    def process(sym):
        links = {l["nid"]: l for l in ledger.get(sym, [])}
        v1 = _call(sym)
        if v1 is None:
            return sym, None
        # Empty-ledger establishment: two votes, UNIONED — single-vote
        # establishment is where the coin-flip variance lives (LDOS defence
        # link found by one vote, missed by the next). Where both votes see a
        # link, average the strengths; single-vote links survive (Sonnet adds
        # are evidence-cited) so genuine but subtly-phrased links aren't lost.
        if not links:
            v1b = _call(sym)
            with lock: stats["second_votes"] += 1
            if v1b:
                m1 = {o.get("narrative_id"): o for o in v1
                      if isinstance(o, dict) and o.get("op") == "add"}
                for o in v1b:
                    if not isinstance(o, dict) or o.get("op") != "add":
                        continue
                    nid = o.get("narrative_id")
                    if nid in m1:
                        try:
                            m1[nid]["new_exposure"] = round((float(m1[nid].get("new_exposure") or 0)
                                                            + float(o.get("new_exposure") or 0)) / 2, 2)
                        except Exception:
                            pass
                    else:
                        v1.append(o)
        ops1 = {o.get("narrative_id"): o for o in v1
                if isinstance(o, dict) and o.get("narrative_id") in valid_ids}
        # removal set: explicit remove_candidate + any existing link v1 omitted
        # entirely when v1 is otherwise empty-ish (strict-empty flip protection)
        removals = {nid for nid, o in ops1.items() if o.get("op") == "remove_candidate"}
        if links and not any(o.get("op") in ("confirm", "strengthen", "weaken")
                             for o in ops1.values()):
            removals |= set(links)   # verdict effectively empties the stock
        vetoed = set()
        if removals:
            v2 = _call(sym)   # second independent vote
            with lock: stats["second_votes"] += 1
            if v2 is not None:
                ops2 = {o.get("narrative_id"): o for o in v2 if isinstance(o, dict)}
                for nid in list(removals):
                    o2 = ops2.get(nid)
                    agrees = (o2 is None and not any(
                        x.get("op") in ("confirm", "strengthen", "weaken")
                        for x in ops2.values())) or (o2 or {}).get("op") == "remove_candidate"
                    if not agrees:
                        removals.discard(nid); vetoed.add(nid)
            else:
                vetoed |= removals; removals = set()
        return sym, (ops1, removals, vetoed)

    def apply(sym, ops1, removals, vetoed):
        links = {l["nid"]: l for l in ledger.get(sym, [])}
        with engine.begin() as conn:
            def hist(nid, op, oe, ne_, od, nd, ev):
                conn.execute(text("""INSERT INTO exposure_history
                    (symbol, narrative_id, op, old_exposure, new_exposure,
                     old_direction, new_direction, evidence, trigger)
                    VALUES (:s,:n,:op,:oe,:ne,:od,:nd,:ev,'verification')"""),
                    {"s": sym, "n": nid, "op": op, "oe": oe, "ne": ne_,
                     "od": od, "nd": nd, "ev": (ev or "")[:500]})
            for nid, o in ops1.items():
                op = o.get("op"); cur = links.get(nid)
                d = _san(o.get("direction"), DIRS, cur["direction"] if cur else "beneficiary")
                l = _san(o.get("linkage"), LNKS, cur["linkage"] if cur else "secondary")
                if op == "add" and cur is None:
                    try: exp = max(0.25, min(1.0, float(o.get("new_exposure") or 0)))
                    except Exception: continue
                    if exp < 0.25: continue
                    stats["add"] += 1
                    hist(nid, "add", None, exp, None, d, o.get("evidence"))
                    conn.execute(text("""INSERT INTO narrative_exposures
                        (symbol, narrative_id, exposure, direction, linkage, evidence,
                         updated_at, signed_at, first_seen, last_confirmed,
                         last_evidence_at, status, misses)
                        VALUES (:s,:n,:e,:d,:l,:ev,NOW(),NOW(),NOW(),NOW(),NOW(),'active',0)
                        ON CONFLICT (symbol, narrative_id) DO UPDATE SET
                            exposure=EXCLUDED.exposure, direction=EXCLUDED.direction,
                            linkage=EXCLUDED.linkage, signed_at=NOW(),
                            last_confirmed=NOW(), misses=0"""),
                        {"s": sym, "n": nid, "e": exp, "d": d, "l": l,
                         "ev": (o.get("evidence") or "")[:600]})
                elif cur is not None and op in ("confirm", "strengthen", "weaken"):
                    if op == "confirm":
                        stats["confirm"] += 1
                        conn.execute(text("""UPDATE narrative_exposures
                            SET last_confirmed=NOW(), signed_at=NOW(), misses=0
                            WHERE symbol=:s AND narrative_id=:n"""), {"s": sym, "n": nid})
                    else:
                        try: exp = max(0.10, min(1.0, float(o.get("new_exposure"))))
                        except Exception: continue
                        stats[op] += 1
                        hist(nid, op, cur["exposure"], exp, cur["direction"], d, o.get("evidence"))
                        conn.execute(text("""UPDATE narrative_exposures
                            SET exposure=:e, direction=:d, linkage=:l, signed_at=NOW(),
                                last_confirmed=NOW(), misses=0, updated_at=NOW()
                            WHERE symbol=:s AND narrative_id=:n"""),
                            {"e": exp, "d": d, "l": l, "s": sym, "n": nid})
            for nid in removals:
                cur = links.get(nid)
                if cur is None: continue
                stats["remove_confirmed"] += 1
                hist(nid, "remove", cur["exposure"], None, cur["direction"], None,
                     "verification: two independent votes found no evidentiary support")
                conn.execute(text("""DELETE FROM narrative_exposures
                    WHERE symbol=:s AND narrative_id=:n"""), {"s": sym, "n": nid})
            for nid in vetoed:
                stats["remove_vetoed"] += 1
                hist(nid, "remove_vetoed", links[nid]["exposure"] if nid in links else None,
                     None, None, None, "second vote disagreed — link retained")

    syms = list(ctx)
    print(f"VERIFICATION PASS: {len(syms)} stocks")
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process, s): s for s in syms}
        for fut in as_completed(futures):
            sym, result = fut.result()
            with lock:
                done += 1
                if result is None:
                    stats["failed"] += 1
                    continue
                stats["verified"] += 1
                apply(sym, *result)
                if done % 50 == 0:
                    print(f"  {done}/{len(syms)} verified...", flush=True)
    print(f"verification done: {stats}")
    return stats


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    if "--verify" in sys.argv:
        verify_universe(get_engine())
    else:
        run_update_pass(get_engine(), shadow="--shadow" in sys.argv)
