# The Sealed Replay — narrative system walk-forward, design for review

Status: DESIGN FOR EXTERNAL REVIEW (2026-08-21). Nothing here is
built or scheduled. Edmund's originating idea, verbatim intent: run a
parallel narrative exercise OUTSIDE the actual system, gated as if
judged at the time (no future knowledge, no future price action),
everything in sequence, fed exactly as the live system ingests, using
the new (v2 anchored) methodology; assess what it found and created;
only then design an integration strategy. This document is the
methodology desk's max-effort assessment and design of that idea.
Reviewer questions are collected at the end.

## 1. What this is, and is not

IS: a walk-forward replay of the LIVING NARRATIVE SYSTEM (story
births, exposure ledger, checkpoints, believability, vital signs,
decay, momentum) over ~18 months of history (window pinned at build
time; nominally Feb 2025 → Aug 2026), inside a sealed environment,
producing a foundation the live system currently lacks: multi-quarter
narrative arcs, a populated truthfulness ledger, momentum baselines
across market conditions, and a full-cycle exercise of decay.

IS NOT: a track record. No output of this exercise may ever be
presented, on any surface or in any conversation, as "the instrument
called X early." The live narrative record begins 2026-07-05 and that
remains the only lived history. Replay outputs are era-stamped
`replayed` forever (v2d-style era discipline). This is a foundation
and a laboratory, not a résumé.

ALSO NOT (v1): a board/score backtest. The narrative system replays
cleanly from documents + prices; the full scoring stack drags in
feeds we hold only as current state (analyst counts, overrides, deep
dives) and a survivorship-shaped universe. A board replay is a
separate, later decision with its own design; folding it in now would
quietly poison the clean part with the dirty part.

## 2. The isolation principle — state, not code (assessment of
## "outside our actual system")

Edmund's isolation requirement is adopted in full, with one precision
that changes the architecture: the boundary is drawn at the STATE
layer, not the code layer.

- If the replay runs a FORK of the pipeline, the exercise validates
  the fork. Every divergence — accidental or "minor" — makes the
  backtest a test of something other than the instrument, and the
  later integration assessment worthless.
- Therefore: SAME CODE, pinned at one git commit (recorded in the
  replay's manifest), executed against a SEALED DATABASE. The entire
  pipeline acquires state through DATABASE_URL; a replay driver
  process that sets DATABASE_URL to the sealed instance runs the real
  functions with zero reach into production. Prod credentials are not
  present in the replay environment at all — isolation by absence,
  not by discipline.
- The sealed instance is a physically separate Postgres (local or a
  scratch instance), schema-seeded from prod's DDL (pg_dump --schema-
  only), data-seeded per §3. Nothing in prod ever reads from or
  writes to it. Promotion of any replay output into the live universe
  is a MANUAL, later, per-output decision (§8) — never a pipe.

## 3. Time-gating — progressive reveal (the core design decision)

Two ways to keep the future out of a judgment:
(a) bound every query to <= sim_date — audit-heavy, fails open (one
    missed bound leaks silently);
(b) PROGRESSIVE REVEAL — the sealed DB starts EMPTY of events and the
    driver inserts each day's documents/prices at the start of that
    simulated day. The future physically does not exist in the
    database. Fails closed by construction; no query audit needed.
This design mandates (b). It is the direct implementation of Edmund's
"it needs to do everything in sequence."

Mechanics:
- A STAGING corpus (read-only, outside the sealed DB) holds the full
  window: raw documents (filings incl. 8-Ks, transcripts), v2 grades
  (the #15 side table filing_themes_v2 — the replay CONSUMES the
  cutover's backfill; one payment, two uses), daily prices,
  fundamentals as-reported with their filing dates.
- The driver's day-loop, per simulated trading day T:
    1. REVEAL: insert staging rows with event_date == T into the
       sealed DB, stamping created_at = T's date-time (see timestamp
       rule below).
    2. RUN the day-cycle: the same step functions the live scheduler
       runs, in the same order (theme/claims already present via v2
       feed; exposure judging on T's events; birth queue two-vote;
       checkpoint minting; qual-narrative steps that belong to the
       narrative system).
    3. On simulated Fridays: the weekly set (silence decay LIVE mode,
       vital signs, believability resolution).
- TIMESTAMP RULE (a named hazard, solved at the loader): several live
  windows are relative ("last 14 days of 8-K analyses", decay's
  last_confirmed, checkpoint deadlines). Under progressive reveal,
  created_at must carry SIMULATED time, not wall time, wherever any
  consumer windows on it. The loader stamps domain-consistent
  timestamps; the build enumerates every created_at/NOW() consumer in
  the replayed steps (there is a known list to start from: qual
  trigger windows, decay's 21h/weekly bounds, checkpoint deadline
  validation, vital-signs week bucketing) and proves each one reads
  simulated time correctly. NOW()-in-SQL call sites in replayed steps
  are refactored to accept an as_of parameter (the V3 #16 pattern —
  this is the "slight adjustments" Edmund anticipated, and each such
  refactor is ALSO a live-code improvement, reviewed as such).
- LEAK CANARIES (constructive proof, run before the real replay): the
  staging corpus is salted with (i) a future-dated synthetic document
  containing a distinctive marker fact and (ii) a real document
  duplicated with a shifted date. Acceptance: at any sampled sim-day,
  neither the marker fact nor the shifted duplicate is visible in the
  sealed DB, in any judge context assembled, or in any output. A
  replay whose canaries fail is discarded wholesale.

## 4. The judge-knowledge leak — named, measured, bounded (the one
## gate that cannot be fully closed)

Data can be sealed; the model's training cannot. Every judgment runs
on a model that has read the replay window's newspapers up to its
training snapshot. Facts, stated plainly:
- The live extractor/judge models are pinned snapshots (e.g. the
  extraction model's snapshot is 2025-10-01). For the nominal window
  (Feb 2025 → Aug 2026), everything AFTER the model snapshot (~10 of
  18 months) is genuinely unknown to the model — near-clean. The
  earliest months fall inside its knowledge — contaminated in
  principle.
- MITIGATIONS (defense in depth, none total):
  1. The v2 anchored rubric is the main defense: evidence-cited
     judgment mechanically narrows the room for priors ("cite the
     number in the document or you cannot award the band"). The same
     validation rules apply in replay (unevidenced output = invalid).
  2. Judge prompts in replay carry the simulated date and the same
     context the live judge gets — never "this is a backtest of the
     past" framing that invites retrospection.
  3. REPORTING SPLIT: every replay result is reported in two
     segments — pre-model-snapshot (contaminated-in-principle) and
     post-model-snapshot (near-clean) — and never blended without
     both numbers shown.
  4. Optional sensitivity probe (cheap): re-run one mid-window month
     with a second model; the divergence measures judge-variance and
     gives a scale for how much judgment (vs document content) drives
     the ledger.
- CONSEQUENCE (binding): even the near-clean segment supports
  foundation claims ("the machinery, fed 2026 documents in sequence,
  builds arcs like these"), not prescience claims. §1's IS-NOT rule
  is absolute regardless of segment.

## 5. Fidelity inventory — what the replay eats, and gaps to close
## first (checked against prod 2026-08-21)

- Documents: filings back to 2016 (21,994 incl. 8-Ks); graded themes
  10,541. The 18-month v2 side table (9,094 docs) is the feed — the
  replay REQUIRES the #15 cutover's backfill to exist first.
  Sequencing: after #15 Phase 3 (side table built), the replay can
  start even before live cutover, since it reads the side table.
- 8-K event analyses: live narrative steps consume llm_analysis on
  8-Ks. INVENTORY GATE at build time: count window 8-Ks lacking
  llm_analysis; analyzing them (events pipeline, same code) is a
  priced line-item in the quote.
- Prices: daily closes for the window (yfinance/vendor history) —
  needed for the qual-narrative steps that read reactions; revealed
  day by day like documents. NO forward prices ever staged beyond the
  reveal frontier (progressive reveal covers prices identically).
- Fundamentals: fundamentals_annual/history as-reported with filing
  dates — revealed on filing date, not fiscal date.
- Universe: pinned to a stated list with its survivorship bias NAMED
  in the manifest (today's ~828 tickers, minus IPOs after each
  sim-date via first-trading-date check). Foundation-acceptable;
  performance-fatal — restated in §1.
- The narrative system's OWN parameters (thresholds, caps, judge
  prompts) are today's — the replay tests TODAY'S instrument on
  yesterday's inflow. Fine for foundation; named for the reviewer.

## 6. What the replay produces (the assessment package)

At completion, a report — the ONLY artifact that crosses back to
Edmund before any integration talk:
1. Library genesis: what stories were born, when, from what evidence;
   final library vs the live July-born library (a CONVERGENCE TEST:
   two different starting points arriving at similar libraries is
   evidence of robustness; divergence is a finding about
   path-dependence, not automatically a defect).
2. Believability: per-company claim ledgers with resolutions across
   4-6 quarters — the truthfulness protection, populated. (Claims +
   resolution are the hindsight-safest layer: verbatim at the time,
   graded by what the next quarter filed.)
3. Checkpoint discipline: minted promises, hit/miss rates by sector
   and by management, deadline realism.
4. Momentum: weekly support/erosion series across 18 months incl. at
   least one full earnings cycle per company — the calibration
   input the September ritual currently lacks (6 weeks of live data).
5. Decay: strike/reconfirm dynamics over multiple report cycles —
   does the 0.25 similarity bar and 2-strike step-down behave over a
   full year? (Today: one shadow fortnight.)
6. Case studies: 8-10 names with known arcs (SMCI's whiplash, EL's
   decline, ENS, ACM's charge) — did the sequence-fed machinery
   develop, amend, and decay exposures sensibly? Each case carries
   its segment label (§4.3).
7. The honesty annexes: canary results, model manifest (IDs,
   snapshots, git commit), cost ledger, failure list, both reporting
   segments.

## 7. Refinement discipline (assessment of "clear back testing and
## refinement afterwards")

The benefit is real and it carries the classic trap: refine the
system against the replay, re-run, admire the improvement — and you
have curve-fit the instrument to one historical window. Binding
protocol:
- SPLIT: the window is divided ONCE, in advance (e.g. Feb-Dec 2025
  refinement segment / Jan-Aug 2026 validation segment). Proposals
  may be motivated by the refinement segment only; the validation
  segment is touched ONCE per proposal for a yes/no read.
- Any refinement adopted from replay evidence still walks the live
  freeze ritual END-TO-END (shadow, diff, sign-off) — the replay
  shortens the argument, never the ritual.
- Process defects found in replay (crashes, mis-wired windows, the
  timestamp class) are fixed freely — they are bugs, not tuning.

## 8. Integration strategy — deliberately later, shape sketched now
Nothing integrates until Edmund has the §6 report and rules. The
menu, in ascending order of caution:
- Tier 1 (light review): believability/claims ledgers → live tables,
  era-stamped; the extractor's per-company caution starts working.
- Tier 2 (ritual inputs): momentum baselines and decay statistics →
  the September calibration as INPUT DATA (clearly labeled), not as
  pre-made parameters.
- Tier 3 (Edmund-only, default NO): any replayed narrative arcs
  entering the live library or any surface. If ever shown, shown as
  a separate "replayed era" — never merged with lived history.

## 9. Cost, scale, and gates (structure now; numbers at the gates)
- Phase R0 INVENTORY (cheap, read-only): counts — events in window,
  8-Ks needing analyses, judge-calls per day-cycle formula → FIRM
  QUOTE. Ballpark honesty: extraction is already paid by #15; the
  judged layers (exposure ops, births, minting, weekly passes ×
  ~390 sim-days) are tens of thousands of calls — low hundreds of
  dollars at extraction-class models, four figures if judge steps
  run larger models. The quote decides; nothing runs without
  Edmund's approval of the number (the V3 #1 rule).
- Phase R1 HARNESS: sealed DB, loader, day-loop driver, timestamp
  audit, canaries. Acceptance: a ONE-WEEK pilot replay (5 sim-days)
  passes canaries and produces sane ledgers end-to-end.
- Phase R2 PILOT MONTH: one calendar month replayed; Edmund reviews
  a mini §6 report before the full spend (gate).
- Phase R3 FULL RUN: chunked, resumable, cost-metered; manifest
  recorded.
- Phase R4 ASSESSMENT REPORT (§6) → Edmund → integration ruling.

## 10. Sequencing against the live roadmap
- Hard prerequisite: V3 #15 Phase 3 (v2 side table). Natural slot:
  harness build (R1) can start immediately after the cutover
  session's backfill; the full run should not collide with the
  September calibration's attention — either R2 pilot feeds the
  calibration (if timing allows) or the calibration proceeds on live
  data and is later DEEPENED by replay statistics (Tier 2). Both
  orderings are legitimate; Edmund picks at R2.
- The believability WIRING for live (claims resolution in
  after-close, V3 #15 companion) proceeds regardless — the replay
  populates history; the live wiring keeps it current.

## 11. Risks (named, with owners)
- Judge knowledge (§4): bounded, split-reported, never fully closed.
- Code drift: replay pinned to a commit; live keeps moving — the
  manifest records the delta at assessment time.
- Timestamp semantics: the single most likely implementation bug
  class (§3); mitigated by the enumerated-consumer audit + canaries
  + pilot gates.
- Cost overrun: per-phase quotes, metering, chunked execution.
- Interpretation creep: the strongest risk is human — replay arcs
  LOOK like a track record. The era stamp, the IS-NOT clause, and
  Tier 3's default-NO exist for this. Any surfacing decision is
  Edmund's alone.
- Wall-clock: a full run at throttled concurrency is days-to-weeks;
  resumability is mandatory (the incident-proven pattern).

## Questions for the external reviewer
1. Is the state-not-code isolation boundary the right cut, or do you
   see a case for a forked codebase despite the fidelity cost?
2. Progressive reveal vs query-bounding: any leak channel you can
   construct that survives reveal + canaries + simulated-time
   stamping?
3. Is the pre/post-model-snapshot reporting split sufficient
   treatment of judge knowledge, or should the contaminated segment
   be dropped entirely?
4. The refinement split (§7): is one fixed split adequate, or should
   we require k-fold style rotation given a single 18-month window?
5. Survivorship: acceptable as named-and-bounded for a foundation
   exercise, or does it demand delisted-name inclusion even at v1?
6. Anything in §8's integration tiers that should be stricter?
