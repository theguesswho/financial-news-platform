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

3. **Narrative momentum uninformative.** Every macro reads
   "accelerating" — no discriminating signal. Recalibrate from ledger
   evidence (op balance over a window), not vibes. Blocks honest
   momentum coloring on the product's landing page (currently contracted
   to use ledger ops instead).

4. **EVR consistency knob revisit.** If EVR still smells wrong after the
   fiscal-calendar hygiene: measure residuals against the 15-year
   history or a harsher tail measure.

5. **BAH override-screen candidate.** Offline 5.2 vs live 2.6 — superb
   quality/value, low story exposure. Watch as the BR-class narrative-
   blind override case.

## Data / pipeline hygiene

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

6c. **Checkpoint inflow stops when the birth queue drains.** New
   predictions (narrative_checkpoints) are only created at company-
   narrative BIRTH (company_narrative.py:294): 140+32+48+32 during the
   Aug 4-7 birth drain, zero since — through peak earnings season.
   Existing dossiers never gain fresh predictions. Design decision
   needed (ties to P3 shadow lane + the product dossier page): should
   new typed claims on existing narratives mint checkpoints?

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
