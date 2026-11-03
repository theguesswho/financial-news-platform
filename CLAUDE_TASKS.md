# CLAUDE_TASKS.md — replacement content (Grok, 9 Oct 2026)

> Claude: read this first. Replace the whole of CLAUDE_TASKS.md with this file (header included). The old T1 (filing-themes era / normaliser flap, parked 28 Sep) is un-parked and absorbed into T1–T2 below; carry its recorded evidence across into T2's "Evidence" block, then drop the old entry. Commit this as part of the local docs commit already holding e6c59d8 (amend or a second local commit; do not push on its own).

## How this list works
- OPEN items only. When an item is fully done (merged, pushed when Edmund says `push`, verified as the item requires), delete it from this file in the same commit. No strikethroughs, no done section.
- Follow-ups, concerns and reviews happen in chat, not here.
- Rules are universal. Tickers below are worked examples to check live numbers against, never special cases in code.
- Edmund alone says `push`, in a quiet Railway window (no scheduler job live). Scoring changes go through the freeze ritual: before/after snapshot diff of the full board, published to Edmund before push.
- Do the items in order. Each one is its own sitting unless it says otherwise.

## OPEN

### T1 — Watch-path isolation (two steps left)
Opened 9 Oct 2026. Size S. Scoring impact: none.

Shipped 9 Oct 2026, commit `4eca961` (scheduler `48a07afb`, api `6b382ad6`, impartial-heart `7242207a`, all SUCCESS; /health/platform and /board 200): deploy triggers recorded in DESK.md, E_DIAG flap logging live. Edmund deferred the rest to another day.

Left:
1. Set watch paths in the Railway dashboard on financial-news-platform (scheduler), api and impartial-heart, using the lists under "Deploy triggers" in DESK.md. Claude walks Edmund through it click by click (service, screen, exact text per box), then reads them back with `railway status --json`.
2. Markdown-only proof push: Railway must show scheduler, api and impartial-heart SKIPPED. Record date and deployment ids in DESK.md.

Done when: both steps done and recorded. Then delete T1.

### T2 — Kill the universe-wide E flap, plus two scoring guards
Opened 9 Oct 2026 (absorbs the 28 Sep parked item). Size M. Scoring impact: yes, freeze ritual.

**CAUSE FOUND 1 Nov 2026:** a second scheduler (Railway project `protective-cooperation`, no era variable) wrote the board on 27 of 68 days since 23 Aug — see DESK.md INCIDENT 2026-11-01. The flap stops when that copy is off (Mon 2 Nov 06:00 is the first single-copy board). Re-scope T2 after Monday's read-back; the bench (Streamlit, era unset) still reads mixed.

Evidence so far:
- E for ~800 of 822 names toggles between two states. Era-2-only read: ~319 names qualify for the gap term, max gap 0.464. Mixed era-1+2 read: ~806 qualify, max gap 0.550.
- Sentinel: the seven no-exposure names with exactly one era-2 call. E = 0.100 means era-2 read; ≈0.15 means mixed.
- Mixed on 25, 26, 27, 29, 30 Sep, 1, 3, 5 and 9 Oct; era-2 on 28 Sep, 2, 4, 6, 7, 8 Oct. Same deployment, env set to 2 on the scheduler, no job-type pattern.
- Tier churn concentrates on toggle days (e.g. 18 Watch↔Buy changes on 2 Oct). The assessor is then woken on phantom "movers" and writes verdicts on noise (ES, DUK, FE, XYL, OMC on 27 Sep).
- Carried from the 28 Sep parked entry (read-only observation, 2026-09-28):
  - `leaderboard_history.narrative_score` changed for 800/822 symbols between the 09-24 and 09-25 snapshots (mean +0.026; 486 up, 314 down) and for 800/822 between 09-27 and 09-28 (mean −0.026); 797 returned to the EXACT 09-24 value. 09-25 → 09-26 → 09-27: 4 and 1 changes.
  - Same deployment throughout (`a53b08b4`, main `ea3d730`, deployed 2026-09-21 12:14 UTC). No re-extractions that week (only 10 new filing_themes rows, all rubric 2, strengths 0.4–0.85). No narrative momentum/status flips in `narrative_history`. 2 exposure adds. `FILING_THEMES_RUBRIC_ERA=2` on the scheduler service.
  - Edmund 2026-09-28: neither he nor Grok ran anything against `filing_themes` on 25 Sep — no re-grade, no backfill, no rubric-era change.
  - Fingerprint = the call-vs-filing gap term of E (`hidden_gem_scorer.compute_call_vs_filing_gap`, 20% of E). The seven no-exposure names (SJM, LULU, MOH, ROL, AZO, NKE, CNC; E = 0.10 exactly) moved +0.04..+0.07 — only possible if they gained gap data. Each has exactly one era-2 call and eight era-1 calls, so they qualify (≥2 calls) only under a mixed-era read. The largest falls were SITM, SMTC, AHR — holders of the biggest era-2 gaps, which shrink exactly when a larger gap enters the universe `max_gap`.
  - Candidates noted then: child-process environment (jobs run as children since R1 — does `_rubric_era_clause()` see the variable in the child?); any path that writes/updates `rubric_version` (a temporary 2 on era-1 rows would give the same fingerprint); Railway logs for 25–27 Sep (retention permitting).
  - Knock-on: the five 27 Sep 06:47 UTC "shifting" Buy→Watch verdicts (ES, DUK, FE, XYL, OMC) were written on data noise, not company evidence.

Part A: root cause
1. Use T1's diagnostic lines to identify which process or path reads the mixed set. Candidates: env not inherited by the spawned child, a code path that bypasses the era filter, a writer of rubric_version, the lab bench, or a cached/stale import.
2. Enforce the era rule in one place (the query helper), not by each caller remembering an env var. Default to era 2 if the variable is missing, and log loudly when it is.

Part B: remove the coupling (fixed scale)
3. Replace the universe-max normaliser on the call-vs-filing gap with a fixed scale (a documented constant chosen from the era-2 distribution, e.g. its 95th–99th percentile). One extreme row must not move every other name's E.
4. Review any other min-max or universe-max normaliser in the E stack; fix each the same way or justify it in DESK.md.
5. Make the Streamlit lab bench use the same era rule and normaliser as prod.

Part C: unexplained-crash guard (FICO is the worked example)
6. If a name's price falls more than 15% in one session (or more than 20% over 3 sessions) with no 8-K, 10-Q, 10-K or call in the prior 5 trading days, freeze its tier at the pre-drop level. It can go down, not up. Hold for up to 5 trading days or until the assessor has written a rationale that explicitly addresses the drop.
7. Show the hold on the stock page ("held: unexplained price drop, awaiting review"). Log every hold and release.
8. Back-test on the last 60 days and list every name it would have held. FICO's 29–30 Sep should be one.

Part D: corporate actions (CTVA is the worked example)
9. Adjust the price series for splits and spin-offs before value or price-lag terms see it (FMP adjusted close or a corporate-actions feed). If neither is available, detect a one-day move over 40% coinciding with a spin or split 8-K and exclude that day from value/price terms until adjusted.
10. List every name with an unadjusted price break in the last 12 months.

Part E: clean up noise already written
11. Add a noise flag on assessor verdicts that readers honour (stock page, reports, any later scoring read). Flag verdicts written on phantom-mover days since 25 Sep. Never hand-edit a rationale.
12. Fix /reports/{date}: it returns current standings for every date instead of that day's.
13. Fix assessor date slips (e.g. "held since October 2026" written in early October; an "upgrade to Buy" the board history doesn't show). Ground dates in board history, not free text.

Freeze ritual: before/after diff of the full board under the fixed scale and guards — tier changes, top-20 changes, count of names whose E moves more than 0.05. After push, 5 consecutive daily runs showing the sentinel constant and no universe-wide E jumps.

Sentinel alarm: /health/platform goes amber if more than 50% of names change E on a run with no matching input change (new filing, new exposure op).

Done when: root cause named and fixed; fixed scale live; guards C and D live; noise verdicts flagged; reports endpoint fixed; 5 clean runs observed; alarm live. Then delete T2.

### T3 — Unfreeze narratives: scoped re-embed, then decay can erode
Opened 9 Oct 2026. Size M. Scoring impact: shadow only in this sitting. Timing: before the mid-October reporting peak.

Why: Every filing_themes.embedding since 10 Aug is NULL (239/239). Decay can't compare new evidence to old, so it has written zero erosion ops since 21 Aug (201 strengthens, 87 adds, 2 proposed removals). Momentum labels are July stamps. October's wave will only add and strengthen unless this is fixed first.

1. Run the scoped NULL-only re-embed per the NARRATIVE_SPEC scope note: fill missing embeddings only, same model and dimension as existing rows.
2. Find out why embeddings stopped on 10 Aug and fix it so new filings embed on ingest. Add a /health/platform check: amber if more than 5% of filings in the last 14 days have NULL embeddings.
3. Re-run decay over 21 Aug → today in shadow (shadow ops table, not live). Report weaken/erode/remove ops it would have written, by narrative, and the 10 biggest.
4. Populate the momentum_state shadow column from the shadow decay output. Report how many narratives would move between accelerating, stable and declining.
5. Show Edmund the shadow result as a plain list ("these narratives would weaken, here's the evidence"). Edmund decides whether shadow decay and momentum go live; that's a separate push with the freeze ritual.
6. Out of scope: Phase 4 amendments, Phase 5 falsification sweeps, Narrative Map, Replay, company narratives in live E. Note mis-parented candidates (e.g. single-company food/brand candidates under "Weight Loss Drug Cascade") in DESK.md for later.

Done when: no NULL embeddings in the window; ingest embeds new filings; health check live; shadow report delivered to Edmund. Then delete T3.

### T4 — Management accuracy: the claims resolver (shadow)
Opened 9 Oct 2026. Size M–L. Scoring impact: none; data and display only. Timing: in time to grade July/August promises against this month's 10-Qs.

Why: 39,695 claims extracted, every one pending; narrative_believability has 0 rows. We record what management promises but never check whether they delivered.

1. Define "due": a claim is resolvable when a filing covering its stated period exists. Claims with no period or no measurable target are marked not_gradable with a reason, not left pending forever.
2. Build the resolver: for each due claim, read the matching filing, compare against the target, write met / missed / partially_met / not_gradable with the evidence quote and numbers. Quantitative claims first; qualitative catalysts second with a stricter bar. Mid-period guidance changes count against the original claim, recorded as such.
3. Fill narrative_believability per company: claims due, met, missed, hit rate, trend over quarters. Minimum 5 graded claims before any rate is shown.
4. Run on everything already due, then on each new 10-Q / results 8-K as it ingests.
5. Show on the stock page as "Promises: X due, Y met, Z missed" with the list behind it. Don't feed the score.
6. Hand spot-check 30 graded claims across sectors and report the resolver's own accuracy before anything shows publicly.
7. Extend the checkpoint grader with on-track and slipping statuses only if cheap; otherwise note for later.
8. Scoring use is Edmund's later decision, after about two quarters of data.

Done when: resolver runs on ingest; due claims graded with evidence; narrative_believability populated; spot-check reported; stock-page display live. Then delete T4.

### T5 — "Why did it move": a cause record for every definitive band crossing, shown on the chart
Opened 10 Oct 2026 (Edmund, from the PTC retrace). Size M. Scoring impact: none — reads scores, never writes them. Two halves: methodology writes the record; product displays it. Absorbs the report-honesty flags of V3 #23 A (same classifier, two consumers: report writer and chart).

Why (PTC as the worked example, 21 Jun → 6 Oct 2026): four band crossings, four different causes, and the record of them is spread across editions, assessor rationales and component columns with no single honest line per crossing. 3 Aug SB→off (growth penalty on divestiture-distorted comps; a data artefact, reversed 6 Aug); 9 Aug SB→Buy (our 10-year quality methodology — edition said so correctly); 30 Sep Buy→Watch (assessor verdict citing "narrative exposure down 0.055" = the T2 E flap, and "priced-in up 0.036" = an internal gap move on a flat price; edition narrated it as "the market catching up"); 6 Oct exit (Schneider $205 cash bid — the only one that was the market). A reader of the chart cannot tell these apart today.

1. Definition of "definitive": the effective tier (assessed or quant) changes AND holds for ≥3 consecutive snapshots, or the crossing clears the band line by ≥0.02 gem on the day. Micro-flaps that revert inside 3 snapshots are not annotated (they are T2's problem).
2. Cause classifier, run at archive time for each definitive crossing, writing one row to a new `band_events` table (date, symbol, from_tier, to_tier, cause_code, descriptor ≤ 90 chars, evidence_ref): codes, in precedence order —
   `corporate_action` (takeover / spin / split 8-K in prior 5 trading days) → `company_event` (10-Q/10-K/8-K/call in prior 5 trading days; name it) → `assessor_verdict` (assessed_tier changed while quant tier did not; descriptor = first clause of the rationale, machine-written, never edited) → `measuring_stick` (active platform_notes row OR a component moved by a data repair / methodology change with no price or filing input change) → `price` (priced-in or value moved with a real close change; state the move vs SPY) → `data_noise` (T2 noise flag set, or the universe-wide E-change alarm fired that day) → `mixed` with the two largest drivers named.
3. Input-change flags feeding the classifier (from #23 A): new close y/n; growth_quarter_end / growth_source changed; historical_metrics latest date changed; narrative rows changed; platform_notes active; assessor ran.
4. Backfill `band_events` from leaderboard_history for the board's life (classifier over history; where inputs can't be reconstructed, code `unknown` and say so — never guess).
   **Pre-registered for this backfill (written 1 Nov, corrected 2 Nov against the 2 Nov board; `band_events` does not exist yet).** Raw-band crossings on the 2 Nov board caused by the era switch, cause `measuring_stick`: platform_notes id 9 (second scheduler switched off; the board moved to the era-2 read only, no price or filing input behind it). Source: same-data recompute of both reads on 1 Nov, confirmed on the 2 Nov board (the seven T2 sentinels match the era-2 recompute exactly).
   - ADBE: Buy → Watch on raw score (0.3621 → 0.3480). Corridor hold; the 2 Nov assessor ruled HOLD citing note 9, so the displayed tier stays Buy.
   - TPL: Strong Buy → Buy on raw score (0.4809 → 0.4590). Displayed tier was already Buy; no visible change.
   - INTU: Buy → Watch on raw score (0.3614 → 0.3485). Displayed tier was already Watch; no visible change.
   Predicted from the 1 Nov data but did NOT cross on 2 Nov: AM (0.3616 vs the 0.36 Buy line) and CF (0.3211 vs the 0.32 exit line).
   Under item 1 none of the three changed its effective tier on 2 Nov, so none is a band_event unless a later ruling or move changes it; a new filing or real price move for the name outranks this per item 2's precedence.
   Design caveat for item 2: note 9 is active 25 Jun → 15 Nov and note 8 22 Oct → 14 Nov. "Active platform_notes row" as a blanket test would code every price-driven crossing in those windows `measuring_stick`. Match a note to the component it changed (note 9: narrative/E only; note 8: narrative and qualitative legs) before applying the code.
5. Report writer (daily_report.py) must consume the same cause record for its move lines — one source of truth; "the market caught up" is only ever written under cause `price`.
6. Product (FRONTEND_SPEC dated update): API `GET /stocks/{symbol}/band_events`; the stock-page score chart shows a marker at each definitive crossing with the descriptor on hover and a one-line legend. Plain lexicon. Read-only.
7. Verify on PTC: the four crossings above must come out with the four codes above before anything is shown publicly; then a 10-name spot check across sectors.

Sequencing: after T2 (the noise flag and the E alarm are inputs here). Done when: band_events written on archive and backfilled; report writer reads it; endpoint + chart markers live; PTC and the spot check verified. Then delete T5.

### T6 — Failures are not `ok`: step-failure status, judgment-layer health, billing pre-flight
Opened 25 Oct 2026 (Edmund's fortnight review; V3 #28). Size S–M. Scoring impact: none.

**STATUS 31 Oct 2026 08:40 UTC: minimum set (item 13) LIVE on prod (`28bcbbd`, pushed 08:25, migrated 08:31, api 08:40; all four immediate checks passed). First run on the new code is Sun 1 Nov 06:00 UTC — check 5. Items 2 (health amber on degraded/silent judgment layer), 4, 5 (lots cause — needs the log), 8 (remaining 9 unrecorded callers), 9, 10, 12, 14 (log export, needs `railway login`) remain.**

Why: Anthropic credits ran out at 22:15 UTC on 22 Oct. For three days every LLM step (assessor, extraction, claims, ledger, grading, editions) failed inside its try/except; scheduler_runs said `ok`, /health/platform said ok, and only the 2-day daily_brief bar alarmed on the morning of the 25th. 135 filings in the peak week have no analysis text; 13 board movers are unassessed; three editions are missing. Also: no v2d track lot has opened since 18 Sep despite five Strong Buy entries — unexplained until the Railway log is read.

1. Run ledger: a run whose steps raised is `degraded`, with the failed-step list in `error`; `ok` means every step completed. _err() records the failure instead of only logging it.
2. /health/platform: amber (503 with the check named) when the latest run is `degraded`, or llm_usage has zero calls in the last 26 h on a day with scheduled runs, or the newest qual_assessment / filing_themes row is older than 48 h on a weekday.
3. Pre-flight at run start: one 5-token call; a billing 400 or auth 401 is logged as a named alarm and written to env_diagnostics (source `llm_preflight`) so the brief and readouts carry it.
4. Edmund: set a low-balance email alert in the Anthropic console; record the threshold in DATA_SCORECARD.
5. Track record: read the 4t step log for 19 Sep → today; name why no lots opened; fix; back-open only what the rules allow (next-close fills from the day the signal qualified, never retro-priced).
6. Label the 22–24 Oct edition gap with a platform_notes row. No backfill of editions or assessments; the catch-up steps repopulate analysis text and verdicts on their own schedule.

7. Backlog drain (first thing after credits): run the catch-up steps in bounded batches (≤100 extractions / ≤40 assessments per run) rather than one flood; 8-Ks since 23 Oct must be re-fetched before the 14-day cutoff passes (events.py gates storage on the Haiku classification — store first, classify after, so an LLM outage never loses a filing again).
8. Ledger coverage: every Anthropic caller records usage (claim_extractor, events, synopsis, analyzer, brief, deep_dive, narrative_lifecycle, narrative_override, meta_theme_builder, themes, screener, earnings_ingestion) — one wrapper around messages.create so a new caller cannot skip it. Reconcile the ledger against the console for 20–22 Oct and fix RATES if they differ.
9. Assessor economy: one sweep per symbol per day (the 22:00 sweep assesses only names not assessed since 06:00 unless a NEW filing arrived); the materiality corridor respects the 18-hour guard; no verdict on a priced-in move under 0.02 — log it as "held, immaterial" without an LLM call. Target: ≥60% of verdicts coincide with a tier change or a new filing.
10. Prompt caching on every module with a fixed rubric ≥1k tokens: theme_extraction_v2, claim_extractor, checkpoint_minting, checkpoint_grader, events, company_narrative.
11. Spend ceiling: a daily est-cost budget (default $8; wave days $15, set by Edmund) checked by each LLM step before it starts; over budget → step logs "deferred, budget" and the run is `degraded`, never silent.
13. **Minimum set, one push (target Sun 1 Nov, quiet window):** items 1, 3, 7 (store-then-classify + extraction limit 100) and 11, plus: `scheduler_steps` table (run, step, started, finished, status, error, counters) written by _step/_ok/_err so diagnosis never depends on Railway log retention; `filings.backfilled` + `qual_assessments.continuity = 'catch-up'` (recovered documents keep their dates on the wire; backfilled filings never fire event-triggered wakes, deferred-reaction checks or edition move lines; the "unassessed since filing" trigger still fires once for board names); a **drain budget** ($12/day × 7, env `DRAIN_BUDGET_USD_DAILY`) separate from the ceiling — work on items older than 2 days or flagged backfilled charges it; **no assessor wake on an E-only change** (narrative_score moved with no new filing and no exposure op since the last verdict); **lot hold** (`TRACK_LOTS_HOLD=1`) until the post-drain verification passes; read-only `GET /ops/backlog` (backlog counts by surface, per-module llm_usage 24h/7d, 8-Ks stored per day for 14d, board seats whose verdict predates their latest filing). Schema via db/migrate.py.
14. Logs first: `scripts/export_railway_logs.sh` dumps 22–31 Oct step logs and all E_DIAG lines to `logs/incident_2026-10-22/` the moment Edmund has run `railway login`; read the 4t (lots) and transcript step failures from it.
15. 8-K recovery verified read-only 31 Oct (90-day lookback; EDGAR recent list reaches 2013; 19/19 sampled 23–30 Oct filings visible and absent from our DB) — no per-day index path needed; confirm the 23 Oct rows land in the first drain run.
16. Drain order is extraction → ledger (the ledger LEFT-joins filing_themes; judging unextracted 10-Qs writes weak ops that are never revisited).
17. Edmund console: auto-reload on; low-balance email at ~one week of spend; threshold recorded in DATA_SCORECARD.
18. platform_notes id 8 written 31 Oct (active 22 Oct → 14 Nov): board existed, narrative and qualitative legs stale; catch-up verdicts are not reactions to news. Extend or close it when the drain verification passes.
19. **Targeted ledger redo (Edmund 31 Oct) — run ONLY after the remaining ~329 extractions have cleared; do not run now.** The 31 Oct 06:00 pass judged 317 symbols; 212 of 261 10-Qs in evidence had no themes at judge time, and 272 `add` ops were written on bare filing lines. A plain re-run cannot revisit them (`last_evidence_at` has advanced). Build: `run_update_pass(engine, symbols=..., since_override=date)` so the judge re-reads evidence since 2026-10-22 for the named symbols; a CLI entry (`python -m pipeline.exposure_ledger --symbols ... --since 2026-10-22`). Scope: the 23 board names judged on unextracted 10-Qs plus every symbol that received an `add` on an unextracted filing on 31 Oct (list them from exposure_history + filing_themes.extracted_at before running). Charge the drain budget; expected ≈ $1–4. Record the op counts before/after in DESK.md.
20. **spend_today fix (Edmund 1 Nov) — must land before any assistant build:** `pipeline/run_ledger.py` `spend_today` folds every unknown budget tag into `daily` via `COALESCE(budget,'daily')`; a `product` tag (the on-page assistant, FRONTEND_SPEC.md ACCEPTED 2026-11-01) must count against its own ceiling only, never the scheduler's daily ceiling. Methodology-track item; no build of the assistant until it is live.
21. **Single-scheduler guard — BUILT LOCAL `014d1dc`, NOT PUSHED (1 Nov):** one owner per run slot (claim + heartbeat + owner-checked finish; duplicate stands down with env_diagnostics 'duplicate_scheduler'); harness `scripts/test_scheduler_guard.py` 12/12. Push in the next clear window with the docs commits. Next session: surface 'duplicate_scheduler' rows in /health/platform and the daily brief (readouts read back the alarms).
12. Edmund to confirm an economy rule for CLAUDE.md (draft): "Credits are a scoring input like any other: every LLM call is recorded, every module has a stated cost per unit of work, spend has a daily ceiling with a named alarm, and no judgment surface is called twice on the same evidence."

Done when: minimum set (13) live and proven (a forced step failure shows `degraded` + a scheduler_steps row; pre-flight alarm against a bad key; /ops/backlog answering); logs exported; backlog drained in batches with the 8-Ks recovered and flagged; ledger covers 22/22 callers and reconciles to the console within 10%; assessor duplicate rate < 10%; caching live on the six modules; ceiling + drain budget + alarms proven; lots reopened after verification; CLAUDE.md rule in (Edmund's wording). Then delete T6.

### T7 — Judgment surfaces quote their facts correctly (numbers and dates)
Opened 2 Nov 2026 (Edmund, from the ADBE materiality ruling). Size S–M. Scoring impact: none — it changes what the assessor is told and checks what it writes, never a score. Related: T2 item 13 (date slips).

Why: ADBE's 2 Nov ruling (correct HOLD, note 9 cited) misstated two facts it quoted. (1) "a 5.6-point drift in story-exposure scoring": the story score moved 8.68 → 8.12, a change of 0.56 on the 10-point scale. Cause, verified in code: `materiality_reason` passes component deltas on the 0–1 scale ("story exposure -0.056") while the prompt tells the model to convert 0–1 inputs itself ("a 0.55 input is 5.5 out of 10"); it scaled the delta by 100. (2) "platform note: 23 Aug–1 Nov dual-scheduler contamination": note 9 says the second copy ran 25 Jun – 1 Nov and read mixed from 23 Aug; the two ranges live only in free text and were merged. A reader cannot tell a quoted fact from a slip, and these rationales feed editions and (later) the on-page assistant.

Proposed fix (inputs and a check — the machinery still does the assessing; nothing tells the assessor what to conclude, and no rationale is ever hand-edited):
1. Facts, not conversions: every score and delta reaches the prompt already on the 10-point scale and labelled once ("story score 8.68 → 8.12, change −0.56 on the 10-point scale"). `materiality_reason` and every trigger line use the same formatter (`pipeline.tiers.fmt10` is the one place the transform lives).
2. Platform notes carry structured dates: add `period_from`, `period_to` and an optional second range (e.g. `mixed_from`) plus `affected_components` to platform_notes via db/migrate.py; the injector prints them as a FACTS line ahead of the note text ("second copy ran 25 Jun – 1 Nov 2026; mixed reading 23 Aug – 1 Nov; affects: story score"). The same fields serve T5's component matching (see T5 design caveat).
3. One number check, shared: the check FRONTEND_SPEC fixes for the on-page assistant (every number and quote must appear in a cited row; stated rounding and the 10-point conversion allowed; every rejection logged) lives in pipeline/ as a methodology module and runs on each assessor rationale before it is stored: every number and date in the text must match a fact in the prompt's fact block (or its 10-point form within stated rounding). On a mismatch: log the rejection (named, with the quoted and the expected value), re-ask ONCE with the mismatch listed as a fact correction, and if it still fails store the verdict flagged `number_check_failed` and name it in the daily brief. The product assistant later imports the same module read-only.
4. Verify offline first: replay ADBE's 2 Nov prompt through the check — both slips must be caught; then a 20-verdict sample from one day must pass with zero false rejections before it goes live.
5. Price moves carry their dates (added 3 Nov 2026, Edmund, from the evening-closes incident, DESK 2026-11-03): the trigger's "MARKET REACTION: the stock moved X% on the latest session" names the two closes it compares ("close 2 Nov vs close 30 Oct") and says whether the release came before or after the later close, from the filing's timestamp. The 2 Nov verdicts show why: ON's rationale tied Friday's -4.7% to Monday's Synaptics announcement and FN's called Friday's -6.1% "the session move". The number check (item 3) must accept the move only with those dates.

Done when: deltas and dates reach every judgment prompt as structured facts; the shared check runs on every assessor rationale with rejections logged and surfaced; ADBE replay caught; sample clean. Then delete T7.
