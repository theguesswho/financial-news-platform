"""
Narrative vital signs — NARRATIVE_SPEC.md Phase 1 (the living-narrative build).

Writes narrative_health_history: one row per narrative per week, the stored
trajectory the front page will chart ("is conviction growing?"). Observational
only — this module touches NO judgment surface, NO scoring input, NO live
narrative field. momentum_state is a shadow column left NULL until Phase 2.

Source of truth is exposure_history (append-only ledger). This table is a
DERIVED CACHE of the ledger, recomputable at any time — never an independent
authority. Every run upserts; re-running any week is safe and self-healing.

Conventions (locked in NARRATIVE_SPEC Definitions, Phase 0 sign-off 2026-08-12):
- Week = Monday-start, UTC (matches date_trunc('week')). Backfill starts
  2026-07-06 (a Monday).
- Support ops: add, strengthen. Erosion ops: weaken, remove, decay (silence
  at earnings — Phase 1b, decision 6), plus company-scope prediction misses
  (checkpoint status='missed' in the window).
  propose_remove and remove_vetoed change no exposure state and count as
  neither (a proposal is not yet an erosion; a veto retained the link).
  trigger='shadow' rows changed nothing live and are excluded everywhere.
- Breadth = DISTINCT companies contributing ops in the window, rolled up
  through the narrative's subtree (parent_id chain).
- Seeding: weeks starting before 2026-08-03 are flagged seeding=true and
  excluded from Phase 2 calibration — the ledger's first week (verification
  sweep 2026-07-27) is the instrument opening its eyes, not the world changing.

Historical state (active_exposures, exposed_board_weight, translation_share)
is reconstructed by replaying the ledger BACKWARD from the current
narrative_exposures table. The ledger is complete from 2026-07-27; state at
any boundary on/after that date is exact. Weeks ending before 2026-07-27
pre-date the ledger: state columns are NULL there (the ledger cannot say),
and op counts are honestly zero.

Implementation notes:
- exposed_board_weight = CANONICAL BOARD CONVICTION (decision 7, 2026-08-11):
  sum over DISTINCT board-member symbols (latest leaderboard_history snapshot
  on/before week end) of tier weight (Strong Buy 3 / Buy 2 / Watch 1) x the
  symbol's MAX exposure within the subtree — per-symbol max so a symbol
  exposed to several children is not double-counted. Same formula as the
  Themes map and GET /narratives; plain-lexicon label "board conviction".
- translation_share = delivered / exposed over the subtree's exposed symbols
  at week end. "Delivered" is currently a symbol-level proxy: a checkpoint
  pass (status='confirmed') on the symbol's company narrative, or an
  earnings claim graded delivered, within 100 days before week end — passes
  and delivery only, never management talk. Phase 3's minting will tie
  delivery to specific narratives; until then this is the honest floor
  (near zero today: 3 confirmed checkpoints platform-wide).
"""
from datetime import date, datetime, timedelta

from sqlalchemy import text

WEEK0 = date(2026, 7, 6)          # backfill start (Monday), per NARRATIVE_SPEC
LEDGER_START = date(2026, 7, 27)  # stateful ledger begins; state exact from here
ORGANIC_START = date(2026, 8, 3)  # weeks before this are seeding-flagged

SUPPORT_OPS = ("add", "strengthen")
EROSION_OPS = ("weaken", "remove", "decay")
TIER_W = {"Strong Buy": 3.0, "Buy": 2.0, "Watch": 1.0}  # board conviction
DELIVERY_RECENCY_DAYS = 100       # "most recent earnings evidence" window


def ensure_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS narrative_health_history (
                id                  SERIAL PRIMARY KEY,
                narrative_id        INTEGER NOT NULL REFERENCES narratives(id),
                week_start          DATE NOT NULL,
                support             INTEGER NOT NULL DEFAULT 0,
                erosion             INTEGER NOT NULL DEFAULT 0,
                breadth             INTEGER NOT NULL DEFAULT 0,
                active_exposures    INTEGER,          -- NULL = pre-ledger, unknowable
                exposed_board_weight NUMERIC(8,3),    -- NULL = pre-ledger, unknowable
                checkpoint_passes   INTEGER NOT NULL DEFAULT 0,
                checkpoint_fails    INTEGER NOT NULL DEFAULT 0,
                translation_share   NUMERIC(5,3),     -- NULL = pre-ledger or no exposed cohort
                momentum_state      VARCHAR(20),      -- shadow column; Phase 2 writes it
                seeding             BOOLEAN NOT NULL DEFAULT FALSE,
                computed_at         TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (narrative_id, week_start)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_nhh_week
            ON narrative_health_history (week_start)
        """))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _load_narratives(conn):
    """Active/declining narratives + subtree map {id: set of ids incl self}."""
    rows = conn.execute(text("""
        SELECT id, parent_id FROM narratives
        WHERE status IN ('active', 'declining')
    """)).fetchall()
    children: dict[int, list[int]] = {}
    ids = []
    for nid, pid in rows:
        ids.append(nid)
        if pid is not None:
            children.setdefault(pid, []).append(nid)

    def subtree(nid):
        out, stack = {nid}, [nid]
        while stack:
            for c in children.get(stack.pop(), []):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out

    return ids, {nid: subtree(nid) for nid in ids}


def _replay_states(conn, boundaries: list[date]) -> dict[date, dict]:
    """State {(symbol, narrative_id): exposure} at 00:00 UTC of each boundary
    date, by undoing ledger ops backward from the current narrative_exposures.
    Boundaries must be sorted ascending; dates before LEDGER_START get None."""
    state = {(r[0], r[1]): float(r[2]) for r in conn.execute(text(
        "SELECT symbol, narrative_id, exposure FROM narrative_exposures")).fetchall()}
    ops = conn.execute(text("""
        SELECT symbol, narrative_id, op, old_exposure, judged_at
        FROM exposure_history
        WHERE trigger != 'shadow'
          AND op IN ('add','strengthen','weaken','remove','decay')
        ORDER BY judged_at DESC, id DESC
    """)).fetchall()

    out: dict[date, dict] = {}
    i = 0
    for b in sorted(boundaries, reverse=True):
        cutoff = datetime(b.year, b.month, b.day)
        while i < len(ops) and ops[i][4] >= cutoff:
            sym, nid, op, old_exp, _ = ops[i]
            key = (sym, nid)
            if op == "add":
                state.pop(key, None)
            elif op == "remove":
                if old_exp is not None:
                    state[key] = float(old_exp)
            else:  # strengthen / weaken / decay
                if old_exp is not None and key in state:
                    state[key] = float(old_exp)
            i += 1
        out[b] = dict(state) if b >= LEDGER_START else None
    return out


def _board_symbols(conn, week_end: date):
    """{symbol: tier weight} for the latest board snapshot before week end."""
    row = conn.execute(text(
        "SELECT MAX(date) FROM leaderboard_history WHERE date < :d"),
        {"d": week_end}).scalar()
    if row is None:
        return {}
    return {r[0]: TIER_W.get(r[1], 0.0) for r in conn.execute(text("""
        SELECT DISTINCT ON (symbol) symbol, COALESCE(assessed_tier, tier)
        FROM leaderboard_history
        WHERE date = :d AND COALESCE(assessed_tier, tier) IS NOT NULL
        ORDER BY symbol
    """), {"d": row}).fetchall()}


def _delivered_symbols(conn, week_end: date):
    since = week_end - timedelta(days=DELIVERY_RECENCY_DAYS)
    delivered = {r[0] for r in conn.execute(text("""
        SELECT DISTINCT n.symbol
        FROM narrative_checkpoints ck
        JOIN narratives n ON n.id = ck.narrative_id
        WHERE ck.status = 'confirmed' AND n.symbol IS NOT NULL
          AND ck.status_updated >= :since AND ck.status_updated < :end
    """), {"since": since, "end": week_end}).fetchall()}
    delivered |= {r[0] for r in conn.execute(text("""
        SELECT DISTINCT symbol FROM earnings_claims
        WHERE outcome_status IN ('delivered', 'confirmed')
          AND outcome_checked_at >= :since AND outcome_checked_at < :end
    """), {"since": since, "end": week_end}).fetchall()}
    return delivered


def compute_week(engine, week_start: date) -> int:
    """Upsert one week's vital signs for every active/declining narrative."""
    week_end = week_start + timedelta(days=7)   # exclusive boundary
    seeding = week_start < ORGANIC_START

    with engine.connect() as conn:
        ids, subtrees = _load_narratives(conn)

        ops = conn.execute(text("""
            SELECT narrative_id, op, symbol FROM exposure_history
            WHERE trigger != 'shadow'
              AND judged_at >= :ws AND judged_at < :we
        """), {"ws": week_start, "we": week_end}).fetchall()

        ckpts = conn.execute(text("""
            SELECT narrative_id, status FROM narrative_checkpoints
            WHERE status IN ('confirmed', 'missed')
              AND status_updated >= :ws AND status_updated < :we
        """), {"ws": week_start, "we": week_end}).fetchall()

        state = _replay_states(conn, [week_end])[week_end]
        board = _board_symbols(conn, week_end) if state is not None else {}
        delivered = _delivered_symbols(conn, week_end) if state is not None else set()

        # index ops/checkpoints by narrative for subtree rollup
        ops_by_n: dict[int, list] = {}
        for nid, op, sym in ops:
            ops_by_n.setdefault(nid, []).append((op, sym))
        ck_by_n: dict[int, list] = {}
        for nid, status in ckpts:
            ck_by_n.setdefault(nid, []).append(status)
        state_by_n: dict[int, list] = {}
        if state is not None:
            for (sym, nid), exp in state.items():
                state_by_n.setdefault(nid, []).append((sym, exp))

    rows = []
    for nid in ids:
        tree = subtrees[nid]
        support = erosion = 0
        breadth_syms = set()
        for t in tree:
            for op, sym in ops_by_n.get(t, []):
                if op in SUPPORT_OPS:
                    support += 1
                elif op in EROSION_OPS:
                    erosion += 1
                else:
                    continue
                breadth_syms.add(sym)
        passes = fails = 0
        for t in tree:
            for status in ck_by_n.get(t, []):
                if status == "confirmed":
                    passes += 1
                else:
                    fails += 1
        erosion += fails  # company-scope prediction misses erode (Definitions)

        active = board_w = translation = None
        if state is not None:
            exposed: dict[str, float] = {}
            n_links = 0
            for t in tree:
                for sym, exp in state_by_n.get(t, []):
                    n_links += 1
                    exposed[sym] = max(exposed.get(sym, 0.0), exp)
            active = n_links
            board_w = round(sum(board[s] * e for s, e in exposed.items()
                                if s in board), 3)
            if exposed:
                translation = round(
                    len([s for s in exposed if s in delivered]) / len(exposed), 3)

        rows.append({"nid": nid, "ws": week_start, "sup": support, "ero": erosion,
                     "brd": len(breadth_syms), "act": active, "ebw": board_w,
                     "ckp": passes, "ckf": fails, "tra": translation,
                     "seed": seeding})

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO narrative_health_history
                    (narrative_id, week_start, support, erosion, breadth,
                     active_exposures, exposed_board_weight,
                     checkpoint_passes, checkpoint_fails, translation_share,
                     seeding, computed_at)
                VALUES (:nid, :ws, :sup, :ero, :brd, :act, :ebw,
                        :ckp, :ckf, :tra, :seed, NOW())
                ON CONFLICT (narrative_id, week_start) DO UPDATE SET
                    support = EXCLUDED.support, erosion = EXCLUDED.erosion,
                    breadth = EXCLUDED.breadth,
                    active_exposures = EXCLUDED.active_exposures,
                    exposed_board_weight = EXCLUDED.exposed_board_weight,
                    checkpoint_passes = EXCLUDED.checkpoint_passes,
                    checkpoint_fails = EXCLUDED.checkpoint_fails,
                    translation_share = EXCLUDED.translation_share,
                    seeding = EXCLUDED.seeding, computed_at = NOW()
            """), r)
    return len(rows)


def backfill(engine, start: date = WEEK0) -> int:
    """Recompute every week from `start` through the current week. Idempotent."""
    ensure_table(engine)
    total = 0
    ws = _monday(start)
    this_week = _monday(date.today())
    while ws <= this_week:
        n = compute_week(engine, ws)
        print(f"  vital signs {ws}: {n} narratives"
              f"{' (seeding)' if ws < ORGANIC_START else ''}")
        total += n
        ws += timedelta(days=7)
    return total


def run_vital_signs(engine=None) -> dict:
    """Weekly entry point: recompute the current and previous week (upsert —
    the in-progress week is finalized by the next run; the cache self-heals)."""
    if engine is None:
        from pipeline.hidden_gem_scorer import get_engine
        engine = get_engine()
    ensure_table(engine)
    this_week = _monday(date.today())
    prev_week = this_week - timedelta(days=7)
    n_prev = compute_week(engine, prev_week)
    n_cur = compute_week(engine, this_week)
    return {"weeks": [str(prev_week), str(this_week)],
            "rows": n_prev + n_cur}
