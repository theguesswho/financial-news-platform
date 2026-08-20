# V3 #15 — anchored story grading: cutover build spec

Session opener (Edmund types exactly this, nothing more):
**"Read V3_15_CUTOVER_SPEC.md and continue from the Checklist."**

Status: OPEN. Design and shadow validation live in
V3_15_STORY_GRADING_DESIGN.md (read it FIRST — the rubric text,
shadow results, and rejection rationale are there and are BINDING;
this file is the build procedure). CLAUDE.md + STANDING BRIEF bind.
This IS a scoring change (narrative_strength feeds
compute_call_vs_filing_gap in the live scorer) → full freeze
discipline. TWO HARD GATES inside this session require Edmund's
in-session reply; if he is not present at a gate, STOP there, record
state, end the session. Nothing after a gate runs without his words.

## Scope — exactly this, nothing else
IN: pipeline/narrative_extractor.py (rubric v2 + validation), a
rubric_version era stamp, an offline side-table backfill, the offline
consumer/board diff, the cutover swap + push, paperwork, wire tone
vocabulary handling in api/routers/wire.py + web pill labels.
OUT (do not touch): Streamlit (graceful degradation only — VERIFY its
pill fallback renders unknown vocab as plain gray text, change
NOTHING in ui/); 8-K impact anchors (design section D — SEPARATE
later session); believability population (separate item); the wire's
>=0.60 display floor (see Phase 6 — monitored, not changed); any
other scoring math; the momentum calibration.

## Phase 0 — consumer sweep (evidence before code)
Enumerate EVERY reader of filing_themes.narrative_strength /
trajectory / management_tone (grep pipeline/, api/, ui/ and paste the
list). Known: hidden_gem_scorer.compute_call_vs_filing_gap (numeric —
unaffected by vocabulary), api/routers/wire.py + web pills
(vocabulary — needs the new groundedness terms), ui News Wire
(fallback-verify only), daily_report? qual_assessor context? — find
out, verify each handles the v2 vocabulary (grounded/promotional
added; confident/cautious/defensive still possible in old-era rows),
record per-consumer verdicts. Any consumer that would BREAK on new
vocab and is out of scope → STOP and report before coding.

## Phase 1 — extractor v2 + validation
- Implement the rubric EXACTLY as V3_15_STORY_GRADING_DESIGN.md
  sections A/B/C, prompt including: anchored bands with the cap-at-
  0.6-without-cited-numbers rule; trajectory vs the company's OWN
  prior artifact (prior filing's claims passed in; deterministic
  prior selection: latest (filing_date, filing_id) strictly before
  this one — same tiebreak class as the wire delta fix); groundedness
  vocabulary. The shadow script's prompt is the validated reference —
  transcribe it faithfully, don't re-draft from memory.
- VALIDATION RULE (from the PAG defect): an output whose strength
  band has no non-empty cited evidence string is INVALID → retry
  (max 3) → on final failure store NOTHING for that filing and count
  it; never store an unevidenced grade, high or low.
- Era stamp: filing_themes gains rubric_version SMALLINT NOT NULL
  DEFAULT 1; v2 writes stamp 2. Schema change is additive only.
- Unit proofs (paste): a synthetic no-evidence output is rejected and
  retried; a valid output stores with rubric_version=2; prior-claims
  context assembles correctly for a same-day pair (EL 08-19: the call
  must see the 10-K or vice versa per the deterministic order, state
  which).

## Phase 2 — GATE 1: the backfill quote (Edmund's reply required)
Compute the FIRM cost: count = filing_themes rows in the scorer's
18-month window at run time (~9,094 on 2026-08-20; 4,385 calls /
3,829 10-Qs / 880 10-Ks), × measured mean tokens from the shadow run,
at Haiku prices. Present one sentence: "Re-extracting N filings will
cost ≈ $X and take ≈ Y hours at 12 workers — reply 'approved' to
run." If no reply / not present: STOP HERE, record Phases 0–1 done,
end session. NEVER start the backfill on inferred consent.

## Phase 3 — backfill to a SIDE table (live untouched)
- Create filing_themes_v2 (same shape + rubric_version=2). Backfill
  the 18-month window INTO THE SIDE TABLE via the v2 extractor.
  Live filing_themes is NOT written in this phase; the scorer, wire,
  and Streamlit all keep reading v1. No deploy, no push — LLM + side
  writes only, safe during scheduler slots (verify the DB user's
  connection headroom; throttle workers if the scheduler is mid-run).
- Resumable (skip already-present filing_ids), progress-logged,
  failures listed by id. ERROR BUDGET: >2% invalid-after-retries →
  STOP, report the failure list, do not proceed to Phase 4.
- Trajectory prior-artifact context comes from V2 rows where they
  exist (process oldest→newest so each filing's prior is same-era),
  v1 rows before the window's start.

## Phase 4 — GATE 2: offline diff + cutover sign-off (Edmund's reply)
All offline, against the side table:
- Distribution report: v1 vs v2 strength/trajectory/groundedness
  across the full window (the shadow's shape should reproduce at
  scale — if it does NOT, that is a finding: STOP and show).
- Consumer diff: compute_call_vs_filing_gap for every symbol, v1 vs
  v2 inputs; list the movers (top 20 by |change|).
- BOARD DIFF through the REAL scorer offline (never a parallel
  formula): score_all with the v2-based gap, today's other inputs
  fixed; diff displayed membership + tiers vs today's board. Paste
  every flip with its cause.
- STOP CONDITIONS: any flip NOT traceable to the gap input; >5
  membership changes; a tier change of more than one step on any
  name. Otherwise present to Edmund: "Board diff under the new
  grading: <summary>. Reply 'cut over' to swap and push." No reply →
  STOP, everything recorded, side table kept, end session.

## Phase 5 — cutover (only inside an Edmund-at-Railway push window)
Ordering matters — DB swap and code push must land in ONE window,
outside deploy-gate slots (05:50–07:00, 21:50–23:00 UTC; Fri
23:20–00:40), or new filings keep grading v1 into a v2 table:
1. Archive: rename live rows' table to filing_themes_v1_archive (or
   copy — state which, prove row counts match before and after).
2. Swap the side table in as filing_themes (single transaction;
   verify consumer reads succeed immediately after — hit local
   /wire + run the gap query).
3. Commit extractor v2 + wire/web vocabulary changes; Edmund says
   "push" at the dashboard; push; verify on prod: /wire 200 and
   items carry sane grades, scheduler restarted with jobs re-armed.
4. platform_notes row (active ~7 days): story grades re-anchored
   platform-wide; lower numbers are the new honest scale, not
   company deterioration. The assessor must never narrate the
   re-grade as company news.
5. The next after-close run grades new filings v2 — verify its wire
   edition the following morning (grades in the new distribution,
   zero unevidenced rows).

## Phase 6 — post-cutover paperwork + the floor watch
- V2_CONSIDERATIONS.md: dated entry — design pointer, shadow + full
  diff summaries, both gate quotes from Edmund verbatim.
- V3_FIXLIST #15 → Done (date + commit). This spec's Status →
  CLOSED.
- FRONTEND_SPEC dated update: wire vocabulary (groundedness pills),
  and the FLOOR WATCH: the wire's >=0.60 display floor now selects
  only 7+ stories under the honest scale — monitor item counts for
  3 editions; if the feed starves (<5 items), the floor decision
  goes to EDMUND with options, it is NOT changed silently.
- Do NOT delete filing_themes_v1_archive — it is the era-1 record.

## Guardrails
- The two GATES are absolute: no backfill without the quoted-cost
  approval, no cutover without the board-diff approval. Words from
  Edmund in the session, quoted in the checklist — never inferred,
  never carried over from this scoping conversation.
- Machinery does the grading — the session never hand-edits a grade,
  including "obviously wrong" ones; wrong grades are rubric or
  validation findings, reported not corrected.
- No `git push` unless Edmund has just said "push" AND is at the
  Railway dashboard. Local verifies: kill stale :8010/:3100 first.
- Streamlit untouched. Recorded ≠ fixed. Stop on any surprise.

## Checklist (evidence pasted inline, top to bottom)
- [ ] 0. Consumer sweep list + per-consumer vocabulary verdicts
- [ ] 1. Extractor v2 + validation + era stamp; unit proofs pasted
- [ ] 2. GATE 1 quote presented; Edmund's approval quoted (or STOP
       recorded)
- [ ] 3. Side-table backfill complete; counts + failure list + error
       rate pasted (<=2%)
- [ ] 4. GATE 2: distribution + gap movers + board diff pasted;
       Edmund's cutover approval quoted (or STOP recorded)
- [ ] 5. Swap + push + prod verify (wire grades sane, scheduler
       re-armed); platform_notes row id noted
- [ ] 6. Next-edition check: v2 grades flowing, zero unevidenced rows
- [ ] 7. Paperwork done (V2_CONSIDERATIONS, V3 #15 Done, FRONTEND_SPEC
       floor-watch); Status flipped CLOSED
