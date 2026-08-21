# V3 fix list

Started 2026-08-11 (user directive). Known defects and improvements not
yet actioned — distinct from V2_CONSIDERATIONS.md (the scoring-change
log; anything here that touches scoring still goes through that ritual
when actioned). Move items to a Done section with date + commit when
fixed.

## High priority

1. **Claim extractor orphaned (HIGH — user 2026-08-11).**
   pipeline/claim_extractor.py has no caller; earnings_claims stopped
   2026-06-12. 674 transcripts unextracted incl. 42 tiered names and all
   7 held positions. Not redundant with narrative_checkpoints (user):
   claims are per-company vendor-verbatim; checkpoints are per-narrative
   judged. Fix: wire into after-close right after transcript ingestion +
   backfill the June 12 -> now backlog (est. one-time LLM cost — check
   extractor's model, give user the number before running). Feeds the
   product track's Companies dossier ("promised vs delivered" pane).

2. ~~Transcript fetch cadence~~ VOID (2026-08-11): the after-close run
   already pulls transcripts (step 2, before the assessor at step 6) —
   the architecture was right all along. Replaced by:
   **Fast-path quarter fallback can fetch the WRONG call (corrected
   diagnosis 2026-08-11).** The vendor indexes by FISCAL quarter (same
   as FMP) — the earlier "calendar/fiscal collision" diagnosis was
   WRONG. Real behavior: the sweep guesses calendar quarter from the
   8-K date; for offset-FY companies the guess misses (404 — correctly,
   transcript not yet published) and the q-1 fallback can fetch the
   PRIOR quarter's call, whose insert then no-ops on the existing FMP
   row (harmless) — but a hand-ingest trusting the fallback's label
   stored ACM's MAY call as "Q3" (caught + deleted same night; see
   CLAUDE.md Evidence integrity rule 3). Fix: derive the FISCAL quarter
   from FYE month (fundamentals_annual) before requesting, and verify
   the returned transcript's internal date before insert; drop the
   blind q-1 fallback.
   RESOLVED SAME NIGHT (the deeper finding): **assessor was blind to
   8-K content** — judged filings it never read; the LHX/ACM class.
   get_stock_context now passes the last 14 days of 8-K analyses into
   every assessment (RECENT MATERIAL EVENTS block); ACM re-assessed
   through the machinery with the charge + guidance cut in view (SB
   held, honestly argued, sharper bear case). Codified as CLAUDE.md
   "Evidence integrity" rules 1-4.

## Methodology (freeze ritual applies)

3. **Narrative momentum — SCOPED 2026-08-11 (user: "we need to nail
   this bit"; build shadow-first, NO live push without sign-off).**
   Today every macro reads "accelerating" = zero signal. Design:
   - Source: the exposure LEDGER, not judge vibes. Per narrative,
     two trailing windows (28d primary, 7d turn-detector):
     support = adds + strengthens; erosion = weakens + removes +
     misses. Net support rate = (support − erosion) / active exposures.
   - States: accelerating (28d rate ≥ +X% and 7d not negative),
     decelerating (28d ≤ −X%, OR any falsification condition hit, OR
     checkpoint failures outweigh passes), stable otherwise; "quiet"
     when ops < minimum N (thin evidence must not flap the label).
   - Company scope: checkpoint verdicts (delivered vs missed) count as
     first-class ops.
   - Calibration: compute over ledger history since July; tune X and N
     so the library actually spreads across states (roughly 20/60/20,
     not 100/0/0). Present distribution to user BEFORE cutover.
   - Rollout: shadow field alongside the current one for ~2 weeks,
     diff shown, then cutover with sign-off. Product landing page
     colors stay ledger-driven until this ships.

4. **EVR consistency knob revisit.** If EVR still smells wrong after the
   fiscal-calendar hygiene: measure residuals against the 15-year
   history or a harsher tail measure.

5. **BAH override-screen candidate.** Offline 5.2 vs live 2.6 — superb
   quality/value, low story exposure. Watch as the BR-class narrative-
   blind override case.

## New analytics (scoring-adjacent — reads scores, never writes them)

8. **Re-rating room ("how big is the opportunity") — DESIGN APPROVED
   2026-08-13, build-ready.** Solves the two factors from the SMCI
   whiplash: a Strong Buy must not die on one good day (thin gaps
   masquerade as real ones because value is a RANK, which hides
   depth), and we want compounders, not trades.
   THE MEASURE — re-rating distance: how far price would move if the
   stock were priced like the MEDIAN company in its story (narrative
   peers; thin groups <~8 fall back to sector, labeled thin evidence
   like the PEG analyst count). ONE multiple per category (user
   2026-08-13, no blended conflicts): most stocks forward P/E; banks
   P/B; REITs P/FCF. No forecasts, no assumptions — today's prices,
   today's peers.
   THE INTERPRETATION — two engines, shown side by side, never
   merged: re-rating room (one-time) + the business engine (quality
   trend: growing/flat/shrinking). Shrinking-earnings cheapness is
   fiction — flag, don't celebrate. Plain-words surface: "Priced X%
   below the typical company in its story (N peers). Business engine:
   growing." Nightly, dated, "on the numbers alone" (assessed layer
   sits on top).
   Companion (from the same episode, still valuable): tier-band
   ceilings/re-entry prices via price-override re-scoring of the REAL
   scorer (never a parallel formula; nightly self-test must reproduce
   today's live score or publish nothing), incl. cyclical cliffs
   (SMCI's punished flag dies at 75% of 52w-high ≈ $44).
   SEQUENCE: build room measure + ceilings → assessor context line +
   surfaces → Dell backtest as validation (how many +20% sessions
   could Dell absorb during its re-rating vs SMCI's one) → THEN the
   doctrine decision (minimum headroom for SB) with the distribution
   in hand, not before.

9. **DONE 2026-08-13 (after ENS became the second victim — the cost of
   logging instead of building).** Two-part fix in the qual trigger:
   (a) earnings-8-K reaction lines now carry an explicit caution that
   an after-hours release makes the quoted move pre-release; (b) a
   DEFERRED REACTION CHECK re-fires the assessment once, after the
   first post-release close, whenever that close moved >=3% (one-shot
   via a 21h assessed_at bound). Verified: full trigger query clean;
   ENS simulation fires tonight at +14%; two backlog victims (MTSI,
   ABNB, Aug 6 releases) caught by the 7-day window and re-assessed
   tonight. Release timestamps aren't stored (SEC acceptance time not
   ingested), so morning-vs-evening can't be distinguished directly —
   the >=3% next-session gate is the proxy; storing acceptance time is
   the eventual clean fix.

## Data / pipeline hygiene

0. **STALE LIVE-SCORING INPUT (found 2026-08-11, highest item here):**
   the weekly embeddings build requires sentence-transformers, absent
   from Railway requirements → it has failed silently on every Railway
   weekly. stock_theme_alignment (its downstream) froze 2026-07-12 —
   and it supplies the 20% "narrative momentum" leg of the priced-in P
   component in LIVE scoring. A fifth of P has run on July-12
   trajectories for a month. Decision needed (belongs at the
   NARRATIVE_SPEC Phase 2 gate, alongside the momentum board diff):
   REPLACE P's leg with narrative-brain honest momentum and RETIRE the
   legacy embeddings/meta-theme-alignment path (recommended — one
   narrative system, no 2GB torch in the image), vs revive the
   dependency (itself a scoring change: unfreezing shifts P).
   Either way the change is freeze-discipline. Interim: it has been
   stale a month with slow-moving trajectories; two more weeks of
   documented staleness beats a rushed unfreeze.
   INTERIM ACTIONED 2026-08-11 (user-approved): sentence-transformers
   added to requirements (unblocks decay SHADOW accumulation on
   Railway) and legacy step 5 explicitly PARKED with a loud weekly
   warning — the P leg stays frozen-and-documented; nothing unfreezes
   outside the Phase 2 ritual.

6. **processed_at is vestigial — retire it.** Full-audit finding
   2026-08-11: the huge processed_at NULL counts are NOT unprocessed
   content. Real coverage metrics are healthy: 8-Ks 100% llm_analysis
   within 30d; 10-K/Q and transcripts are themed (0 unthemed in 14d),
   and llm_analysis was never their channel. processed_at is written
   only by legacy paths (analyzer.py, events.py). Drop or stop reading
   it; it misleads audits (it misled this one).

6b. ~~theme_extraction has no prompt caching~~ CORRECTED 2026-08-11
   (user challenge): 0% cache is STRUCTURAL, not a miss — instructions
   are ~220 tokens (cache minimum 1024; padding costs more than it
   saves) and the spend is dominated by unique filing text, uncachable.
   The original cost audit adjudicated this correctly; the 2026-08-11
   audit note briefly mislabeled it as free savings. Real cost lever if
   ever needed: theming BREADTH (830-symbol universe) — but narrowing
   blinds narrative discovery; methodology call, user-only, not
   recommended.

6e. **Yahoo refresh still writes legacy TTM margins into the
   fundamentals snapshot** (fundamentals.py ~137-141). Harmless today
   — scorer/assessor take margins from canonical FMP tables and the
   sync overwrites — but it is a mixed-definition trap for any future
   snapshot consumer. Stop writing gross/operating/net margin from the
   Yahoo path; canonical owns statement-derived fields.

6c. **LIVING NARRATIVES — SCOPED 2026-08-11 (user: "the whole point is
   that it should be living and breathing"). Supersedes the narrower
   checkpoint-inflow question; user answered YES and went further:
   narratives must absorb everything — calls, 8-Ks, 10-K/Qs —
   continuously.** Design, in dependency order:
   a. **Post-birth prediction minting**: new typed claims on EXISTING
      company narratives mint checkpoints (not only at birth). Feed:
      earnings_claims (extractor re-wired 2026-08-11) mapped to the
      company's narrative; dedupe against open checkpoints; cap per
      narrative per quarter. This alone makes dossiers breathe.
   b. **Thesis amendments, evidence-cited**: when a narrative
      accumulates K new evidence rows or a checkpoint resolves, an
      update judge amends the thesis — versioned into thesis_history,
      each amendment citing the evidence rows that drove it (grounding
      discipline as in P2). Never silent rewrites.
   c. **Sector/macro narratives breathe too**: weekly evidence digest
      per narrative (child exposures' ledger ops + filing themes) into
      the same amendment judge. Macro theses currently only change at
      lifecycle events — that is the "static meta-narrative" the user
      rejects.
   d. **Falsification sweep**: kill conditions checked against fresh
      evidence every weekly pass; hits force momentum = decelerating
      and open a lifecycle review.
   **CORROBORATION PRINCIPLE (user, 2026-08-11 — governs all of the
   above):** one company reporting something new is NEVER a narrative
   event above company scope. A new narrative is born — or an existing
   one develops up or down — only when a NUMBER of companies say
   similar things in a similar direction. Single-company signals feed
   that company's own dossier and count as ONE vote toward any broader
   narrative. Mechanically: sector/meta thesis amendments and births
   require evidence from >= B distinct companies within the window
   (B calibrated per tier — higher for metas than subsectors); the
   momentum measure (#3) likewise requires breadth — ops from >= M
   distinct symbols, so one company's repeated ledger activity cannot
   move a narrative's momentum alone.
   Cost bound: (a) event-driven off claims (cheap); (b)+(c) batched
   weekly. Depends on: claim extractor (live), momentum #3 above.
   Sequencing: (a) first — it unblocks the product dossier page.

6d. **qual_assessor cache share is 53.6%, not the ~85% hoped.** The
   warm-up fix works within a run, but runs are spaced further apart
   than the cache TTL, so cross-run misses are structural. Either
   accept (cost is ~$1.4/day) or restructure prompts; recalibrate the
   expectation in any case.

7. **OZK filing-mapping** still open (chunk-3 exclusion note).

8. **Assessor cache hit rate** — verify the warm-up fix moved ~55% to
   ~85% in llm_usage after a week of runs (check ~Aug 16).

## Standing gates (not fixes, reminders)

- Chunk 4 + ALNY/LITE/SNDK additions stay gated behind the board-size
  tripwire (>75 tiered -> proposal first).
- Watch-path isolation still unproven for web-only pushes (CLAUDE.md
  rule; the recent scheduler deploys were pipeline pushes, so no test
  yet).

10. **track_lots has no created_at/audit timestamps** — a row
    disappearance on 2026-08-15 was untraceable (end state verified
    correct, cause unknown). Add created_at DEFAULT now() + updated_at;
    never again an untraceable mutation in the record that judges us.

11. **assessed_tier provenance (BLOCKS the product's assessor badge).**
    Since the 2026-08-15 materiality corridor, assessed_tier can be
    written by three different mechanisms: a judge's conviction
    override, a corridor hold pending ruling, or a materiality-ruled
    hold. The column doesn't say which, so the product's "judgment
    raised it" badge would mislabel mechanism as conviction. Add a
    provenance column stamped at write time (judge / corridor_pending /
    materiality_hold) in apply_qual_tiers + apply_materiality_holds;
    expose via /board.

12. **Report writer must see the book everywhere (law-17 counterpart).**
    The UI now reconciles "no position" sentences against the scorecard
    (DESIGN_BRIEF law 17, user-adopted); the durable fix is upstream:
    the daily_report writer already gets position truth on MOVES
    (2026-08-10 fix) but coverage/top-story/other sections can still
    claim no position. Extend the position field to every section's
    facts so the UI regex becomes a belt, not the brakes.

13. **Corridor holds vs the board's raw-floor guard (found via the
    roster fix, 2026-08-16).** /board applies "an assessor verdict
    counts only while the raw score clears the Watch floor" (Aug 10
    rule); the materiality corridor (Aug 15) stamps holds whose raw
    score can sit BELOW that floor — the guard silently discards them
    (INTU: held Buy in the DB, absent from /board). Two rules written
    five days apart disagree about who wins at the bottom of the
    board. Decide precedence deliberately (freeze ritual — it changes
    board membership); until then the guard wins and holds below the
    floor are display-dead.
    Second worked example 2026-08-19 (CSL, found by Edmund comparing
    surfaces): raw 0.339 sits between exit (0.32) and entry (0.34) —
    the methodology's hysteresis grace seat keeps it on the board
    (stored tier Watch) and the assessor affirms Watch, so Streamlit
    shows it; /board's resolver recomputes tier_for(raw)=None and the
    guard drops the name entirely. The product board does not honor
    grace seats the methodology grants. Likely the same mechanism as
    the 35-vs-38 wrinkle (which stays visible, undiagnosed, per the
    standing brief). Still Edmund's precedence call — nothing changed.
    DONE 2026-08-20 (local, not pushed): Edmund ruled — seat wins above
    the exit line, guard kills below it (V3_13_PRECEDENCE_SPEC.md;
    freeze entry in V2_CONSIDERATIONS.md). board_membership.py resolver
    now rides the stored snapshot tier with a hard kill below
    BOARD_EXIT; both worked examples resolved: CSL back on /board
    (Watch 3.4, grace seat) and INTU's class of corridor holds honoured
    (INTU itself is below 0.32 today — correctly off). Mandatory
    offline diff: additions only, both expected classes, zero
    removals; flip-count stop condition (7/day, Aug 13-16) reported
    and signed off by Edmund ("Proceed"). Local /board 44 -> 46,
    non-flipped entries byte-identical. Commit 0bf2daf; hash also in the
    spec. Prod verify + 35-vs-38 outcome pending the next
    Edmund-attended push.

14. **Report masthead has its own board-membership definition (found
    2026-08-18 during the NaN incident).** daily_report._masthead
    counted board=36 the same morning /board showed 41. Third parallel
    definition of "on the board" (force rosters were the second —
    fixed 2026-08-16 via board_membership). Fix is the same pattern:
    the report generator derives membership/counts from the shared
    resolver, never its own query. Do alongside the daily_report
    bookkeeping-vs-real-move fix assigned in FRONTEND_SPEC (2026-08-18
    decision).
    DONE 2026-08-19 (local, not pushed): resolver EXTRACTED to
    pipeline/board_membership.py with an as_of date (per Edmund's A2
    correction — pipeline never imports api; api re-exports from the
    pipeline module); _masthead/_board_moves use board_membership(conn,
    as_of=edition_date); own COALESCE queries deleted. Local /board
    before/after the extract: byte-identical. Verified read-only vs
    prod DB: board=40, leaders top-3 ACM/GDDY/LDOS — identical to
    prod /board the same day. [Wording corrected 2026-08-19: an earlier
    note here mis-described the fix as importing from api/routers.]

15. **Filings-intelligence positivity skew (user observation 2026-08-20,
    CONFIRMED in data).** Last 30 days: trajectory 72% "accelerating"
    (962/1335) vs 7.5% decelerating; strength wildly top-heavy (mode =
    the 0.9-1.0 bucket, 36% of all filings; almost nothing below 0.6);
    tone 66% "confident"; 8-K impact 11:1 positive (795 vs 71). The
    extractor grades what management CLAIMS, and management always
    claims acceleration — same disease as "every macro accelerating =
    zero signal" (#3). The wire's display floor (strength >= 0.60)
    then hides the few weak ones, making the surfaced feed look even
    rosier. Protections that exist: believability/claims grading and
    checkpoint verdicts (real but slow — they accrue over quarters).
    WORKED DESIGN 2026-08-20 (Edmund: high effort, "not arbitrary in
    either direction"): see V3_15_STORY_GRADING_DESIGN.md — anchored
    evidence-cited strength bands, trajectory graded vs the company's
    OWN prior artifact, tone→groundedness (the "promotional"
    category), 8-K impact anchors. Percentile display and post-hoc
    deflation REJECTED as curves. NOTE: narrative_strength feeds the
    live scorer (call_vs_filing_gap) → full freeze ritual; and
    narrative_believability is EMPTY (0 rows) — the truthfulness
    protection is not operating; populating it is the companion
    build. Shadow sample ~$3 runnable now; 18-month re-extraction
    ~$150-200 quoted before any run. Awaiting Edmund's ruling.

16. **Edition date is midnight-unsafe + off-schedule regeneration
    (found 2026-08-21 via Edmund's SARO question).** Both scheduler
    call sites pass for_date=date.today() evaluated WHEN THE STEP
    RUNS: any invocation crossing/starting after 00:00 UTC stamps
    tomorrow's date onto yesterday's snapshots. Observed: an 00:39
    UTC invocation (likely dead-run rescue after a restart; logs
    rotated, trigger unproven) wrote an Aug-21-dated edition from
    Aug-19/20 snapshots — no moves section, SARO's entry missing
    from headlines while the board correctly flagged it New. Fix:
    derive the session date from the LATEST SNAPSHOT date (the data
    the diff actually uses), never wall-clock at step time; and log
    trigger + for_date + snapshot-dates on every generation (V3 #10
    audit-columns companion) so the next orphan is attributable.
    Self-heals nightly via DELETE+INSERT, so severity is
    hours-of-stale-headlines, not permanent corruption.
    BUILT 2026-08-21 (local, same conversation, per the incident-fix
    rule): latest_snapshot_date() in daily_report.py is the anchor for
    BOTH scheduler call sites (after-close step 8, weekly step F —
    whose friday calc mapped any Friday-daytime catch-up to the
    UPCOMING session, the exact 00:39 shape); generation audit line
    prints for_date + the two diffed snapshot dates + wall clock on
    every edition. Verified read-only: anchor returns 2026-08-21,
    audit pair [08-21, 08-20], SARO None->Buy in that diff. Rides the
    next push; tonight's 22:00 run still executes the OLD code (its
    wall-clock date is safe at 22:2x) and overwrites the orphan
    either way.
