# CLAUDE_TASKS.md — replacement content (Grok, 9 Oct 2026)

> Claude: read this first. Replace the whole of CLAUDE_TASKS.md with this file (header included). The old T1 (filing-themes era / normaliser flap, parked 28 Sep) is un-parked and absorbed into T1–T2 below; carry its recorded evidence across into T2's "Evidence" block, then drop the old entry. Commit this as part of the local docs commit already holding e6c59d8 (amend or a second local commit; do not push on its own).

## How this list works
- OPEN items only. When an item is fully done (merged, pushed when Edmund says `push`, verified as the item requires), delete it from this file in the same commit. No strikethroughs, no done section.
- Follow-ups, concerns and reviews happen in chat, not here.
- Rules are universal. Tickers below are worked examples to check live numbers against, never special cases in code.
- Edmund alone says `push`, in a quiet Railway window (no scheduler job live). Scoring changes go through the freeze ritual: before/after snapshot diff of the full board, published to Edmund before push.
- Do the items in order. Each one is its own sitting unless it says otherwise.

## OPEN

### T1 — Watch-path isolation + flap diagnostic logging (one push)
Opened 9 Oct 2026. Size S. Scoring impact: none (logging only).

Why: Every push to main, including markdown, rebuilds and restarts the scheduler. We also need a diagnostic push to catch the flap (T2) in the act. Doing both in one push means one restart, not two.

Part A: watch paths
1. Find how Railway decides to rebuild each service (financial-news-platform scheduler, api, web): dashboard watch paths, railway.toml/railway.json, root directory, Dockerfile context. Write the current state into DESK.md under a "Deploy triggers" heading.
2. Set watch paths so: scheduler rebuilds only on runtime paths (pipeline/**, scheduler*.py, db/**, config/**, runtime scripts/**, requirements*.txt, Dockerfile*, railway.*); api only on api/** plus shared runtime paths it actually imports; web only on web/**; nothing rebuilds on *.md, docs/**, TRIAGE_*, V3_FIXLIST.md, DESK.md, CLAUDE_TASKS.md.
3. If the config lives in a repo file, this push itself restarts once (expected). Either way, plan a separate markdown-only proof push afterwards, because the T1 push carries runtime files (Part B).

Part B: flap diagnostic (logging only)
4. Inside the scoring child process, at every re-score, log one structured line: run id, job type, PID, the rubric-era clause actually applied in SQL, the value of FILING_THEMES_RUBRIC_ERA as that process sees it (unset vs "2"), count of names qualifying for the call-vs-filing gap term, and the max gap used as normaliser.
5. Add the same line to any other code path that computes E (after-close re-score, assessor mover prep, backfills). If a path computes E without going through the era filter, list it in DESK.md. That is likely the bug.
6. Note in DESK.md: the Streamlit lab bench has no era variable and computes E under the mixed read. Not the prod cause, but bench and prod must agree; fix belongs in T2.

Done when: watch paths set and recorded; T1 pushed (with e6c59d8 and the new CLAUDE_TASKS.md); a later markdown-only push shows scheduler and api SKIPPED in Railway, recorded in DESK.md with date and deployment ids; diagnostic lines visible in logs across at least one flip day. Then delete T1.

### T2 — Kill the universe-wide E flap, plus two scoring guards
Opened 9 Oct 2026 (absorbs the 28 Sep parked item). Size M. Scoring impact: yes, freeze ritual.

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
