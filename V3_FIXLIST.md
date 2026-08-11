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
   **Fast-path fiscal/calendar key collision (ROOT CAUSE FOUND
   2026-08-11).** The fast path keys transcripts by CALENDAR quarter
   guessed from the 8-K date; FMP keys by the company's FISCAL quarter.
   For offset fiscal years (ACM ends Sep) the fast path's key collides
   with a PRIOR call's FMP row and ON CONFLICT DO NOTHING silently
   drops the new transcript — ACM's Aug-10 call collided with its May
   fiscal-Q2 row. Fix: derive the fiscal label (FYE month from
   fundamentals_annual) before keying, or key by call DATE. Affects any
   offset-FY reporter every quarter. ACM's call was hand-ingested under
   the correct fiscal key (Q3:2026) and all transcript-stale names were
   re-assessed 2026-08-11 (9 stocks, zero tier changes).

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

6. **Unprocessed-filings sweep.** ACM's 2026-05-12 10-Q has
   processed_at NULL (content never analyzed). Count the class
   (processed_at IS NULL by type/date), find the cause, drain it.

7. **OZK filing-mapping** still open (chunk-3 exclusion note).

8. **Assessor cache hit rate** — verify the warm-up fix moved ~55% to
   ~85% in llm_usage after a week of runs (check ~Aug 16).

## Standing gates (not fixes, reminders)

- Chunk 4 + ALNY/LITE/SNDK additions stay gated behind the board-size
  tripwire (>75 tiered -> proposal first).
- Watch-path isolation still unproven for web-only pushes (CLAUDE.md
  rule; the recent scheduler deploys were pipeline pushes, so no test
  yet).
