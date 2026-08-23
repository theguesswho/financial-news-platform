# V3 #15 — anchored story grading: cutover build spec

Session opener for the FIRST sitting (Edmund types exactly this,
nothing more):
**"Read V3_15_CUTOVER_SPEC.md and V3_15_STORY_GRADING_DESIGN.md. Do
Sitting 1 (Phase 0–1). Present the GATE 1 sentence. Stop."**

Status: OPEN. Design and shadow validation live in
V3_15_STORY_GRADING_DESIGN.md (read it FIRST — the rubric text,
shadow results, and rejection rationale are there and are BINDING;
this file is the build procedure). CLAUDE.md + STANDING BRIEF bind.
This IS a scoring change (narrative_strength feeds
compute_call_vs_filing_gap in the live scorer) → full freeze
discipline.

## Sittings (amended 2026-08-22, external review) — the ONLY way
## through this spec
- SITTING 1: Phase 0–1 only, then present the GATE 1 quote sentence.
  STOP — whether or not Edmund replies.
- SITTING 2: starts ONLY after Edmund has replied "approved" to the
  GATE 1 sentence IN THAT SITTING. Phase 3 backfill only. STOP.
- SITTING 3: Phase 4, ending at the GATE 2 presentation. Phase 5–6
  run ONLY after Edmund replies "cut over" AND is at the Railway
  dashboard and has said "push".
Running "continue from the Checklist" straight through to CLOSED is
FORBIDDEN. A gate with no reply ends the sitting with state recorded.
Consent is never carried over from the scoping conversation or a
previous sitting — each gate's words are given fresh, in that
sitting.

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
- SYNOPSIS PARITY (Edmund 2026-08-21): the v2 output adds "synopsis"
  — 2–4 sentences in the 8-K events style, grounded in the SAME cited
  numbers the band evidence uses (the WMT one-liner vs the Sysco
  paragraph was the gap: calls/10-Ks stored ~130 chars, 8-Ks ~420).
  Stored into the same llm_analysis synopsis slot the wire already
  displays — no display change needed; the backfill fills 18 months
  of history at marginal output-token cost (fold into the GATE 1
  quote — roughly +$5–10). AMENDED (Edmund 2026-08-22, Sitting 2): a
  synopsis that states figures not present in the evidence list — or
  is missing/mis-sized — is NO LONGER fatal to the output. The grade
  stores; the synopsis is DROPPED (never stored or applied) and the
  row is logged as synopsis_dropped in the audit log. Rationale: the
  resumed overlay was rejecting ~27% of grades over a field the
  backfill does not even store (write_synopses=False). Only the PAG
  evidence rule below invalidates an output.
- VALIDATION RULE (from the PAG defect): an output whose strength
  band has no non-empty cited evidence string is INVALID → retry
  (max 3) → on final failure store NOTHING for that filing and count
  it; never store an unevidenced grade, high or low.
  AMENDED (Edmund 2026-08-22, Sitting 2): this fatal class covers
  evidence and vocabulary only. Synopsis figure/length defects store
  the grade, drop the synopsis, and log synopsis_dropped (see the
  synopsis-parity amendment above). The PAG rule itself is unchanged
  and was NOT loosened.
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
COVERAGE RULING (Edmund 2026-08-22, GATE 1 finding accepted; the
4,919 / 9,098 counts verified): re-extract ONLY the 4,919 filings
that still have source text. Do NOT re-fetch the 4,179 text-less
rows from the vendor.
- COPY-THEN-OVERLAY: create filing_themes_v2 as a COPY of live
  filing_themes — ALL ~9,098 window rows, carried with
  rubric_version=1 — then overlay v2 extractions onto the 4,919
  with text. The 4,179 stay era-1. Phase 5 swaps this FULL table.
  A 4,919-row side table is FORBIDDEN — swapping it would delete
  the era-1 grades.
- Sitting 2 writes go to table=filing_themes_v2 ONLY, with
  write_synopses=False. Do NOT UPDATE filings.llm_analysis —
  synopses wait for cutover. Live filing_themes is NOT written in
  this phase; the scorer, wire, and Streamlit all keep reading v1.
  No deploy, no push — LLM + side writes only, safe during scheduler
  slots (verify the DB user's connection headroom; throttle workers
  if the scheduler is mid-run).
- run_extraction_v2's DEFAULT table stays filing_themes; Sitting 2
  must pass the side table explicitly on every call.
- Resumable (skip filing_ids already stamped rubric_version=2),
  progress-logged, failures listed by id (a failed overlay leaves
  the copied era-1 row in place). ERROR BUDGET: >2%
  invalid-after-retries → STOP, report the failure list, do not
  proceed to Phase 4.
- Trajectory prior-artifact context comes from V2 rows where they
  exist (process oldest→newest so each filing's prior is same-era),
  v1 rows before the window's start.
- SITTING 2 STOP RECORD (2026-08-22): two overlay runs stored 344
  era-2 rows, then Edmund stopped the second run at a 26.8% reject
  rate (34 of 127 resumed attempts; run 1 was 12.9%). The rejects
  were overwhelmingly synopsis-only (figures-not-in-evidence /
  length) — grades discarded over a field this phase does not store.
  Ruling: the synopsis_dropped amendment above; rejected rows stay
  era-1 and re-extract on the next overlay run (they are still
  rubric_version<2). Overlay NOT resumed in that chat — next sitting
  restarts it under the amended validator.
- CONSEQUENCE FOR PHASE 4 (ruled here 2026-08-22): the swapped
  table is mixed-era, so Phase 4 must show TWO board diffs —
  mixed-era (all rows on the side table) AND within-era
  (rubric_version=2 rows only). Edmund rules at GATE 2 which gap
  the live scorer uses.

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
  INJECTION PATH (amended 2026-08-22): running the real scorer and
  the gap query against the SIDE table requires a named injection
  point — an env var or argument (e.g. FILING_THEMES_TABLE=
  filing_themes_v2) consumed by compute_call_vs_filing_gap and any
  other filing_themes reader in the offline path. Offline only —
  the deployed default stays the live table. If the injection point
  does not exist, STOP and add it as a reviewed code change FIRST;
  NEVER hand-copy the formula into a parallel script.
- WIRE-COUNT ARTIFACT (amended 2026-08-22 — shown BEFORE Edmund is
  asked to cut over): count the items passing the current >=0.60
  display floor under v1 vs v2 over the same window /wire uses. The
  new mode is 0.5–0.6, so starvation is EXPECTED, not a surprise.
  If the v2 count is <5, present the floor options AT THIS GATE
  (keep 0.60 / drop to 0.50 / drop the floor) with the counts each
  would give — do NOT wait for three thin editions to force the
  question. Phase 6's three-edition watch applies only if 0.60 is
  kept.
- STOP CONDITIONS: any flip NOT traceable to the gap input; >5
  membership changes; a tier change of more than one step on any
  name. Otherwise present to Edmund: "Board diff under the new
  grading: <summary>. Reply 'cut over' to swap and push." No reply →
  STOP, everything recorded, side table kept, end session.

## Phase 5 — cutover (REWRITTEN 2026-08-22, external review: reader
## code ships BEFORE the data swap — the old swap-then-push order
## would have /wire serving 'promotional' into v1 pills)
All inside ONE Edmund-at-Railway window, outside the deploy-gate
slots (05:50–07:00, 21:50–23:00 UTC; Fri 23:20–00:40):
a. PAUSE the scheduler (or prove by CLI that no job is running and
   none fires inside the window).
b. Push READER-TOLERANT code first: wire/web accept
   grounded/promotional, and any unknown tone vocabulary renders as
   plain text — prove Streamlit's EXISTING fallback renders unknown
   vocab as plain gray (verify only; NO Streamlit edits). This is
   push #1.
c. COPY live filing_themes → filing_themes_v1_archive (prefer COPY
   over RENAME if anything references the table by name — foreign
   keys, views, matviews; check and STATE WHICH was found and why
   the choice). Prove row counts match before proceeding.
d. SWAP the side table in as filing_themes in ONE transaction.
   Immediately hit local /wire + run the gap query — both must
   succeed on the swapped table.
   d2. ERA ENV VAR (Edmund's era ruling 2026-08-23): set
   FILING_THEMES_RUBRIC_ERA=2 on the Railway scheduler service IN
   THIS SAME WINDOW, before the scheduler is re-armed — the ruling
   is WITHIN-ERA, and the code's default (no filter) would read
   mixed-era. Verify with `railway variables`. The Phase 5e commit
   must also fix the "offline-only knobs" comment at the injection
   point in pipeline/hidden_gem_scorer.py — after this ruling the
   era var is a PRODUCTION setting. (FILING_THEMES_TABLE stays
   unset in prod: after the swap, the live table IS the v2 data.)
e. Extractor v2 goes live ONLY AFTER the swap, still in this window,
   so new rows stamp rubric_version=2 into the v2 table: commit the
   extractor change, Edmund says "push" (push #2), verify on prod:
   /wire 200 with sane grades, scheduler resumed/re-armed.
   NOTE (desk, 2026-08-22): two pushes in one window brushes the
   no-back-to-back-rebuilds rule; the mitigation is the paused
   scheduler (a) and push #2 being extractor-only. Watch each
   rebuild green before the next step; if push #1 goes unhealthy,
   the window ABORTS before any data is touched.
f. platform_notes row (active ~7 days): story grades re-anchored
   platform-wide; lower numbers are the new honest scale, not
   company deterioration. The assessor must never narrate the
   re-grade as company news.
DEFAULT: do NOT start a long local extractor run against prod inside
this window — side-table workers belong to Sitting 2 only; if a
scheduler job is mid-run during Sitting 2, throttle workers.

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

## SITTING 1 RECORD (2026-08-22, Sat 03:15–05:30 UTC — outside all slots)

### Phase 0 — consumer sweep (every reader of filing_themes
### narrative_strength / trajectory / management_tone; verdicts)
| Consumer | Reads | Verdict on v2 vocab (grounded/promotional added) |
|---|---|---|
| pipeline/hidden_gem_scorer.py:134 compute_call_vs_filing_gap | strength (numeric) | OK — numeric only |
| pipeline/hidden_gem_scorer.py:863 velocity guard | EARN_CALL trajectory, matches "decelerating" | OK — trajectory vocab UNCHANGED in v2; but v2's higher decelerating share (33% shadow vs 7.5%) will trip it more often. SECOND scorer path beyond the gap — Phase 4's real-scorer board diff must run with the side table injected for BOTH reads |
| pipeline/hidden_gem_scorer.py:887 divestiture guard | raw_themes/catalysts ILIKE | OK — text search, v2 keeps themes |
| api/routers/wire.py | strength floor 0.60, trajectory/tone passed RAW | OK (no crash); "management grounded/promotional" wording lands via web pill labels in Phase 5b |
| api/routers/stocks.py | strings passed through | OK — tolerant |
| web/app/wire/page.tsx:87 | renders `management {tone}` plain text | OK (renders any word); label wording = Phase 5b work |
| web/components/mock/CallsStack.tsx | tone/trajectory raw text | OK — tolerant |
| ui/Home.py + ui/pages/6_News_Wire.py | tone NEVER pilled (only fed to synopsis prompt); trajectory_pill has gray fallback `mapping.get(..., ("pill-gray", raw))` | VERIFIED graceful — no ui/ change needed |
| ui/pages/5_Stock_Detail.py:363 tone_badge | "conf"/"caut" substring else badge-mixed (CSS exists :102) | OK — grounded/promotional render as neutral gray badge with the word |
| scheduler(_light).py synopsis step (653/931) | trajectory/tone → synopsis prompt; gate strength>=0.60 | OK — prompt strings; post-cutover mostly no-op (v2 writes synopses itself) |
| pipeline/qual_assessor.py:221, narrative_override.py | strings into assessor prompt | OK — tolerant (new vocab is informative) |
| company_narrative, exposure_ledger, deep_dive, daily_report:324 | strings/text into prompts | OK — tolerant |
| meta_theme_builder, embedding_builder | themes text + strength weight + embedding col | OK vocab-wise. NOTE: side-table v2 rows will have NULL embeddings — post-cutover re-embed pass needed (embedding_builder self-heals on NULL) before stock_theme_alignment rebuild |
| pipeline/earnings_ingestion.py:158 | CALLS extract_themes_from_filing+store_themes inline | flip site: Phase 5e's extractor commit MUST also route this through v2 or new transcripts write era-1 rows post-swap |
No out-of-scope breaker found. No SELECT *; single INSERT (explicit
columns) → additive rubric_version column is safe everywhere.

### Phase 1 — extractor v2 (pipeline/narrative_extractor.py)
- v2 implemented alongside v1; run_extraction dispatches to v2 only
  when RUBRIC_V2=1 (default v1) so a stray pre-cutover deploy cannot
  write v2 grades. Grading text transcribed verbatim from the shadow
  script (scratchpad shadow_regrade.py); groundedness rides the
  management_tone column; prior selection = latest (filing_date,
  filing_id) strictly before, side-table-first for the backfill.
- Validation (PAG rule + synopsis parity): no non-empty evidence →
  INVALID; synopsis 80–700 chars, figures must appear in evidence
  (years/Q-refs/form numbers exempt); vocab enforced; retries carry
  the rejection reason back; max 3 attempts then store NOTHING.
- Smoke (12 sampled, 9 with text, REAL calls, nothing stored): 9/9
  valid. Calls 0.80–0.85 grounded (EVR/ACM/HON), filings mostly 0.5
  cautious, BKH 0.7 grounded — gap signal survives, shadow shape
  reproduced. Mean synopsis 535 chars.
- Unit proofs: PAG empty/blank/high-band-no-evidence all rejected;
  orphan synopsis figure rejected; old vocab ("confident",
  "improving") rejected; stub client → exactly 3 attempts then
  (None, reason), nothing stored. EL 08-19 same-day pair: 10-K
  (id 22931) sees the call (id 22903, same date, lower id) as prior;
  the call sees EARN_CALL 2026-05-01 — deterministic order holds.
- PENDING (permission-blocked): the era-stamp DDL itself. The session
  classifier denied prod DDL; scripts/migrate_rubric_version.py is
  written (additive, idempotent, lock_timeout 5s) and must be run
  before Sitting 2 — unit proof "stores with rubric_version=2" runs
  then. Nothing else depends on it.

### GATE 1 measurements (2026-08-22)
- Window at run time: 9,098 rows (4,385 calls / 3,831 10-Q / 882
  10-K). FINDING: only 4,919 still have source text (calls 1,859,
  10-Q 2,385, 10-K 675). 4,179 rows (46%) have master_analysis AND
  content both NULL — text loss is age-graded (0% this quarter → 97%
  at the window edge). They CANNOT be re-extracted; full one-era
  window as designed is not achievable without re-fetching old
  documents from the vendor. Options put to Edmund at the gate.
- Measured (count_tokens on 22 exact assembled prompts): mean input
  11,492 tok. Measured (9 real extractions): mean output 1,382 tok,
  mean wall 32.3s incl. retries, ~1.3 attempts/filing.
- Haiku 4.5: $1/M in, $5/M out → $0.0184/filing single-attempt,
  ≈$0.024 with measured retry rate. 4,919 × ≈$0.024 ≈ $115 (synopsis
  cost folded in). 4,919 × 32.3s ÷ 12 workers ≈ 3.7h.

## SITTING 3 RECORD (2026-08-23 — Phase 4 only, all offline reads;
## live filing_themes never written, no push, no deploy)

### Injection point (added this sitting, reviewed code change)
pipeline/hidden_gem_scorer.py: FILING_THEMES_TABLE env var (identifier-
validated, default "filing_themes") consumed by ALL three filing_themes
reads — gap, velocity guard, divestiture guard; FILING_THEMES_RUBRIC_ERA
adds `AND ft.rubric_version = N` to the GRADED reads only (gap strength,
velocity trajectory) — the divestiture guard is a text search, not a
graded field, so era-1 divestiture disclosures keep standing down the
penalty in within-era mode. Both unset in deployment → byte-identical
behavior. Verified inert-by-default + injection-guard unit checks.
Change is LOCAL-ONLY until Phase 5's push.

### Distribution (18-mo window; v1 = live, v2 = side-table era-2 rows)
- Strength means (v1 → v2): calls 0.882 → 0.767 (median 0.92 → 0.78);
  10-Q 0.680 → 0.521 (median 0.65 → 0.50); 10-K 0.734 → 0.558
  (median 0.75 → 0.50). Filings mode band 0.5–0.59: 7.6% → 59.6%.
  Calls 0.85+: 78.2% → 24.2%. Paired per-row delta (n=4,917): mean
  −0.170, 96.8% down / 1.4% same / 1.8% up. Shadow shape REPRODUCES
  (shadow: mean 0.77→0.59, median →0.50, mode 0.5–0.6).
- Trajectory (v2): 27.9% accelerating / 56.4% stable / 15.7% decel
  (v1: 66.2/25.3/7.4). Accelerating matches shadow (26%); decel 15.7%
  vs shadow 33% — FINDING, explained: prior-artifact availability is
  age-graded (2025-Q2 rows: 0.9% decel, 94.5% stable — no in-window
  prior to compare; recent quarters 14–24%), and the shadow's 141
  deliberately included trouble cases (EL/LHX/ACM). Not a rubric
  drift; presented at the gate, Edmund rules.
- Tone/groundedness (v2): grounded 2,416 / cautious 1,972 /
  promotional 280 / defensive 249 — new vocabulary present at scale.

### Gap movers (normalised gap, v1 → mixed; top 20 by |change|)
MSFT +0.283, PSKY +0.255, AMZN +0.252, RYN +0.217, NVDA +0.216,
DOCN +0.200, SITM +0.199, FOX +0.198, NWS +0.196, GH +0.194,
GOOGL +0.194, AAPL +0.184, WTS +0.178, CDE +0.177, CRDO +0.173,
IREN +0.161, SGI +0.160, NVT +0.159, HALO +0.156, PATH +0.156.
Era-mix audit of the 20: MSFT/NVDA (6/0) and AAPL/AMZN/GOOGL/FOX (5/1)
and NWS (5/0) have era-1-dominated CALLS vs all-era-2 FILINGS — their
widening is partly the old scale meeting the new one, by construction.
The other 13 are all-era-2 both sides (genuine). Within-era mode
inverts the problem: those 7 fail the ≥2-era-2-calls qualifier and
fall to neutral 0.500. Qualifying symbols: 806 (v1) / 806 (mixed) /
315 (within-era).

### Board diffs (real scorer, 3 runs same sitting: baseline/mixed/era2;
### baseline reproduces latest snapshot — 4 symbols price-drifted >0.02)
MIXED-ERA vs baseline: 2 flips, both 1-step raw entries, both already
seated on today's displayed board → 0 displayed-membership changes.
  LMT None→Watch gem 0.336→0.342 [cfg 0.620→0.714; E 0.826→0.844]
  TDG None→Watch gem 0.339→0.341 [cfg 0.676→0.718; E 0.935→0.944]
STOP-check: untraced 0; membership 2 raw / 0 displayed; >1-step 0. PASS.
WITHIN-ERA vs baseline: 13 flips, all 1-step, all cfg-traced:
  ARE  Watch→None 0.345→0.334 [cfg 0.645→0.500]  (seat survives, >0.32)
  BDX  Watch→None 0.340→0.327 [cfg 0.743→0.500]  (seat survives)
  ES   Buy→Watch  0.364→0.347 [cfg 0.752→0.500]
  FTAI Buy→Strong Buy 0.453→0.463 [cfg 0.697→0.845]
  GDDY Strong Buy→Buy 0.468→0.453 [cfg 0.666→0.500]
  NOC  Watch→None 0.342→0.331 [cfg 0.712→0.500]  (seat survives)
  NRG  Watch→None 0.340→0.328 [cfg 0.726→0.500]  (seat survives)
  PNR  Watch→None 0.348→0.329 [cfg 0.688→0.500]  (seat survives)
  PSN  None→Watch 0.336→0.342 [cfg 0.615→0.719]  (already seated today)
  PTC  Buy→Watch  0.366→0.350 [cfg 0.742→0.500]
  SF   Watch→Buy  0.356→0.361 [cfg 0.785→0.851]
  TEL  Watch→None 0.351→0.336 [cfg 0.734→0.500]  (seat survives)
  TPL  Strong Buy→Buy 0.461→0.443 [cfg 0.729→0.500]
STOP-check: untraced 0; >1-step 0; membership 7 RAW (crosses the >5
line) but 0 DISPLAYED (all six exits hold seats above BOARD_EXIT 0.32;
PSN already seated) — flagged, Edmund rules whether raw or displayed
counts govern. The eight →0.500 moves are all no-qualify fallbacks
(fewer than 2 era-2 calls), i.e. signal LOSS, not re-grading.
Side effects, no tier impact: velocity guard +DPZ/FBIN/INGR/OTIS
(mixed; v2's higher decel share, as Sitting 1 predicted); divestiture
guard 12 gain / 42 lose the stand-down (re-extracted themes wording
changed ILIKE matches) — largest affected gem 0.29 (STWD −0.142), all
far below Watch.

### Wire-count artifact (>=0.60 floor, /wire's own 14-day window,
### graded lane only; 8-K lane untouched)
v1 65 items pass 0.60; v2 35 pass (all 67 window rows are era-2 —
recent filings all have text). ≥5 → floor options NOT triggered at
this gate; Phase 6's three-edition watch applies if 0.60 kept.
Reference: v2 at 0.50 floor = 61; no floor = 67; delta-rescued
(<0.60, |Δ|≥0.12) rises 1 → 12 — the wire tilts call-heavy, filings
enter mostly via the delta trigger.

### GATE 2 state
Presented 2026-08-23. Edmund pre-stated he would not reply "cut over"
in that chat → sitting ends with NO cutover approval; Phase 5–6 not
started. Side table kept. Open ruling for the cutover sitting: which
gap the live scorer uses (mixed-era vs within-era) + the raw-vs-
displayed membership count question above. Scorer injection change is
local-only and inert; it ships with Phase 5b's reader-tolerant push.

RULINGS (Edmund, same chat, 2026-08-23, verbatim: "Phase 4 accepted.
Era ruling: within-era. Displayed membership governs the >5 stop (0
displayed changes — pass). Keep the 0.60 floor; three-edition watch.
Do not regenerate the 1,348 dropped synopses."):
1. ERA: the live scorer uses the WITHIN-ERA gap — production must run
   with FILING_THEMES_RUBRIC_ERA=2 from the moment the table swaps
   (Railway env var, set inside the Phase 5 window — see the Phase 5
   amendment). Without it the deployed default reads mixed-era, which
   is now a MISCONFIGURATION, not a fallback. Applies to the graded
   reads (gap + velocity guard); divestiture text search stays
   era-unfiltered by design.
2. STOP ACCOUNTING: displayed membership governs the >5 condition.
   Within-era diff = 0 displayed changes → PASS.
3. WIRE FLOOR: 0.60 kept; Phase 6's three-edition watch applies.
4. SYNOPSES: the synopsis_dropped rows are NOT regenerated. Their
   grades stand; those filings simply keep whatever llm_analysis
   synopsis they already have.
"cut over" was NOT said — GATE 2 approval remains OPEN. Phase 5–6
still require "cut over" AND "push" with Edmund at Railway, fresh in
that sitting.

## Checklist (evidence pasted inline, top to bottom)
- [x] 0. [Sitting 1] Consumer sweep list + per-consumer vocabulary
       verdicts — DONE 2026-08-22, table above; no out-of-scope
       breaker; two flip sites + embedding note recorded
- [x] 1. [Sitting 1] Extractor v2 + validation + unit proofs — DONE
       2026-08-22 (record above) EXCEPT era-stamp DDL: blocked by
       session permissions; scripts/migrate_rubric_version.py ready,
       run before Sitting 2, then paste the rubric_version=2 store
       proof
- [ ] 2. [Sitting 1 ends here] GATE 1 quote (rewritten 2026-08-22
       per Edmund's coverage ruling; Sitting 1 accepted, counts
       verified):
       "Re-extracting 4,919 filings (overlay on a full 9,098-row
       copy; 4,179 stay era-1) will cost ≈ $115 and take ≈ 4 hours
       at 12 workers — reply 'approved' to run."
       APPROVED — Edmund, this chat, 2026-08-22 (Sitting 2), verbatim:
       "Approved". Era-stamp DDL run first (04:45 UTC, outside slots):
       rubric_version smallint NOT NULL DEFAULT 1 confirmed, all
       10,541 rows era 1.
- [ ] 3. [Sitting 2] Backfill complete per the coverage ruling:
       copy-then-overlay (filing_themes_v2 = full ~9,098-row copy,
       v2 overlaid on the 4,919 with text), write_synopses=False
       (no UPDATE to filings.llm_analysis), writes to the side
       table ONLY (passed explicitly — default stays
       filing_themes); counts + failure list + error rate pasted
       (<=2%)
       IN PROGRESS 2026-08-22: 344 era-2 stored; stopped by Edmund
       at 26.8% synopsis-only rejects; validator amended
       (synopsis_dropped — see Phase 1/3 amendments); resume in a
       fresh sitting
       RESUME RECORD 2026-08-22 (Sitting 2b, 06:24–08:20 UTC): overlay
       resumed under the amended validator. Batch 1 (450 @ 6 workers,
       throttled — daily slot mid-run): 450 stored, 0 failed, 239
       synopsis_dropped, error rate 0.00%. Main run (12 workers):
       1,484 stored, 0 rubric failures, then the Anthropic API
       returned "credit balance is too low" — 71 attempts failed on
       credits before the run was killed (futility, not the error
       budget; zero PAG/vocab failures across the whole sitting).
       STATE: 2,278 era-2 in filing_themes_v2 (344 prior + 1,934 this
       sitting), 2,641 with-text rows remaining (sums to 4,919 ✓),
       live filing_themes still zero era-2. Credit-failed rows stay
       era-1 and re-select on resume. Synopsis_dropped running at
       ~53% — expected under the amendment, synopses are not stored
       this phase anyway. BLOCKED on Edmund topping up API credits;
       then rerun scripts/backfill_v3_15.py - 12 (resumable).
       COMPLETE (verified at Sitting 3 open, 2026-08-23): side table
       holds 4,917 era-2 + 4,181 era-1 = 9,098 rows; live
       filing_themes all era-1, untouched. 2 of 4,919 with-text rows
       failed after retries — MSFT call 19718 and RVMD call 22332,
       both "output truncated (max_tokens)" (mechanical, not rubric;
       zero PAG/vocab failures). Error rate 0.04% ≤ 2% budget. Both
       stay era-1 and would re-select on any future overlay run.
       NOTE: MSFT's era-1 call is why MSFT tops the mixed-era gap
       movers (old-scale call vs re-anchored filings) — see Sitting 3.
- [ ] 4. [Sitting 3] GATE 2: distribution + gap movers + board diff
       (real scorer via the named injection path) + WIRE-COUNT
       artifact (v1 vs v2 items over the >=0.60 floor; floor options
       presented here if v2 <5) pasted; Edmund's cutover approval
       quoted (or STOP recorded)
       EVIDENCE PRODUCED 2026-08-23 (Sitting 3 — full record below):
       injection point added (FILING_THEMES_TABLE +
       FILING_THEMES_RUBRIC_ERA in pipeline/hidden_gem_scorer.py,
       offline-only, deployed default = live table, era filter on
       graded reads only); distribution reproduces the shadow's
       strength shape; both board diffs run through the real scorer,
       every flip 1-step and gap-traced; wire 0.60-floor count v2=35
       (≥5, no floor options required). GATE 2 sentence presented;
       Edmund stated in advance he will NOT reply "cut over" in that
       chat — NO APPROVAL RECORDED; cutover awaits a future sitting
       with fresh consent. Findings for Edmund's era ruling: (a)
       within-era diff has 7 raw-tier membership changes (>5 line) but
       0 displayed-membership changes (hysteresis + existing seats);
       mixed-era has 2 raw / 0 displayed;
       RULED 2026-08-23 (Edmund, next message in same chat): Phase 4
       ACCEPTED. Era = WITHIN-ERA (prod needs
       FILING_THEMES_RUBRIC_ERA=2 at swap — Phase 5 d2). Displayed
       membership governs the >5 stop → pass. 0.60 floor kept,
       three-edition watch. Dropped synopses NOT regenerated.
       "cut over" still NOT said — cutover approval remains open for
       the Phase 5 sitting. (b) mixed-era gap inflates
       for symbols whose calls lost text (era-1 calls vs era-2
       filings: MSFT/NVDA/AAPL/AMZN/GOOGL/FOX/NWS in the top movers);
       within-era instead drops them to neutral 0.500 (need ≥2 era-2
       calls); (c) decelerating share 15.7% at scale vs shadow 33% —
       age-graded prior availability (early-window rows had no
       in-window prior → "stable"; recent quarters 14–24%) plus the
       shadow's trouble-case sampling; (d) re-extracted themes text
       changes the divestiture guard's ILIKE matches (12 gain / 42
       lose the stand-down) — no affected name within 0.05 of the
       Watch line; (e) v2 velocity guard adds DPZ/FBIN/INGR/OTIS
       (mixed), no tier effect.
- [x] 5. [Sitting 3, after "cut over" + "push"] Scheduler paused /
       no-job proven; reader-tolerant push BEFORE data swap;
       copy-then-swap with row-count proof (copy-vs-rename choice
       stated); extractor v2 pushed only after the swap; prod verify
       (wire grades sane, scheduler re-armed); platform_notes row id
       noted
       DONE 2026-08-23, 03:59–04:55 UTC window (Edmund at Railway;
       consent fresh in-sitting: "Do Phase 5 only" + "push" ×2):
       (a) no-job PROVEN, no pause: scheduler_runs all finished (last:
       daily Sat 06:00, finished 07:00:14); no cron before 06:00;
       catch-up lookback 45m/dead-run 20h cannot fire on restart.
       (b) push #1 f074e6e = scorer injection only — wire/web verified
       ALREADY tolerant (raw pass-through, plain-text render); Streamlit
       gray fallback proven (News Wire trajectory_pill pill-gray
       fallback; Stock Detail tone_badge → badge-mixed neutral gray),
       zero ui/ edits. All services green; prod /wire 200 after rebuild.
       AMENDMENT (Edmund approved in-window, "ok to top up"): live had
       10,542 rows vs side table 9,098 — 1,443 pre-window era-1 rows +
       LOW EARN_CALL 2026-08-19 (extracted by Sat's daily after the
       copy) would have been DELETED by the swap. Topped up side table
       with all 1,444 verbatim (still era-1) → exact superset, 0 diff
       both directions; invisible to graded reads (era filter +
       windows), Phase 4 board diff unaffected. LOW's call stays era-1
       (won't re-extract — extractor selects rows with no themes row).
       (c) COPY chosen: zero FKs / views / matviews reference
       filing_themes; the one by-name dependency is owned sequence
       filing_themes_id_seq (rename-archive would leave it owned by the
       archive; copy keeps the archive independent).
       filing_themes_v1_archive proven identical: 10,542 rows, matching
       COUNT/DISTINCT filing_id/SUM(id)=55,906,635/
       SUM(narrative_strength)=8368.6850.
       (d) one-transaction swap (lock_timeout 5s): re-own sequence →
       DROP proven-archived live → RENAME v2 in → constraint renamed to
       uq_filing_themes_filing → sequence re-owned to new live. Result:
       filing_themes 10,542 rows (4,917 era-2 / 5,625 era-1). Local
       /wire 200 (v2 vocab flowing, BJ call 8.5 grounded accelerating);
       within-era gap via the REAL scorer: 315 qualifying symbols —
       matches Sitting 3 exactly.
       (d2) FILING_THEMES_RUBRIC_ERA=2 set on the scheduler service,
       verified via railway variables (set --skip-deploys; applied by
       push #2's redeploy at 04:44, which postdates the var).
       FILING_THEMES_TABLE confirmed unset. "offline-only knobs"
       comment fixed in the 5e commit per the within-era ruling.
       (e) push #2 c456577 AFTER the swap: run_extraction defaults to
       v2 (RUBRIC_V2=0 = emergency v1 fallback), earnings_ingestion
       routed through extract_themes_v2/store_themes_v2 +
       write_synopsis (the flip site). Prod verify: /wire 200, 14
       items, tones grounded/cautious, signals on the new scale
       (8.5/7.2/5.0); scheduler re-armed 04:44 — daily 06:00,
       after-close Mon 22:00, weekly Fri 23:30.
       (f) platform_notes row id 5, active 2026-08-23 → 2026-08-30:
       lower numbers are the new honest scale, not company news.
       Post-cutover notes for Phase 6: era-2 rows have NULL embeddings
       — re-embed pass (embedding_builder self-heals on NULL) before
       stock_theme_alignment rebuild; item 6 next-edition check due
       after today's 06:00 daily.
- [ ] 6. Next-edition check: v2 grades flowing, zero unevidenced rows
- [ ] 7. Paperwork done (V2_CONSIDERATIONS, V3 #15 Done, FRONTEND_SPEC
       floor-watch); Status flipped CLOSED
