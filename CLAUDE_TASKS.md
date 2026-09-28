# CLAUDE_TASKS — open items for sittings Edmund opens

Created 2026-09-28 (Edmund). One entry per item; state OPEN / PARKED /
DONE with dates. Nothing here is built until Edmund opens a sitting for
it. Cross-references: `DESK.md` (shared board), `V3_FIXLIST.md`
(incident detail), `DATA_SCORECARD.md` (inputs and latencies).

## OPEN

### T1 — Narrative score moved for 800 of 822 names on 25 Sep 2026 and snapped back on 28 Sep. Unexplained. PARKED until October earnings are under way, unless it happens again.

Owner: a sitting Edmund opens later. Not now. (Edmund 2026-09-28:
neither he nor Grok ran anything against `filing_themes` on 25 Sep —
no re-grade, no backfill, no rubric-era change.)

What was observed (read-only, 2026-09-28):
- `leaderboard_history.narrative_score` changed for 800/822 symbols
  between the 09-24 and 09-25 snapshots (mean +0.026; 486 up, 314
  down) and for 800/822 between 09-27 and 09-28 (mean −0.026); 797
  returned to the EXACT 09-24 value. 09-25 → 09-26 → 09-27: 4 and 1
  changes. Same deployment throughout (`a53b08b4`, main `ea3d730`,
  deployed 2026-09-21 12:14 UTC). No re-extractions that week (only
  10 new filing_themes rows, all rubric 2, strengths 0.4–0.85). No
  narrative momentum/status flips in `narrative_history`. 2 exposure
  adds. `FILING_THEMES_RUBRIC_ERA=2` on the scheduler service now.
- Fingerprint = the call-vs-filing gap term of E
  (`hidden_gem_scorer.compute_call_vs_filing_gap`, 20% of E): the
  seven names with NO narrative exposures (E = 0.10 exactly) moved
  +0.04..+0.07 — only possible if they gained gap data — and every
  one of them (SJM, LULU, MOH, ROL, AZO, NKE, CNC) has exactly one
  era-2 call and eight era-1 calls: they qualify (≥2 calls) only
  under a MIXED-era read. The largest falls were SITM, SMTC, AHR —
  the holders of the biggest era-2 gaps, which shrink exactly when
  a larger gap enters the universe `max_gap`. Era-2-only read: 319
  qualifiers, max |gap| 0.464. Mixed read: 806 qualifiers, max |gap|
  0.550. So the 25–27 Sep runs read the mixed set; the 28 Sep run
  read era-2 again. Why is the open question.
- Knock-on: the assessor was woken for ES, DUK, FE, XYL, OMC as
  "movers" and wrote five "shifting" Buy→Watch verdicts on 27 Sep
  06:47 UTC on what was data noise, not company evidence.

The sitting, when opened:
1. Find out why the scorer read the mixed era-1 + era-2 row set from
   25 to 27 Sep with `FILING_THEMES_RUBRIC_ERA=2`. Candidates to test
   first: the child-process environment (jobs run as children since
   R1 — confirm `_rubric_era_clause()` sees the variable in the
   child; log the clause and the qualifier count at every re-score);
   any path that writes/updates `rubric_version` (a temporary 2 on
   era-1 rows would produce the same fingerprint); Railway logs for
   the 25–27 Sep runs (retention permitting).
2. Replace the universe-max normaliser on the call-vs-filing gap
   with a FIXED scale, so one extreme row can never shift every
   name's narrative score. Scoring change → freeze ritual,
   V2_CONSIDERATIONS entry, before/after board diff.
3. Mark the five 27 Sep "shifting" verdicts (ES, DUK, FE, XYL, OMC)
   as noise so they do not feed later reads (the assessor's
   continuity chain, qual_history, the report writer). Mechanism to
   be designed in the sitting — a flag the readers honour, never a
   hand-edited rationale (CLAUDE.md evidence-integrity rule 2).
4. Add to the sentinel / health checks: universe-wide E change count
   between consecutive snapshots above a threshold (e.g. > 25% of
   names) with no matching input change → alarm by name in the
   brief. Would have caught this on the 25th.

Out of scope for T1: #23 A+B, #24 C+D, embeddings/decay, FMP quota.
