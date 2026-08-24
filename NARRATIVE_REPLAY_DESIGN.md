# The Sealed Replay — narrative system walk-forward, design for review

> **Amendments 2026-08-22 (external review):** claims feed corrected
> (v2 table is grades, not claims; live entrypoints named; NO live
> claims resolver exists — stated in §5); 8-K era-mix rule decided
> (§5); R0 recast as a NOW()/as_of consumer sweep (§9); four leak
> channels added (§4b); refinement split pinned to the model-snapshot
> boundary (§7); weekend reveal rule (§3); §8 tightened (Tier 3 never
> customer-facing); sequencing vs the cutover sittings (§10).


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
    2. RUN the day-cycle — the EXACT live entrypoints, nothing else
       (amended 2026-08-22; grep-verified names):
         · claim_extractor.run_claim_extraction (claims are NOT in
           the v2 grades table — extracted fresh in-sequence; spans
           must be VERBATIM from the document, never paraphrases)
         · exposure_ledger.run_update_pass
         · company_narrative.process_birth_queue
         · checkpoint_minting.run_minting
       OUT, explicitly: hidden_gem_scorer, board_membership,
       qual_assessor, overrides, deep dives, Streamlit, any
       board/score path.
    3. On simulated Fridays: narrative_decay.run_decay_pass (live
       mode) + narrative_vital_signs.run_vital_signs + claims
       resolution (see §5 — the resolver must be BUILT).
    WEEKEND/HOLIDAY RULE (amended 2026-08-22): an event dated on a
    non-session day reveals at the OPEN of the next simulated
    session — matching how the live after-close first sees weekend
    filings. No other calendar rule applies.
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

### 4b. Leak channels that survive reveal + canaries (added
### 2026-08-22, external review)
- PRICES: stage the AS-PRINTED close of the day, not today's
  split/dividend-adjusted series — an adjusted series encodes future
  corporate actions into past prices.
- FUNDAMENTALS: as-FILED figures revealed on their filing date —
  never the vendor's restated history (restatements are future
  knowledge wearing old dates).
- MODEL WEIGHTS: §4 above — bounded, never closed.
- JUDGE SYNTHESIS: birth and exposure judges leak more than the v2
  extractor — they synthesize rather than cite. Consequence: the
  PRE-snapshot segment may never justify a live parameter change on
  its own; only the post-snapshot segment plus the §7 protocol can.
- HOST ISOLATION: the replay host carries NO prod DATABASE_URL and
  NO Railway token — isolation by ABSENCE. An env var pointing at a
  sealed DB on a laptop that also holds prod credentials is not
  isolation; the replay runs under a credential-stripped environment
  (separate shell env/user) verified before R1 acceptance.

## 5. Fidelity inventory — what the replay eats, and gaps to close
## first (checked against prod 2026-08-21)

- Documents: filings back to 2016 (21,994 incl. 8-Ks); graded themes
  10,541. The 18-month v2 side table (9,094 docs) is the GRADES feed —
  the replay REQUIRES the #15 cutover's backfill to exist first.
  Sequencing: after #15 Phase 3 (side table built), the replay can
  start even before live cutover, since it reads the side table.
- CLAIMS (corrected 2026-08-22): filing_themes_v2 holds grades, NOT
  claims. Claims come from claim_extractor.run_claim_extraction run
  in-sequence inside the sealed env, and any claim later promoted
  under Tier 1 must be a VERBATIM span from the filing — a 2026
  paraphrase of a 2025 promise is not evidence.
- CLAIMS RESOLVER (stated plainly, grep-verified): NO live resolver
  exists — earnings_claims is read by minting and vital signs, but
  nothing resolves claims into narrative_believability; that is WHY
  the table is empty. The replay's believability product therefore
  REQUIRES building the resolver, in the sealed env, to the
  NARRATIVE_SPEC definition (claims mature at the next report →
  confirmed/missed → per-company claim_accuracy), with NO live
  writes. Its later adoption live is part of the Tier 1 ruling, and
  it goes through normal review as new machinery.
- 8-K ERA MIX (decided 2026-08-22): live 8-K llm_analysis is still
  the v1 adjective scale (11:1 positive); letting those vote would
  birth stories off rosy 8-Ks and poison the clean feed. DECISION:
  re-anchor the window's 8-Ks under design section D (anchored
  impact bands) as a PRICED line in the R0 quote — 8-K evidence
  stays in the replay (fidelity to live behavior) on the honest
  scale. The alternative (stamp v1, excluded from votes) was
  rejected: it removes an entire evidence class the live system
  uses, making the replay structurally unlike the instrument.
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
- SPLIT (pinned 2026-08-22 to the model-snapshot boundary): the
  refinement segment is the PRE-snapshot (contaminated-in-principle)
  half; the validation segment is the POST-snapshot (near-clean)
  half. We knowingly tune on the dirty half and check ONCE per
  proposal on the clean half — stated in those words so nobody
  mistakes the arrangement for more than it is. ONE split, fixed in
  advance; no k-fold rotation on a single 18-month window.
- Any refinement adopted from replay evidence still walks the live
  freeze ritual END-TO-END (shadow, diff, sign-off) — the replay
  shortens the argument, never the ritual.
- Process defects found in replay (crashes, mis-wired windows, the
  timestamp class) are fixed freely — they are bugs, not tuning.

## 8. Integration strategy — deliberately later, shape sketched now
Nothing integrates until Edmund has the §6 report and rules. The
menu, in ascending order of caution:
- Tier 1: believability/claims ledgers → live tables, era-stamped —
  ONLY after (a) every promoted claim is a verbatim span from its
  filing and (b) Edmund's ruling on the §6 report. The extractor's
  per-company caution starts working only then.
- Tier 2: momentum baselines and decay statistics → the September
  calibration as LABELED INPUT DATA only — never pre-made
  parameters; the calibration ritual computes its own numbers with
  replay statistics beside them.
- Tier 3 (default NO, tightened 2026-08-22): replayed narrative
  arcs NEVER appear on any customer-facing surface — including a
  labeled "replayed era" page. Internal / Edmund-only, full stop.
  Entering the live library remains a separate Edmund-only ruling
  that this design does not presume.

## 9. Cost, scale, and gates (structure now; numbers at the gates)
- Phase R0 — CONSUMER SWEEP + INVENTORY (recast 2026-08-22, same
  shape as #15 Phase 0; cheap, read-only):
  · Enumerate EVERY NOW()/CURRENT_TIMESTAMP/date.today() in the IN
    entrypoints (known starters: exposure_ledger's last_confirmed
    handling, company_narrative's 7/30-day and 18-month windows,
    decay's 75-day and weekly bounds, vital signs' computed_at and
    week bucketing, minting's deadline validation). Each must take
    as_of; the live default remains now(); PROVE the live scheduler
    path is byte-identical after the refactor. A missed NOW() is
    the likeliest SILENT bug — canaries can pass while decay simply
    never fires; the sweep is the defense, not the canaries.
  · Count window 8-Ks lacking llm_analysis + the design-D re-anchor
    line (per §5's era-mix decision).
  · Judge-calls-per-day-cycle formula → FIRM QUOTE. Ballpark
    honesty: extraction is paid by #15; the judged layers (exposure
    ops, births, minting, weekly passes × ~390 sim-days) are tens
    of thousands of calls — low hundreds of dollars at
    extraction-class models, four figures if judge steps run larger
    models. Nothing runs without Edmund's approval of the number
    (the V3 #1 rule).
- Phase R1 HARNESS: sealed DB, loader, day-loop driver, timestamp
  audit, canaries. Acceptance: a ONE-WEEK pilot replay (5 sim-days)
  passes canaries and produces sane ledgers end-to-end.
- Phase R2 PILOT MONTH: one calendar month replayed; Edmund reviews
  a mini §6 report before the full spend (gate).
- Phase R3 FULL RUN: chunked, resumable, cost-metered; manifest
  recorded.
- Phase R4 ASSESSMENT REPORT (§6) → Edmund → integration ruling.

## 10. Sequencing against the live roadmap
- Hard prerequisite: V3 #15 Phase 3 (v2 side table) — no full run
  before it exists. The HARNESS may be DESIGNED now (R1 paper work);
  no sealed DB is created and no driver written until after the
  cutover sittings, and nothing about the replay may collide with a
  cutover sitting in progress (amended 2026-08-22). The full run
  must not collide with the September calibration's attention —
  either R2 pilot feeds the calibration (if timing allows) or the
  calibration proceeds on live data and is later DEEPENED by replay
  statistics (Tier 2). Both orderings are legitimate; Edmund picks
  at R2.
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

## Amendment 2026-08-24 — the coverage cliff (post-cutover measurement)
The cutover's Sitting-2 coverage ruling (4,919 of 9,098 window filings
have source text; 4,179 text-less rows stay era-1, NOT re-fetched)
changes this design's feed assumptions. Measured by month (text
coverage of filing_themes rows): Feb-Mar 2025 ~0-2%; Apr 2025-Jan
2026 ~10-41%; Feb 2026 onward 62-77%; Jul-Aug 2026 100%. Two
consequences:
1. The assumed Feb-2025 window START is untenable without a vendor
   re-fetch — no text means no in-sequence claims extraction and no
   v2 grades there (§5's "one payment, two uses" now covers only the
   dense region).
2. The dense region ≈ the NEAR-CLEAN post-model-snapshot segment —
   fortunate for judge-knowledge honesty, but it guts §7's
   tune-on-the-dirty-half split as written (the dirty half barely
   exists as data).
DECISION FOR EDMUND (with an R0 probe + quote before ruling):
  (a) SHORT WINDOW — replay Feb→Aug 2026 (dense, near-clean, cheap).
      Smaller foundation: 1-2 claim-resolution cycles, ~7 months of
      momentum baselines; refinement split becomes a time split
      inside the clean segment (weaker, honest).
  (b) FULL WINDOW — quote a vendor re-fetch of the ~4,179 text-less
      documents (feasibility itself unproven: the vendor may not
      retain old transcripts — R0 must probe a sample before any
      quote). Restores the 18-month ambition and the snapshot split.
      NOTE: Edmund's cutover ruling against re-fetching was scoped to
      the CUTOVER; the replay is a separate purpose needing its own
      ruling either way.
  (c) HYBRID — dense core (Feb→Aug 2026) plus the thin Oct-2025→Jan-
      2026 shoulder as-is, with era-1-graded evidence barred from
      voting on births/exposures (the same rule class as the 8-K
      era-mix decision in §5).
Until Edmund rules, the window in §1 is UNPINNED; R0 gains the
coverage-by-month table and the re-fetch feasibility probe as
standing inventory items.

### R0 probe results (2026-08-25, live, read-only — nothing stored)
Feasibility of backfilling the missing window data, per feed:
- SEC filings (2,075 text-less 10-K/10-Q): every row carries its
  sec.gov URL; probe GETs returned HTTP 200 with full documents
  (2MB+). Re-download is mechanical. (The 1,663 text-less 8-Ks are
  NOT needed — their analyzer layer is 100% complete.)
- Transcripts (2,775 text-less calls): vendor archive probe 4/4 FOUND
  for 2025 calls (DHI, CBOE, NEM, GRMN — 35–56k chars each). The
  vendor retains history. MANDATORY on ingest: internal-date
  verification before storing under any label (V3 #2 / the ACM rule);
  expect 85–95% recovery, not 100%.
- Prices (Feb 3–Apr 4 2025 gap): yfinance serves unadjusted closes
  for the window (probe: 5/5 rows, auto_adjust=False) — the §4b
  as-printed rule is satisfiable.
COST: fetching ≈ $0 (existing vendor subscription + free SEC/yfinance);
v2 grading overlay of ~4,850 recovered docs ≈ $120–200; 8-K design-D
re-anchor ≈ $50–100; replay-side claims for recovered calls ≈ +$60
inside the replay quote. TOTAL NEW LLM SPEND ≈ $250–350.
TIME: elapsed 3–7 days, dominated by vendor rate limits (dripped,
resumable, throttled to protect the nightly pipeline's quota — the
Aug-16 429 lesson); EDGAR ~1–2h; prices <1h; grading overlay ~4–6h.
One build sitting for the fetcher (with date verification), then
unattended.
CONSEQUENCE: option (b) FULL WINDOW is confirmed feasible and cheap —
it restores the 18-month ambition, the §7 refinement split, and the
price gap. The (a)/(b)/(c) ruling remains Edmund's.
