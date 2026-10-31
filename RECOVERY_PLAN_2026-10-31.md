# RECOVERY PLAN — issues, fixes, and the backlog (written 2026-10-31 01:30 UTC)

Edmund asked for one file: every major issue we can see, how each is fixed,
and how we fill the backlog of calls, analysis and pulls missed over the last
weeks. Facts below were read from the live DB and the repo on 2026-10-31;
nothing has been built or pushed from this plan. Owners are sittings Edmund
opens (`CLAUDE_TASKS.md`). Detail per incident lives in `V3_FIXLIST.md`.

## 0. Edmund first — before anything else runs

1. **Anthropic console:** turn on **auto-reload** (so a balance can never
   hit zero again) and a **low-balance email alert** (threshold: one week
   of spend, ~$100). Record the threshold in DATA_SCORECARD when done.
2. **The 06:00 UTC run today (31 Oct) — Edmund's decision 01:35 UTC: no
   push; the run goes unchanged, on one condition — the ledger cap.**
   Checked in code: step 4c / 3e calls `run_update_pass(eng)` with no
   limit; the function has no cap and reads no env var (the only pipeline
   switches are `EXPOSURE_LEGACY` and `RUBRIC_V2`). Dirty set right now:
   **378 symbols** (638 evidence rows), 5.1 exposures each; the judge is
   one Sonnet call per symbol with up to 3 retries. Cost today: ≈ **$6–8**
   if one call per symbol holds; ≈ $35–40 if the 20–22 Oct ratio (~7
   calls per symbol as recorded in llm_usage) repeats — the ratio could
   not be settled without the step logs. The 22:00 pass after it is
   near-zero (only new evidence). **There is no safe way to limit the
   ledger to 60 symbols without a push.** The only no-push lever is
   blanking `ANTHROPIC_API_KEY` on the scheduler service in the Railway
   dashboard (stops ALL LLM work, same state as the last nine days; 8-Ks
   stay recoverable for 90 days). Edmund decides: accept the spend or
   blank the key. Second cost of running now, flagged: the ledger judges
   287 10-Qs before their themes are extracted (section 2, drain order).
3. **`railway login` on this Mac**, then say so. First thing after: export
   the 22–31 Oct step logs and every `E_DIAG` line to
   `logs/incident_2026-10-22/` before retention ages them out (the desk
   runs `scripts/export_railway_logs.sh`, to be written in T6). T6 then
   stores per-step results in the database (`scheduler_steps`: run,
   step, started, finished, status, error, counters) so a diagnosis never
   depends on log retention again.
4. The console's 20–22 Oct spend figure, to calibrate the ledger.
5. Confirm the economy-rule wording for CLAUDE.md (T6 item 12).
6. `push` in a clear window for the T6 minimum set (section 3).

## 0b. Where we stand this minute

- Credits: restored by Edmund on 2026-10-30/31 (the key answers again). No
  LLM call has run since 2026-10-22 22:15 UTC — the first chance is the
  06:00 UTC daily on 2026-10-31.
- Scheduler: every run since 22 Oct reports `ok`. They were not ok: every
  judgment step failed inside its try/except. `/health/platform` stayed
  green. Freshness is now red on daily_brief (8.3d), 8-K filings (8.3d),
  qual_assessments (8.0d).
- Railway CLI on this Mac is logged out (`railway login` needed) — step-
  level logs since 22 Oct are unreadable to the desk until then.
- Repo: `main` = `ea3d730` + Grok's 9 Oct push (`4eca961`); four local
  docs commits ahead (`e6c59d8`, `3c581a3`, `8b3dcee`, `5bedf6d`), unpushed.

## 1. Major issues — what, why, fix, owner

| # | Issue | Evidence (31 Oct) | Root cause | Fix | Owner |
|---|---|---|---|---|---|
| 1 | **Silent LLM outage, 22 Oct 22:15 → 31 Oct** | 0 LLM calls for 9 days; assessor, extraction, claims, ledger, grading, births, editions, briefs all stopped | Anthropic credit balance exhausted; every step swallows its exception; ledger stamps `ok` | T6 1–3: `degraded` run status with failed-step list; health check on the judgment layer (llm_usage silent 26h, newest verdict/extraction > 48h); 5-token pre-flight that turns a billing 400 into a named alarm; low-balance email in the console (Edmund) | T6 |
| 2 | **8-K ingestion died with the LLM** | 0 8-Ks stored since 23 Oct (57/58/68 per day before); wire dark for 8-Ks nine days. **Recovery tested read-only 31 Oct:** `events.py` looks back 90 days and EDGAR's recent list reaches to 2013; of the top-40 board names, 19 8-Ks dated 23–30 Oct are visible on EDGAR and all 19 are absent from our DB — they will be re-fetched by the next after-close run with a working LLM; the per-day index files are not needed | `pipeline/events.py` classifies with Haiku BEFORE storing the row; a failed call = no filing | T6 7: store first, classify after; classification becomes a catch-up step that can never lose a filing. Recovered rows carry `backfilled = true` (amendment 5) | T6 |
| 3 | **Transcripts mostly missing in the peak** | 11 calls stored since 23 Oct vs 285 10-Qs; 78 10-Q filers since 23 Oct with no call since 15 Oct; 15 earlier October reporters still without a call | Unknown until the Railway log is read: LLM-gated path, EarningsCall quota, or FMP 429 fallback (the FMP quota redesign, V3 #25 note, is still unbuilt) | Read the log (needs `railway login`); if gated, same store-first fix as #2; if quota, the #25 redesign (incremental daily growth sweep, transcripts first in the budget) | T6 / #25 |
| 4 | **Spend was invisible and partly wasteful** (20–22 Oct ≈ $18–20 est., 4× baseline) | 12 of 22 Anthropic callers never record usage; assessor woke 114 symbol-days, 107 with no tier change, 76 names twice a day, 6 four times; 77 "rounding-noise" verdicts; extraction/claims/minting/grading/8-K classification uncached; no ceiling | 2 Aug directive ("every call records") never enforced; two sweeps a day; materiality corridor bypasses the 18-hour guard; no budget | T6 8–12: one `messages.create` wrapper that always records; one sweep per symbol per day, corridor honours the guard, no LLM call on a priced-in move < 0.02; caching on six modules; daily ceiling ($8, wave days $15) with a named alarm; economy rule in CLAUDE.md (Edmund's wording) | T6 |
| 5 | **Narrative-score flap (T2)** — 800 of 822 names' E toggles between two states | Toggled 11, 16, 17, 19, 22, 24 Oct; phantom "movers" wake the assessor; tier churn concentrates on toggle days | Call-vs-filing gap term reads a mixed era-1/era-2 row set on some runs despite `FILING_THEMES_RUBRIC_ERA=2`; universe-max normaliser couples every name to one extreme row | T2 A (root cause via the E_DIAG lines Grok shipped 9 Oct), B (fixed scale), C/D guards, E (noise flag on verdicts) — freeze ritual | T2 |
| 6 | **Track record silent since 18 Sep** | No v2d lot opened in six weeks; six Strong Buys today (JBL LDOS SANM FN AMKR DY) have no October lot | Step 4t failing or gated — unknown without the log | T6 5: read the 4t log, fix, open lots forward only (next-close fills from the day the signal qualified; never retro-priced) | T6 |
| 7 | **Narratives frozen** — embeddings NULL for every filing since 10 Aug (441 rows) | Decay has written 0 erosion ops since going live 21 Aug; momentum labels are July stamps (129 stable / 15 accelerating) | Step 5 embeddings parked (V3 #0); nothing embeds on ingest | T3: scoped NULL-only re-embed; embed on ingest; health check on NULL share; shadow decay replay 21 Aug → today; momentum_state shadow; Edmund decides live | T3 |
| 8 | **Management promises never graded** | 39,695 + 1,056 claims, all `pending`; believability table empty | Resolver never built | T4: due-claim resolver (met / missed / partial / not_gradable with evidence), believability per company, stock-page display; no score use until two quarters of data | T4 |
| 9 | **Report honesty** — "the market caught up" written on data noise (PTC 30 Sep, INTU 7 Sep) | VOICE template hard-wires priced_in UP = market; writer never sees which inputs moved | T5: cause record per definitive band crossing (corporate_action / company_event / assessor_verdict / measuring_stick / price / data_noise), consumed by the writer and the chart | T5 |
| 10 | **Watch-path isolation unproven** | Every push restarts the scheduler | Railway watch paths not set | T1: set paths on three services, markdown-only proof push | T1 |
| 11 | **Checkpoints overdue** | 9 pending past deadline (oldest 30 Sep); 80 due in the next 14 days | Grader stopped with the LLM; some predate it | Drains with the LLM (step 5b2); the 9 overdue need a look at why the grader skipped them | drain |
| 12 | **Five names with no closes for 7+ days** — AVB, EQR, EA, WBD, WBS | Prices stop; value/gap terms go stale | Delisting, acquisition or ticker change — unverified | One check each; retire or remap; the ETF/extras hygiene list covers the other five | hygiene |
| 13 | **Assessor skew** | In the peak fortnight 199 of 208 verdicts were "reinforcing", 7 "shifting" | Observation, not yet a diagnosis; the T2 phantom wakes inflate "reinforcing" | Re-measure after T2 and T6 9; then decide | later |
| 14 | **Edition gap** | No editions 22, 23, 26–29 Oct; no briefs 23–30 Oct | Consequence of #1 | Never regenerate past editions (dates anchor to the latest snapshot); label with a `platform_notes` row | drain |

## 2. The backlog — what was missed, whether it comes back, how

Counts as of 2026-10-31 01:30 UTC. "Mechanism" = the existing idempotent
catch-up step that repopulates it once the LLM answers. "Per run" = today's
limit; raising a limit is a code change (push).

| Missed | Since | Count | Recoverable? | Mechanism | Per run today | Priority |
|---|---|---|---|---|---|---|
| 8-K filings not stored | 23 Oct | ~9 days × ~60/day ≈ 500 | **Yes — verified 31 Oct** (90-day lookback; EDGAR recent list reaches 2013; 19/19 sampled 23–30 Oct filings visible and absent from our DB) | after-close step 3 (`run_events`) | all | 1 |
| Earnings-call transcripts | ~23 Oct | 78 10-Q filers with no call; 15 earlier reporters | **Mostly** — EarningsCall.biz / FMP keep them; needs the log to see why they stopped | after-close step 2 / daily step 4 | per quota | 1 |
| Filing analysis (wire grades, themes, synopses) | 22 Oct | 370 filings: 287 10-Q, 68 8-K, 11 calls, 4 10-K | Yes | step 4b / 3c extraction catch-up | **30 per run** → 60/day → ~6 days; raise to 100 for the drain | 2 |
| Claims extraction | 22 Oct | 209 October calls without claims | Yes | step 4a2 / 2c | small (verify the LIMIT 8 in `claim_extractor.py`) | 3 |
| Assessments | 22 Oct | 321 10-Q filers unassessed since filing; **24 of them on the board**; 25 tier movers never assessed; 47 of 53 board seats carry a pre-22-Oct verdict | Yes — board-relevant first | step 8 / 6 sweep (movers + unassessed Buy/SB), LIMIT 80 per sweep | 80 | 2 |
| Narrative ledger (exposure updates) | 22 Oct | 323 symbols with new evidence and no judgement | Yes, but the most expensive item (~7 Sonnet calls per symbol ≈ $0.10/symbol) | step 4c / 3e ledger update | all dirty symbols | 3 — board and near-board first |
| Company-narrative births | 22 Oct | 301 10-Q filers with no company narrative | Self-limiting (birth queue is a circuit-breaker cap) | step 4d | capped | 4 |
| Checkpoint minting + grading | 22 Oct | 9 overdue; 80 due in 14 days | Yes | steps 4e / 5b2 | all due | 3 |
| Daily brief | 23 Oct | 8 days | **No** (dated artefacts) | — | — | label only |
| Editions / session reports | 22 Oct | 6 weekdays | **No** (dates anchor to the latest snapshot) | — | — | label only |
| Board snapshots | — | none missing | n/a | — | — | — |
| Prices | — | none missing (5 names dead, see #12) | n/a | — | — | — |
| Growth blocks (FMP same-day numbers) | — | none missing: 87/87 October filers within 3 days | n/a | — | — | — |
| Track lots | 18 Sep | six weeks | **Forward only** — open from the first day each signal re-qualifies after the fix; no retro lots | step 4t after fix | — | T6 5 |

### Drain plan (order, batches, cost)

Estimated at the 20–22 Oct unit costs (extraction $0.021, assessor $0.014,
ledger call $0.014, 8-K classification ~$0.008, claims ~$0.02). Edmund's
console is the truth; these are planning numbers.

**Budget (amendment 7):** the drain gets its own budget — **$12/day for
seven days, separate from the normal $8/$15 ceiling** — so the ceiling
cannot halt it and the drain cannot hide normal spend. Mechanism: work on
items older than two days (or flagged `backfilled`) charges the drain
budget; same-day work charges the ceiling; both are checked by each LLM
step before it starts and both alarm by name when exhausted.

**Backfilled rule (amendment 5):** every filing recovered during the drain,
and every analysis written on one, carries `backfilled = true`. The wire
keeps the original filing date. Backfilled filings are **not events** for
the assessor: no 8-K wake, no "market reaction" line, no deferred-reaction
check, no edition "move" narration. *Desk's one disagreement, flagged:* a
board name whose latest 10-Q/10-K postdates its verdict must still be
assessed once — otherwise the 24 board names with unassessed October
10-Qs keep stale seats indefinitely. Proposed rule: the backfilled flag
suppresses event-triggered wakes; the "unassessed since filing" trigger
still fires once, and the verdict is stamped `continuity = 'catch-up'` so
the writer never calls it a reaction to news.

**Lots (amendment 6):** no new track-record lot opens until the post-drain
verification below passes; then lots open forward only.

0. **Day 0 (31 Oct):** Edmund's decision in section 0 item 2. If (b): blank
   the key on the scheduler service in a quiet window; runs keep prices,
   snapshots and 10-Q ingestion going; nothing else spends.
1. **Minimum set ships (target Sunday 1 Nov), one push, quiet window:**
   store-then-classify for 8-Ks; extraction limit 30 → 100; `degraded` run
   status + per-step results in `scheduler_steps`; pre-flight; drain
   budget + ceiling; `backfilled` flag; lot hold; **no assessor wake on an
   E-only change with no new filing or exposure change** (amendment 8);
   read-only `/ops/backlog` endpoint (amendment 10): backlog counts by
   surface, per-module LLM usage (24h / 7d), 8-Ks stored per day (14d),
   and board seats whose verdict is older than their latest filing.
2. **Phase 1 — documents back (day 1):** 8-K re-fetch + classification
   (~500 × $0.008 ≈ $4); transcripts for the 78 + 15 reporters (quota-
   bound). Verify: 8-Ks per day 23–30 Oct > 0 in `filings`, all flagged
   backfilled; the 23 Oct rows present.
3. **Phase 2 — extraction before judgement (day 1–3):** themes for the 370
   filings at 100/run (≈ $8), board and near-board filings first. *Desk's
   addition, flagged:* the ledger must run AFTER extraction — today it
   LEFT-joins `filing_themes`, so an early ledger pass would judge 287
   10-Qs on no extracted evidence and write weaker ops that later runs
   will not revisit.
4. **Phase 3 — board verdicts (day 1–3, in parallel):** the 24 board names
   with unassessed 10-Qs, the 25 unassessed movers, then the 47 stale
   seats (~100 verdicts ≈ $1.5), all stamped catch-up. Verify: no board
   seat with a verdict older than its latest filing.
5. **Phase 4 — the universe (day 3–7):** ledger for the 323 symbols,
   **top ~150 by gem first** (≈ $15), remainder over the week (≈ $17);
   claims 209 (≈ $4); checkpoint grading (9 overdue + due); births and
   minting at their caps. Verify daily on `/ops/backlog`: counts falling,
   llm_usage calls > 0 per run, drain budget under $12.
6. **Labels, not backfills:** `platform_notes` **id 8 is written (31 Oct
   01:35 UTC, active 22 Oct → 14 Nov)**: the board existed 22–30 Oct but
   its narrative and qualitative legs were stale (24 board names
   unassessed, 47 of 53 seats on pre-22-Oct verdicts); analysis, verdicts
   and 8-Ks are repopulated afterwards with original dates and the
   backfilled mark; nothing is back-dated, no edition regenerated; a
   catch-up verdict is not a reaction to news. Never regenerate editions
   or snapshots.
7. **Expected drain cost:** ≈ $45–60 in total, within the $12/day drain
   budget over the week; ≈ $25–30 if the ledger is capped to board and
   near-board names.

### Verification after the drain (the "verified, not assumed" rule)

- `filings` 8-K rows per day 23–31 Oct all > 0; `filing_themes` backlog
  < 20; `earnings_claims` October calls without claims < 10.
- Every board seat has a verdict newer than its latest 10-Q/10-K.
- `llm_usage` covers every module that called the API that day (22/22 once
  T6 8 ships).
- Freshness: no red rows; `/health/platform` ok with the new judgment-layer
  checks green.
- A `platform_notes` row labels the gap (id 8, written).
- Every recovered filing and catch-up verdict carries `backfilled` / `catch-up`; none of them triggered an edition move.
- Only after all of the above: the lot hold is lifted (T6 5).

## 3. Order of work and what needs Edmund

1. **Edmund now:** section 0 — console auto-reload + low-balance email; the
   decision on today's run; `railway login`; the console's 20–22 Oct figure;
   the economy-rule wording; a push window for the T6 minimum set.
2. **Logs first** once logged in: export 22–31 Oct step logs + E_DIAG to
   `logs/incident_2026-10-22/`.
3. **T6 minimum set** (one push), then the rest of T6: ledger coverage;
   assessor economy; caching; `scheduler_steps`; lots.
4. **Drain** per section 2, in batches, verified daily on `/ops/backlog`.
5. **T2** (flap root cause + fixed scale + guards + noise flag), freeze ritual.
6. **T3** (re-embed, shadow decay) — before the next reporting peak.
7. **T4** (claims resolver) — in time to grade October promises against
   January 10-Qs.
8. **T5** (why-did-it-move record + chart markers), **T1** (watch paths)
   when convenient.

## 4. Standing lessons this plan encodes

- A run is `ok` only when every step completed; a swallowed exception is a
  `degraded` run with a name attached.
- Ingestion never depends on a judgment call: store the document, judge it
  afterwards.
- The alarm lives outside the thing it watches, and it watches the judgment
  layer, not just the scheduler's pulse.
- Credits are a scoring input: recorded per call, capped per day, alarmed
  by name, and never spent twice on the same evidence.
- Gaps in dated artefacts are labelled, never backfilled; recovered documents
  keep their dates and carry a mark, and a catch-up judgement is never an
  event.
- Diagnosis never depends on log retention: step results live in the
  database.
