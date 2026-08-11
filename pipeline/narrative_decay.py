"""
Silence decay — NARRATIVE_SPEC.md Phase 1b (Open decision 6, user-approved
2026-08-11): "silence at earnings is evidence."

When an exposed company REPORTS (earnings call + quarterly filing both
ingested with themes extracted) and the report's extracted themes do not
reconfirm a narrative the company is exposed to, the weekly pass emits a
deterministic `decay` erosion op on that exposure. No LLM — theme extraction
already ran; reconfirmation is judged by embedding similarity plus the ledger.

Reconfirm definition (implementation choice, documented in NARRATIVE_SPEC
Progress; calibrated against live data 2026-08-11):
  A report event reconfirms exposure (symbol, narrative) if EITHER
  (a) the update judge emitted a cited support op (add/strengthen) for the
      pair on or after the event date — active evidence beats any heuristic; OR
  (b) max cosine similarity between the event filings' theme embeddings
      (MiniLM, same model as filing_themes.embedding) and the narrative's
      name+thesis embedding >= RECONFIRM_SIM (0.25). Calibration: judge-cited
      driven pairs median 0.42 (92% >= 0.25); random non-links median 0.25.
      Conservative on purpose: a healthy link mis-read once is only flagged;
      exposure moves only on the SECOND consecutive silent report, so the
      false-erosion rate is ~0.08^2 < 1% per two-report cycle.

Decay mechanics (the "repeated decay lowers exposure" machinery):
  - Each unreconfirmed report event appends ONE `decay` op to exposure_history
    for the pair (deduped: at most one decay per pair per event).
  - Live mode: narrative_exposures.decays += 1 and status='waning'. On the
    2nd+ consecutive decay, exposure steps down 0.25 (floor 0.10). Decay
    NEVER removes a link — removal remains the judge's two-vote job.
  - A dedicated `decays` counter is used instead of `misses`, deliberately:
    the update judge treats silence as "confirm" and resets misses=0, which
    would erase decay memory weekly; and sharing the counter would let one
    propose_remove vote plus one silent quarter trigger a removal neither
    path alone justifies. Reconfirmation (either path) resets decays=0 and
    refreshes last_confirmed.
  - If the judge already emitted ANY op for the pair since the event
    (weaken/remove included), the pair is skipped — that evidence was judged;
    decay is only for silence.

Shadow-first: default is shadow=True — history rows carry trigger='shadow'
(excluded from vital signs, replay, and every live surface) and NO exposure
row is touched. Cutover to live requires user sign-off recorded in
NARRATIVE_SPEC Progress.
"""
import json
from datetime import date, timedelta

import numpy as np
from sqlalchemy import text

RECONFIRM_SIM = 0.25      # calibrated 2026-08-11; see module docstring
REPORT_WINDOW_DAYS = 45   # call + quarterly filing must both land inside this
LOOKBACK_DAYS = 14        # weekly pass + slack; dedupe makes re-runs safe
DECAY_STEP = 0.25
EXPOSURE_FLOOR = 0.10


def ensure_columns(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE narrative_exposures
            ADD COLUMN IF NOT EXISTS decays INTEGER NOT NULL DEFAULT 0
        """))


def _report_events(conn, since: date):
    """Symbols that fully REPORTED recently: an EARN_CALL and a 10-Q/10-K,
    both theme-extracted, within REPORT_WINDOW_DAYS of each other, the later
    of the two landing on/after `since`. Returns {symbol: event_date}."""
    rows = conn.execute(text("""
        WITH themed AS (
            SELECT f.symbol, f.filing_type, f.filing_date::date AS fd
            FROM filings f
            JOIN filing_themes ft ON ft.filing_id = f.id
            WHERE f.filing_type IN ('EARN_CALL', '10-Q', '10-K')
        ),
        calls AS (SELECT symbol, MAX(fd) AS d FROM themed
                  WHERE filing_type = 'EARN_CALL' GROUP BY symbol),
        qtr AS (SELECT symbol, MAX(fd) AS d FROM themed
                WHERE filing_type IN ('10-Q', '10-K') GROUP BY symbol)
        SELECT c.symbol, GREATEST(c.d, q.d) AS event_date
        FROM calls c JOIN qtr q ON q.symbol = c.symbol
        WHERE ABS(c.d - q.d) <= :win AND GREATEST(c.d, q.d) >= :since
    """), {"win": REPORT_WINDOW_DAYS, "since": since}).fetchall()
    return {r[0]: r[1] for r in rows}


def _event_embeddings(conn, symbols, events):
    """{symbol: [embedding, ...]} for the event's themed filings."""
    if not symbols:
        return {}
    rows = conn.execute(text("""
        SELECT ft.symbol, ft.embedding, f.filing_date::date
        FROM filing_themes ft
        JOIN filings f ON f.id = ft.filing_id
        WHERE ft.symbol = ANY(:syms) AND ft.embedding IS NOT NULL
          AND f.filing_type IN ('EARN_CALL', '10-Q', '10-K')
          AND f.filing_date >= NOW() - INTERVAL '75 days'
    """), {"syms": list(symbols)}).fetchall()
    out: dict[str, list] = {}
    for sym, emb, fd in rows:
        if (events[sym] - fd).days <= REPORT_WINDOW_DAYS:
            vec = np.array(json.loads(emb) if isinstance(emb, str) else emb,
                           dtype=float)
            out.setdefault(sym, []).append(vec)
    return out


def _narrative_embeddings(nars):
    """Embed name+thesis with the same local model as filing_themes."""
    from pipeline.embedding_builder import load_model
    model = load_model()
    texts = [f"{n[1]}: {(n[2] or '')[:600]}" for n in nars]
    embs = model.encode(texts, normalize_embeddings=True,
                        convert_to_numpy=True)
    return {n[0]: embs[i] for i, n in enumerate(nars)}


def run_decay_pass(engine, shadow: bool = True) -> dict:
    """Weekly deterministic pass. shadow=True (default until user sign-off):
    log trigger='shadow' history rows only, touch no exposure."""
    ensure_columns(engine)
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    stats = {"events": 0, "pairs_checked": 0, "reconfirmed_judge": 0,
             "reconfirmed_themes": 0, "already_judged": 0, "decayed": 0,
             "exposure_lowered": 0, "shadow": shadow, "samples": []}

    with engine.connect() as conn:
        events = _report_events(conn, since)
        stats["events"] = len(events)
        if not events:
            return stats
        syms = list(events)

        nars = conn.execute(text("""
            SELECT id, name, COALESCE(thesis, description, '')
            FROM narratives WHERE status IN ('active', 'declining')
              AND COALESCE(scope, '') != 'company'
        """)).fetchall()
        nar_names = {n[0]: n[1] for n in nars}

        expo = conn.execute(text("""
            SELECT symbol, narrative_id, exposure, decays, first_seen::date
            FROM narrative_exposures
            WHERE symbol = ANY(:syms) AND narrative_id = ANY(:nids)
        """), {"syms": syms, "nids": [n[0] for n in nars]}).fetchall()

        # any ledger op for a pair on/after its event date = already judged /
        # reconfirmed / deduped (decay included — idempotent re-runs)
        hist = conn.execute(text("""
            SELECT symbol, narrative_id, op, judged_at::date
            FROM exposure_history
            WHERE symbol = ANY(:syms) AND judged_at >= :since
        """), {"syms": syms, "since": since - timedelta(days=2)}).fetchall()

        f_embs = _event_embeddings(conn, syms, events)

    support_since, judged_since = set(), set()
    for sym, nid, op, jd in hist:
        if sym in events and jd >= events[sym] - timedelta(days=2):
            judged_since.add((sym, nid))
            if op in ("add", "strengthen"):
                support_since.add((sym, nid))

    n_embs = _narrative_embeddings(nars)

    to_reconfirm, to_decay = [], []
    for sym, nid, exposure, decays, first_seen in expo:
        ev = events.get(sym)
        if ev is None or nid not in n_embs:
            continue
        if first_seen and first_seen >= ev:
            continue  # link born from this very report
        stats["pairs_checked"] += 1
        if (sym, nid) in support_since:
            stats["reconfirmed_judge"] += 1
            to_reconfirm.append((sym, nid))
            continue
        if (sym, nid) in judged_since:
            stats["already_judged"] += 1
            continue  # judge saw evidence (weaken/remove) or decay already emitted
        sims = [float(fe @ n_embs[nid]) for fe in f_embs.get(sym, [])]
        best = max(sims) if sims else None
        if best is not None and best >= RECONFIRM_SIM:
            stats["reconfirmed_themes"] += 1
            to_reconfirm.append((sym, nid))
            continue
        if best is None:
            continue  # no embedded themes for the event — cannot judge silence
        to_decay.append((sym, nid, float(exposure), int(decays or 0), ev, best))

    with engine.begin() as conn:
        for sym, nid, exposure, decays, ev, best in to_decay:
            new_decays = decays + 1
            new_exp = exposure
            if not shadow and new_decays >= 2:
                new_exp = max(EXPOSURE_FLOOR, round(exposure - DECAY_STEP, 2))
            evidence = (f"silence at earnings {ev}: extracted themes did not "
                        f"reconfirm (best similarity {best:.2f} < "
                        f"{RECONFIRM_SIM}); consecutive silent reports: "
                        f"{new_decays}")
            conn.execute(text("""
                INSERT INTO exposure_history
                    (symbol, narrative_id, op, old_exposure, new_exposure,
                     evidence, trigger, judged_at)
                VALUES (:s, :n, 'decay', :oe, :ne, :ev, :tr, NOW())
            """), {"s": sym, "n": nid, "oe": exposure, "ne": new_exp,
                   "ev": evidence,
                   "tr": "shadow" if shadow else "weekly_decay"})
            stats["decayed"] += 1
            if not shadow:
                conn.execute(text("""
                    UPDATE narrative_exposures
                    SET decays = :d, status = 'waning', exposure = :e,
                        updated_at = NOW()
                    WHERE symbol = :s AND narrative_id = :n
                """), {"d": new_decays, "e": new_exp, "s": sym, "n": nid})
                if new_exp != exposure:
                    stats["exposure_lowered"] += 1
            if len(stats["samples"]) < 12:
                stats["samples"].append(
                    f"{sym} ~ {nar_names.get(nid, nid)}: sim {best:.2f}, "
                    f"exposure {exposure:.2f}->{new_exp:.2f}, "
                    f"decays {decays}->{new_decays}")
        if not shadow and to_reconfirm:
            for sym, nid in to_reconfirm:
                conn.execute(text("""
                    UPDATE narrative_exposures
                    SET decays = 0, last_confirmed = NOW()
                    WHERE symbol = :s AND narrative_id = :n AND decays > 0
                """), {"s": sym, "n": nid})
    return stats


if __name__ == "__main__":
    import sys
    from pipeline.hidden_gem_scorer import get_engine
    shadow = "--live" not in sys.argv
    out = run_decay_pass(get_engine(), shadow=shadow)
    for k, v in out.items():
        if k != "samples":
            print(f"{k}: {v}")
    for s in out["samples"]:
        print(" ", s)
