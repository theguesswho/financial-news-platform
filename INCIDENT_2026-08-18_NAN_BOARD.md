# INCIDENT: NaN-poisoned board snapshot, 2026-08-18 — fix spec

Session opener (Edmund types exactly this, nothing more):
**"Read INCIDENT_2026-08-18_NAN_BOARD.md and continue from the Checklist."**

Status: CLOSED 2026-08-18 (22:00 after-close ran clean on guarded code;
all checklist items done with evidence below). Written 2026-08-18 ~12:00
UTC by the methodology desk with Edmund present. This spec is the ONLY
authority for the fix session.
CLAUDE.md and the STANDING BRIEF (FRONTEND_SPEC.md) bind as always.

## HARD DEADLINE
The after-close run fires **22:00 UTC today (Tue 18 Aug)** and reads the
board for the v2d lot lifecycle. On the poisoned snapshot every held name
reads "below Buy" → mass false sells into the live track record.
**If the repair is not verified complete by 21:30 UTC**, stop repairing
and ask Edmund this exact sentence: *"The board repair isn't done and the
22:00 after-close run would sell every position on false zeros — reply
PAUSE and I'll stop tonight's after-close job via Railway CLI, or reply
RISK to let it run."* Do not decide for him. Do not let 22:00 pass
silently.

## What happened (verified, don't re-litigate)
- The 06:00 UTC daily run on 2026-08-18 archived leaderboard_history
  rows for all 828 names with gap_score = NaN on 827 of them; gem
  collapsed (max 0.132), tier NULL everywhere → board count 0.
- Prod GET /board returns HTTP 500 (NaN fails JSON serialization).
  The product site is down; Streamlit board is equally empty/garbage.
- Value, quality, exposure components are INTACT and equal to 08-17.
  Only the gap/priced-in path is poisoned.
- The run itself logged "✓ 828 scored, 0 on-board" and "All sources
  fresh" and completed "successfully" — no guard exists on OUTPUT.

## Root cause (verified, reproduced locally)
pipeline/hidden_gem_scorer.py, gap computation (~lines 628–660):
`yf.download("SPY", ...)` returned a series containing a **NaN close**
(reproduced 2026-08-18: 128 rows, 1 NaN). The guard checks only
`spy_raw.empty` / `len >= 2` / `except` — a NaN passes all three, so
`spy_6m = NaN`, and NaN propagates through every symbol's price_lag →
gap_score → priced_in → ng_score → gem_score. The `if spy_6m is None`
DB fallback never triggers because NaN is not None.

## The fix — exactly three changes, in this order

### 1. Guard the input (pipeline/hidden_gem_scorer.py)
- Drop NaN closes before use: `spy_raw = spy_raw.dropna(subset=["Close"])`
  (mind the MultiIndex columns yfinance returns), THEN apply the
  existing empty/len checks.
- After computing, add: `if spy_6m is not None and not np.isfinite(spy_6m):
  spy_6m = None` so the existing DB-median fallback takes over.
- Per-symbol belt: skip any price_lag entry that is not finite.
- NOTHING else in the scorer changes. This restores the intended
  computation; it is a defect fix, not a scoring change. Any temptation
  to "improve" scoring here is OUT OF SCOPE (freeze discipline).

### 2. Guard the output (pipeline/leaderboard_archiver.py)
The systemic hole: a zeroed/NaN universe was archived and every
downstream consumer trusted it. Add a **pre-archive sanity gate**:
refuse to write the snapshot and raise loudly (so the scheduler step
FAILS, visibly) if ANY of:
- any scored component or gem_score is non-finite (NaN/inf), or
- on-board count is 0 while the previous snapshot's was > 0.
On refusal the previous day's snapshot simply remains the latest —
/board stays alive on yesterday's truth instead of dying on today's
garbage. Log line must say exactly what tripped. No auto-repair, no
silent fallback — fail loud, keep yesterday.

### 3. Repair the data (prod DB, with the FIXED code)
- Run the scorer + archiver locally against the prod DB
  (load_dotenv('/Users/eha/Desktop/financial-news-platform/.env',
  override=True)) to REGENERATE AND OVERWRITE the 2026-08-18 snapshot.
  The machinery recomputes; Claude never hand-writes scores (evidence
  integrity rule 2).
- Edmund authorized this overwrite of the poisoned 08-18 rows in the
  originating conversation (2026-08-18). That authorization covers
  exactly this snapshot, nothing else.
- Then check whether a 2026-08-18 daily_report edition was generated
  from the poisoned diff; if yes, regenerate it through
  generate_report(force=True) — through the machinery, never edited by
  hand.

## Acceptance criteria (all must hold, with evidence pasted into
## the Checklist below)
1. Local: scorer unit-run with a synthetic NaN-poisoned SPY frame
   produces finite scores via the fallback (prove the guard).
2. Prod DB: 2026-08-18 snapshot has 828 rows, zero non-finite values,
   plausible board (roughly 40±5 names; ACM/GDDY/LDOS tiers comparable
   to 08-17 unless real data moved them).
3. Prod: GET /board returns 200 and a populated board. (The prod API
   reads the DB directly — the data repair alone revives it; the code
   fix rides the next authorized push.)
4. Archive gate: feed the gate a snapshot with one NaN → it refuses
   and raises; feed it the repaired snapshot → it passes.
5. The 22:00 after-close run either runs on the repaired board or was
   PAUSED by Edmund's explicit word. Whichever happened is recorded.

## Guardrails (violating any of these ends the session)
- Scope is EXACTLY the three changes + repair above. No other V3
  items, no scoring "improvements", no report-writer changes (the
  DVA/assessor-surfacing decision is a SEPARATE assigned fix — see
  FRONTEND_SPEC), no Streamlit changes, no schema changes.
- No `git push` unless Edmund has just said "push" AND is at the
  Railway dashboard. The code fix can wait for the window; the DATA
  repair cannot (deadline above).
- Deploy-gate slots bind: no push 21:50–23:00 UTC (after-close) or
  05:50–07:00 UTC (daily).
- Kill stale :8010/:3100 before any local verify; /health 200 is not
  proof — hit /board.
- Verify every claim against the DB or prod with hard evidence before
  writing "done". Recorded ≠ fixed.
- If anything unexpected appears mid-repair (schema drift, second
  poisoned table, writes failing), STOP and report; do not improvise.

## Checklist (the session works top to bottom, records evidence inline)
- [x] 1. Guard in hidden_gem_scorer.py + synthetic-NaN proof
        (done 2026-08-18 ~12:15 UTC) dropna on Close before the existing
        empty/len checks (MultiIndex handled via ndim); non-finite spy_6m
        forced to None so the DB-median fallback fires; non-finite
        price_lag entries skipped. Proof (yf.download monkeypatched,
        compute_gap_score run against prod DB read-only):
          [one-NaN (incident shape)] symbols=843 non-finite=0 min=0.0000 max=0.8621 mean=0.4710
          [all-NaN (forces DB fallback)] symbols=843 non-finite=0 min=0.0000 max=0.8478 mean=0.4150
- [x] 2. Pre-archive sanity gate in leaderboard_archiver.py + both gate
        proofs (refuses NaN, passes clean)
        (done ~12:20 UTC) check_snapshot_sane() raises SnapshotSanityError
        before any write. Proof:
          PASS refuse-NaN: "non-finite gap_score=nan on symbol GDDY — nothing written, previous snapshot remains latest"
          PASS refuse-zero-board: "on-board count is 0 while previous snapshot had 40 names on board"
          PASS clean snapshot accepted (None components allowed)
- [x] 3. Prod snapshot 2026-08-18 regenerated; DB evidence pasted
        (done ~12:30 UTC) Ran score_all_stocks → create_table →
        archive_leaderboard → apply_qual_tiers (the scheduler's exact
        path) locally with fixed code against prod DB.
        Before: total=828 on_board=0 nan_gap=827 max_gem=0.1317
        After:  total=828 on_board=47 any_nan=0 (all 7 score columns
        scanned) max_gem=0.5196. Yesterday 08-17: on_board=46 — 47 is
        comparable (above the spec's rough 40±5 but matches yesterday's
        real board). ACM/GDDY/LDOS: Strong Buy ranks 1/2/3 on BOTH
        08-17 and 08-18 (gem 0.5178→0.5196, 0.5017→0.5101, 0.4857→0.4788).
- [x] 4. Prod /board 200 + board populated; response evidence pasted
        GET https://api-production-e885.up.railway.app/board →
        HTTP 200, 446364 bytes, 40 entries, top 3:
        ACM/GDDY/LDOS all Strong Buy.
- [x] 5. 08-18 daily_report checked; regenerated if poisoned
        08-18 edition (6 rows) created_at 2026-08-18 00:26:14 UTC —
        BEFORE the 06:00 poisoned run; min=max created_at, nothing
        written since. NOT poisoned; no regeneration needed.
- [x] 6. 22:00 outcome recorded (ran clean / PAUSED by Edmund)
        Risk surfaced to Edmund ~12:40 UTC: the 22:00 after-close job
        re-scores (scheduler_light step 4) with the then-unguarded prod
        scorer before v2d reads the board (step 4t), and yfinance SPY
        data STILL contained the NaN close (2026-08-17 row) at 12:35 UTC
        — recurrence tonight was near-certain. Edmund chose PUSH.
        Guards deployed: both Railway services SUCCESS 12:35 UTC,
        scheduler restarted on guarded code, after-close re-armed for
        22:00 today, /board 200 on the new deploy.
        OUTCOME: after-close run COMPLETED CLEAN on the guarded code —
        scheduler_runs after_close finished_at 2026-08-18 22:24:47 UTC;
        08-18 board post-run: on_board=47, nan_rows=0; /board still
        HTTP 200. No pause needed; v2d ran on a clean board.
- [x] 7. Local commit(s) made; push status stated honestly
        Commit 811985a on main (both guards). PUSHED 12:26 UTC on
        Edmund's explicit word (deploy gate: clear; outside all slots).
        Prod now runs the GUARDED scorer + archive gate — Wednesday
        06:00 exposure closed.
- [x] 8. This file's Status flipped to CLOSED with date
