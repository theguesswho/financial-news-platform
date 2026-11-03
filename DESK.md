# DESK — shared board (Grok / Claude / Edmund)

Updated 2026-11-03 (INCIDENT: evening boards on the previous session's closes, below). Previous: 2026-11-01 (INCIDENT: second scheduler, below). Previous: 2026-10-09 (CLAUDE_TASKS T1: deploy triggers + E_DIAG).
**Rule:** any sitting that changes plans or status updates this file
in the same PR. Chat-only status essays do not count.

## INCIDENT 2026-11-03 — evening boards scored on the previous session's closes (21 Sep → 3 Nov 2026)

**Status: fix LIVE — pushed 3 Nov 14:20:54 UTC (cf87d80, Edmund at the
dashboard); deploy SUCCESS 14:23:36.** Read-back 14:23–14:25 UTC: origin
main = cf87d80; /health/platform 200 with the coverage check live (819 of
821 names have the 2 Nov close); API /board 200 (61 board rows); site root
and /changed 200; /ops/backlog 200 in 0.95 s, no 8-K line; 30 s lock watch
clean (0 blocked, 0 waiting locks, no long or idle transactions, no live
run). Platform note **id 10 inserted** (active 3–17 Nov), read back
identical to the draft below. Proof still pending: tonight's 22:00 step 1
must store the 3 Nov close for ~820 names; tomorrow's 06:00 step 1 must
show "corrected (refreshed 2026-11-02, 2026-11-03)".

**What.** `pipeline/prices.py` passed `end=date.today()` to Yahoo; Yahoo's
`end` is exclusive. At the 22:00 UTC after-close, today IS the session that
just closed, so it was never stored; the ~820 names' closes arrived at the
next 06:00 daily. SPY alone was stored at 22:00 (the benchmark fetch has no
`end`), so every MAX(date) check — sentinel, `/health/platform` — read
"fresh". The scorer's own SPY download (gap score) had the same `end=today`.
DATA_SCORECARD stated "same evening (22:00 run)": a stated latency that was
false = incident (CLAUDE.md data rule 2).

**Since when.** R1 (pushed 20 Sep) retired the FMP price writer, which had
written each session's closes the same evening (60-day series, no `end`,
in after-close step 3b before scoring). First affected evening: Mon 21 Sep.
Proof: stored volumes match FMP, not Yahoo, on 20 Aug / 2 Sep / 10 Sep /
18 Sep (0–1 of 20 sample names match Yahoo) and match Yahoo on 21 Sep,
23 Sep, 8 Oct, 20 Oct (17–19 of 20). On all 22 October sessions SPY's row
(written at 22:00) was inserted before every other name's row of the date.
2 Nov: after-close step 1 "0 price records added" (40 min); eod_prices held
one row (SPY) for 2 Nov until 06:00 on 3 Nov.

**Effects.**
- Evening boards (after-close step 4) and the session report editions
  built on them: previous session's closes, ~30 evenings. Morning boards
  were right — the offline replay with Monday's closes reproduces the
  stored 3 Nov morning board exactly (821 of 821 to 4 dp).
- Size on one evening (offline, read-only, today's inputs; closes through
  Fri 30 Oct vs through Mon 2 Nov): score moved for 609 of 821 names,
  median 0.019 points (10-point scale), largest SMCI 4.27 → 4.46. Raw band
  crossings: STX, FFIV, CF up into Watch; PSN, ALSN, FLS, LHX below the
  Watch entry line (all four stay on the board by exit hysteresis).
- Assessor: the trigger's "MARKET REACTION: the stock moved X% on the
  latest session" quoted the previous session. 2 Nov: ON's upgrade
  rationale tied Friday's −4.7% to Monday's Synaptics announcement (ON's
  Monday move: −2.2%); FN's called Friday's −6.1% "the session move" (FN's
  Monday move, still pre-release: −3.8%). REPLAY (platform assessor,
  read-only, as-of 2 Nov 23:58 context, 3 runs per variant, llm_usage not
  written, ≈$0.20): ON Buy (upgrade) 6 of 6, FN Strong Buy (hold) 6 of 6,
  with the Friday move and with the Monday move — neither verdict changes.
  Their scores do not depend on the closes (identical before/after).
- Found in passing: 22 Sep 2026 has closes for 80 names only (outside the
  7-day window). The old writer could not fill a hole once later rows
  existed (per-row flush + rollback discarded the earlier new row). Filling
  22 Sep is Edmund's call; not done.

**Fix (local; one commit).**
- `pipeline/trading_days.py` (new): one NYSE calendar for pipeline + API
  (`api/trading_days.py` imports it; its due-session rule is unchanged,
  checked hour by hour against HEAD). `last_closed_session` /
  `yahoo_end` = the day after the last closed session (16:15 ET). Eastern
  time from the tz database, with a built-in rule as fallback.
- `pipeline/prices.py`: `end = yahoo_end`; no row dated after the last
  closed session; set-based upserts (holes in the window fill);
  `refresh_sessions=2` on the 06:00 run overwrites the last two sessions
  when Yahoo's values changed (SPY included). On an ex-dividend date this
  moves the dividend step one session earlier in the stored series;
  multi-month returns are unchanged.
- `pipeline/hidden_gem_scorer.py`: the gap score's SPY download uses
  `yahoo_end` too (the benchmark must cover the same sessions as the
  stocks — coherence). Data-timing fix, no formula change.
- Coverage check (`pipeline/freshness_sentinel.price_coverage`): ≥ 95% of
  the names that traded in the prior 14 days (ETFs and benchmarks
  excluded) must have the session's close. In the 06:00 sentinel, at the
  end of 22:00 step 1 (step FAILED by name, run degraded) and in
  `/health/platform` (503 when short).
- `/ops/backlog`: 8-Ks out of "filings without analysis" (they are
  classified, never theme-extracted); hard 45 s deadline → 503 naming the
  section it was stuck in. The two overnight failures were most likely the
  connection, not the SQL (every section ran in ≤ 6 s by hand; the page
  answered in 0.9 s at 13:34 UTC; Railway logs would prove it). `api/deps.py`: connect_timeout 10 s,
  tcp_user_timeout 30 s, TCP keepalives — a silently dropped connection
  now fails in ~30 s instead of ~15 min (this part cannot be reproduced
  locally; the deadline can, and is tested).
- Brief/sentinel print a coverage alarm without "age None".

**Proof.** `scripts/test_price_freshness.py` 37/37 (throwaway PG 18; HEAD's
price code run on the same inputs stores 0 of 3 Monday closes and leaves
the hole; the fixed code stores 3 of 3, fills it, never stores a partial
bar, corrects only the last two sessions in the morning; coverage fails on
the 2 Nov 22:00 state where MAX(date) passed; health 503 on SPY-only;
backlog 503 in 3 s stuck behind a lock and on a dead connection;
DDL lint clean). `scripts/test_scheduler_guard.py` 12/12.

**Platform note — INSERTED 3 Nov as id 10 (Edmund's word), active 3–17 Nov.**
Suggested window: active_from = push date, active_to = push date + 14 days.
> From 21 Sep to 3 Nov 2026 our evening run (22:00 UTC) scored the board
> on the PREVIOUS session's closing prices: a vendor date cut-off left out
> the session that had just closed. Morning boards (06:00 UTC) used the
> correct closes. In that window, a "session move" quoted in an evening
> verdict was the previous session's move, not the market's reaction to
> that day's news, and part of any score change between an evening board
> and the next morning's board is one session of prices arriving late.
> This is about OUR data timing, not the company.
(If the push lands later than 3 Nov, the end date changes to the push date.)

## INCIDENT 2026-11-01 — a second scheduler on the production database (25 Jun → 1 Nov 2026)

**What.** A second Railway project, `protective-cooperation`, deployed every
push of this repo from 2026-06-25 13:58 UTC (db0eb5c "Add cloud scheduler for
Railway", 17 min before `friendly-wisdom` existed) to 2026-10-31 (28bcbbd):
195 deployments (GitHub deployment records, read 2026-11-01). One service,
`financial-news-platform`; start command empty (Dockerfile CMD =
`python scheduler_light.py`); variables ANTHROPIC_API_KEY, DATABASE_URL,
FMP_API_KEY only — **no FILING_THEMES_RUBRIC_ERA**. Same database. It ran
every daily, after-close and weekly job a second time.

**Proof.**
- Step 8c (only writer of `env_diagnostics` freshness rows) ran twice on 91
  of 97 recorded dailies, 25 Jul → 1 Nov, and on every day 19–24 Jul.
- 2026-11-01 06:00: two pre-flight rows 119 ms apart; 42 `scheduler_steps`
  rows (two of every step); 4d unique-key and 5b3 lock-timeout failures are
  the two copies colliding.
- `protective-cooperation` deploy 200370ca log: E_DIAG 2026-11-01 06:58 UTC,
  `era_env` null, 806 qualifiers, via
  `score_all_stocks < _score_and_archive < daily_data_update`.
- Already seen once, never traced: R1 comment (2026-09-20) "15–17 Sep 2026
  were only filled by a second writer".

**Effects.**
- **Board provenance is mixed from 25 Jun.** The archive upserts every row,
  so each day's board is whichever copy archived last.
  - 25 Jun → 22 Aug (51 board days): no era variable existed; both copies
    computed the same E. Provenance mixed, values not.
  - 23 Aug → 1 Nov (68 board days): **27 mixed-era boards, 41 era-2 boards,
    31 flips** — this IS the T2 "E flap". Signature: the T2 sentinel names
    sit at narrative_score exactly 0.1000 on era-2 boards, ≈0.15 on mixed.
    Mixed-era days: 08-25; 09-05..09-08; 09-11, 09-20, 09-22, 09-25, 09-26,
    09-27, 09-29, 09-30; 10-01, 10-03, 10-05, 10-09, 10-10, 10-16, 10-19,
    10-20, 10-21, 10-23, 10-26, 10-28, 10-31; 11-01.
  - Everything else the scheduler writes is duplicated or last-writer-wins
    for the same period: editions, assessor verdicts, extraction/ledger
    calls, after-close lots (4t), FMP calls.
- **LLM spend** doubled wherever a step is not idempotent (1 Nov: ≈$3 of
  $8.93 was the second copy). Ledger and console totals since June include it.
- **Possible contributors, NOT proven:** FMP 429 evenings (#25 — two copies
  double the FMP call rate); the 09-09 / 09-14 lock outages (two schedulers
  contending for the same tables).
- **Never backfill** the mixed-era boards; platform_notes carries the record.

**Shutdown.** GitHub repo disconnected and deployment removed in
`protective-cooperation` on 2026-11-01 — CONFIRMED by Edmund; its last
GitHub deploy record now reads `inactive` and the 7ee40af push created none. First single-copy run: Mon 2 Nov 06:00 UTC.

**Guard — `014d1dc`, LIVE on prod since 2026-11-01 (pushed as `7ee40af` with the docs commits, Edmund-authorised; Railway deploy record 12:46:27 UTC friendly-wisdom only — protective-cooperation got none; migration applied ~2 min after push). Read-back 12:49 UTC: origin 7ee40af; `scheduler_runs.owner` + `heartbeat_at` present; /health/platform 200 ok; /board 200 (63); /ops/backlog 200, no error keys; 30-s lock watch clean; no catch-up run fired; 0 duplicate alarms. Pre-flight instance stamp first appears Mon 2 Nov 06:00. Dashboard service states: Edmund to confirm.** One owner per run slot:
`_run_job_recorded` claims the `scheduler_runs` row atomically; the owner
heartbeats every 60 s; a second instance finding a live claim stands down
and writes `env_diagnostics` 'duplicate_scheduler' naming both instances;
claims silent 300 s are dead (rescue still works); fail-open on an
un-migrated DB. Columns `owner`, `heartbeat_at` via db/migrate.py.
Instance tag on claim, pre-flight row and start-up banner.
`scripts/test_scheduler_guard.py` (throwaway Postgres, real workers): 12/12.
Takes effect only after a scheduler restart, i.e. a push in a clear window.
Follow-up: surface 'duplicate_scheduler' in /health/platform and the brief.

**Monday 2 Nov — first era-2-only board** (real scorer run twice on 1 Nov
data, archive hysteresis vs the 1 Nov board; the mixed recompute matched
the archived 1 Nov tiers on 821/821):
- Story score moves for 800 of 821 names: median 0.12, max 0.95 on the
  10-point scale; none reaches the 1.0 E-only wake line.
- Exit: CF (Watch, 3.40 → 3.17, under the 3.2 exit line).
- ADBE, AM: Buy → raw Watch inside the 10% corridor → HELD, assessor
  materiality ruling on Monday's run.
- TPL (raw SB → Buy), INTU (raw Buy → Watch): already displayed at the
  lower tier — no visible change.
- No entries, no upgrades. Monday's own data will add ordinary moves.

**Read back Mon 2 Nov 06:00:** one pre-flight row (instance
`friendly-wisdom/...` once the guard is live), 21 step rows, one freshness
row, no 4d/5b3 race failures, sentinels at 0.1000, no
'duplicate_scheduler' rows.

**platform_notes** id 9 INSERTED 2026-11-01 (Edmund-approved text, active
2026-06-25 → 2026-11-15), read back identical; active on Mon 2 Nov with id 8.

## Status

- **Prod SHA:** `4eca961` on `main` (CLAUDE_TASKS T1 E_DIAG, pushed
  2026-10-09 12:11 UTC by Edmund's `push`). Railway: scheduler
  `48a07afb`, api `6b382ad6`, impartial-heart `7242207a` — all
  SUCCESS; web not rebuilt. Prod check 12:22 UTC: /health/platform
  200 `ok` (no failing checks), /board 200 (2026-10-09). Includes
  `e6c59d8` and `014f665`.
- **R1 (V3 #26):** SHIPPED on main. Ceilings 240 / 300 / 360 min
  (Edmund 2026-09-20: do not raise).
- **Sitting 1 (this PR):** ETF exclusion wired. GLD soft-excluded
  from score / fetch / growth / onboard / assessor / theming.
  History row stays. FMP-empty KPI logs the full list + buckets.
  `DATA_SCORECARD` "PROD STILL YAHOO" ghost corrected (prod
  2026-09-20: 830 fmp / 1 null = GLD).
- **Health / freshness:** still a prod-check item (sitting 0 did
  not hit Railway). Open freshness: unknown until Edmund reads
  `env_diagnostics`. Do not write "none open".
- **Watch-path isolation:** still OPEN. A docs-only push still
  counts as a scheduler restart until a web-only push is observed
  leaving the scheduler untouched. Every push of this PR will
  restart the scheduler.

## Active sitting

**T6 minimum set — LIVE on prod since 2026-10-31 08:31 UTC (`28bcbbd`).**
Remaining T6 items: 2, 4, 5, 8, 9, 10, 12, 14, 19 (see CLAUDE_TASKS). Files:
pipeline/run_ledger.py (new), api/routers/ops.py (new),
scripts/export_railway_logs.sh (new), scheduler_light.py, pipeline/events.py,
pipeline/llm_usage.py, pipeline/claim_extractor.py, pipeline/synopsis.py,
db/migrate.py (+3 steps: scheduler_steps, filings.backfilled,
llm_usage.budget), db/models.py, api/main.py. Verified locally: compile;
harness (degraded on failed step, degraded on billing pre-flight, helpers
no-op without a run); trigger SQL EXPLAIN on prod; /ops/backlog,
/health/platform, /board 200 on a local API; migrate dry-run = 3 new steps.
Post-push checks: scheduler + api SUCCESS; start-up log `migrate: 54
checked, 3 applied`; first run shows a pre-flight line and scheduler_steps
rows; /ops/backlog on prod with no `error` keys; /board 200.


**CLAUDE_TASKS T1 (opened 2026-10-09)** — E_DIAG logging SHIPPED in
`4eca961`. Left: set watch paths (dashboard) + markdown-only proof
push, both deferred by Edmund to another day.

**Next session, first thing (Edmund 2026-10-09):** pull the `E_DIAG`
lines from the 2026-10-09 after-close (22:00 UTC) and weekly (23:30
UTC) runs (`railway logs --service financial-news-platform`) and
report any line where `era_env` is null/empty or `clause` is `""`.
Report only — no T2 fix.

### Deploy triggers (read from `railway status --json`, 2026-10-09)

No `railway.json` / `railway.toml` / `nixpacks.toml` in the repo.
Watch paths, root dir and start command all live in the Railway
dashboard (service settings), not in a repo file.

| Service | Root | Build | Start | Watch paths NOW |
|---|---|---|---|---|
| `financial-news-platform` (scheduler) | `/` | `/Dockerfile` | `python scheduler_light.py` | `**`, `!web/**` |
| `api` | `/` | `/Dockerfile` | `uvicorn api.main:app` | `api/**`, `pipeline/**`, `db/**`, `requirements.txt` |
| `impartial-heart` (Streamlit lab bench) | `/` | `/Dockerfile` | `streamlit run ui/Home.py` | `**`, `!web/**` |
| `web` | `web` | Railpack | (default) | `web/**` |

So today: ANY push outside `web/` — markdown included — rebuilds
and restarts the scheduler AND Streamlit. `api` already skips
docs-only pushes (not yet observed). Dockerfile is `COPY . .`; only
the paths below change runtime behaviour.

What each process actually loads (static import trace + file reads,
2026-10-09): scheduler → `scheduler_light.py`, `pipeline/`, `db/`,
`config/` (tickers.txt, company_map.json), `requirements.txt`.
api → `api/`, `pipeline/`. Streamlit → `ui/`, `pipeline/`, `db/`.
Not loaded by any service: `scripts/` (deploy gate + one-off tests
only), `common/`, `scheduler.py` (legacy), every `*.md`.

**Proposed watch paths (to set in the dashboard — not yet set):**
- scheduler: `pipeline/**`, `db/**`, `config/**`, `scheduler*.py`,
  `requirements.txt`, `Dockerfile`
- api: `api/**`, `pipeline/**`, `db/**`, `config/**`,
  `requirements.txt`, `Dockerfile`
- impartial-heart: `ui/**`, `pipeline/**`, `db/**`, `config/**`,
  `requirements.txt`, `Dockerfile`
- web: `web/**` (unchanged)
None of these match `*.md`, `docs/**`, `TRIAGE_*`, `CLAUDE_TASKS.md`.
Proof still owed: a markdown-only push after T1 shows scheduler,
api and impartial-heart SKIPPED (record date + deployment ids here).
Edmund 2026-10-09: watch paths and proof push deferred to another
day; until set, every non-`web/` push restarts scheduler + Streamlit.

Evidence already on record (`railway deployment list --service api`,
read 2026-10-09): api deployment `a2c787fb-3da5-4bb8-99f1-07c4c9a66fbf`
is **SKIPPED** on 2026-09-20 13:49 UTC — api's narrow watch paths
skipped a push at least once. Not yet a proof for the scheduler or
impartial-heart (both still `**`, `!web/**`).

### E code paths (T1 item 5)

Every E computation goes through ONE function,
`hidden_gem_scorer.compute_call_vs_filing_gap`, which reads the era
from the environment at call time. The `E_DIAG` line is logged there,
so it covers every caller (two lines per full re-score: once via
`compute_narrative_score`, once for display). Callers:
- scheduler child jobs daily / after_close / weekly →
  `_score_and_archive` (tagged `run=<job>@<slot>`)
- scheduler PARENT thread `_process_job_queue` (onboarding re-score)
  → `score_all_stocks` (shows `run=adhoc`, `via=…_process_job_queue`)
- fallbacks: `leaderboard_archiver.archive_leaderboard`,
  `qual_assessor` (when no gems passed), `deep_dive_batch`,
  `shadow_lane`
- Streamlit `ui/app.py` (`load_gem_scores`, `get_gem_for`)
- legacy `scheduler.py` (launchd jobs disabled 2026-08-16)
No path computes E with its own SQL or bypasses the era clause. So
the flap is not a bypass: the clause itself must be coming out empty
in some runs (env unset/empty in that process), or the row set
differs. `E_DIAG` logs `era_env`, `clause`, `qualifiers`, `max_gap`,
`rows_by_era_in_window`, pid/ppid and the call chain to tell which.
Local check 2026-10-09 against the prod DB: era=2 → 329 qualifiers,
max gap 0.4643; unset → 806, max gap 0.55 (rows in window: era-1
4066, era-2 5092). The scorer writes nothing, so a mixed read in
Streamlit cannot reach the board.

### Lab bench (T1 item 6)

`FILING_THEMES_RUBRIC_ERA` is set ONLY on the scheduler service
(=2). It is unset on `api` and `impartial-heart`. The Streamlit
bench therefore computes E under the mixed read. Not the prod cause
(read-only), but bench and prod must agree — fix belongs in T2
(era rule enforced in the query helper, default 2).

## Next sittings (ordered)

1. **V3 #23 Gap honesty A+B** — Grok rulings locked 2026-09-08; **no
   score math**. Opens when Edmund opens it. Report-back before code.
2. **Hold for Edmund** — FMP quota redesign (#25 note) needs his plan
   tier before any code. Do **not** start #24 (freeze) or
   embeddings / decay Phase 2 / replay.

## Open incidents / parked

- **Universe-wide E flap** (was the parked 28 Sep T1; now
  CLAUDE_TASKS T2, un-parked 2026-10-09): E for ~800/822 names
  toggles between era-2 and mixed reads, on and off since 25 Sep.
  T1's `E_DIAG` line is the instrument; T2 is the fix.
  **CAUSE FOUND 2026-11-01:** the second scheduler in
  `protective-cooperation` (no era variable) — see INCIDENT above. The
  flap stops when that copy stops; T2's query-helper default still
  matters for the Streamlit bench (unset there too).
- **15–17 Sep** snapshots / editions / lots: real gap. `platform_notes`
  id 7 already labels it (active 09-15 → 09-22). **Never backfill.**
- **FMP 429 evenings** (#25 design note): parked pending Edmund's plan
  tier. Sitting 1 only *measures* empties (KPI). Not a redesign.
- **Embeddings / silence decay / NARRATIVE_SPEC Phase 2:** parked
  (V3 #0; Edmund 2026-09-05). Decay still starved.
- **Replay:** design only (`NARRATIVE_REPLAY_DESIGN.md`). Parked.
- **#24 Gap math C+D:** freeze; Edmund GATE; not next.
- **Watch-path isolation:** still unproven (CLAUDE.md / FRONTEND_SPEC).
  Docs or pipeline push = scheduler redeploy. Now CLAUDE_TASKS T1;
  current state under "Deploy triggers" above.
- **Operating-company extras** ASND, CHKP, GTLS, OZK (in fundamentals,
  not in tickers.txt): NOT ETFs. Left in place. Separate hygiene.

## Handoff

**This sitting built:** ETFs out of the live universe (pattern, not a
GLD mute). Onboard rejects ETF / grantor trust via known list + Yahoo
`quoteType` + FMP `isEtf`/`isFund`. Growth / canonical logs keep the
full empty list and classify etf / quota_429 / transport / true_hole.
Sentinel imports `pipeline.universe.ETF_SYMBOLS`. Soft exclude — no
DELETE of the GLD fundamentals row.

**Verify (after merge, on a box that can import the branch):**
1. `python -c "from pipeline.universe import ETF_SYMBOLS; assert ETF_SYMBOLS == frozenset({'GLD'})"`
2. `python scripts/test_universe_hygiene.py` — GLD dropped from
   filter/score-skip/onboard known-list; empty list of 25 not truncated;
   ASND/CHKP/GTLS/OZK stay; SPY/MDY not in ETF_SYMBOLS.
3. Onboard: `phase_validate(["GLD"])` rejects without a vendor call.
   A live ETF (any `quoteType=ETF`) is rejected when Yahoo answers.
4. After the first post-merge daily: GLD must not appear in
   `score_all_stocks` output. Growth log must print `empty=[...]` in
   full (no `[:20]`).

**Claude next:** after Edmund merges and **opens sitting 2 (#23)**.
Do not implement #23/#24, FMP quota, embeddings, scorer math, or
15–17 boards. Update `DESK.md` in that PR.

**Needs Edmund:** (1) merge this PR when ready; (2) **push only at
Railway in a clear window** — every push still restarts the
scheduler until watch paths are proven; (3) prod checks still in
`TRIAGE_2026-09-20.md` if not yet done; (4) open #23 when ready.
This PR is not a Railway deploy.
