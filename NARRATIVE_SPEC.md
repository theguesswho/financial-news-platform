# NARRATIVE_SPEC — the living narrative system

Drafted 2026-08-12 (methodology session). The third pillar document:
V2_SPEC governs scoring, QUALITY_DURABILITY_SPEC governs data, THIS
governs the narrative layer — the platform's differentiator. Binding on
every narrative-system session. Decisions land here or they don't
exist. Update the Progress section before any session ends.

Session opener (fixed): "Read NARRATIVE_SPEC.md and continue from the
Progress section."

## Why this document exists

2026-08-11 audit findings (the baseline this spec exists to fix):
- 0 of 83 active non-company narratives have ever had a thesis update;
  macro theses frozen since birth 2026-07-05.
- Predictions (checkpoints) are minted only at narrative birth — zero
  new predictions through peak earnings season once the birth queue
  drained (Aug 7).
- Momentum reads "accelerating" on 100% of macros — a label with no
  discriminating signal.
- No table stores narrative strength over time — "is conviction
  growing?" was unanswerable.
- The "starting to see" surface shows the emerging tier (≥28 days old
  by seasoning-gate construction) while genuinely new candidates (10
  born in 14 days) are invisible.
The user's verdict: "the whole point is that it should be living and
breathing." This spec is how it becomes so — correctly, not quickly.

## How the system works TODAY (step-back, user-requested 2026-08-12 —
## the grounding every session must share)

Creation, bottom of the stack upward:
1. **Filings are the source.** 10-K/Q, 8-K, transcripts → theme
   extraction per company, in the company's own words. Everything
   above derives from this stream.
2. **Metas (9) + sectors (10)**: seeded 2026-07-05 in a one-time
   user-approved act from 4 years of clustered filing themes. The
   interpretation layer.
3. **Emerging/candidates (64)**: organic — lifecycle births a
   candidate when a specific story RECURS across multiple companies'
   filings (corroboration was always implicit here); 28-day seasoning
   before promotion.
4. **Company narratives (58)**: judge-born dossiers with predictions +
   delivery-linked maturity. EXCLUDED from live scoring.
5. **Exposures** (separate object): signed evidence-cited edges
   company↔narrative, updated DAILY by the ledger judge. This layer
   already breathes.

Scoring linkage (verified in code, hidden_gem_scorer ~line 219):
E = noisy-OR of a stock's exposures to ALL active non-company
narratives (not just metas), each weighted by direction × linkage ×
NARRATIVE STATUS/MOMENTUM: accelerating=1.00, stable=0.60,
declining=0.20. **Because momentum currently reads "accelerating"
everywhere, every exposure is pinned at full weight — honest momentum
WILL move E scores and therefore the board. Momentum cutover is a
SCORING CHANGE under full freeze discipline (offline board diff,
user sign-off, V2_CONSIDERATIONS, platform note) — not a display fix.**

Evolution mechanism is the SAME at every tier (evidence → corroboration
bar → cited amendment/momentum update); what differs is CADENCE
(company: event-driven; sector/meta: weekly) and STAKES (sector/meta
feed E and the board; company dossiers feed judgment surfaces only).

## Principles (non-negotiable; do not relitigate)

1. **Living, not twitchy.** Layers breathe at deliberate cadences:
   company narratives react event-by-event; sector and meta narratives
   evolve weekly. A meta that flaps daily is noise wearing the costume
   of vigilance.
2. **Corroboration.** One company reporting something new is NEVER a
   narrative event above company scope. Births, amendments, and
   momentum above company scope require similar signals from a MINIMUM
   NUMBER OF DISTINCT COMPANIES in a similar direction. Single-company
   signals feed that company's dossier and count as one vote.
3. **Evidence-cited change.** Every thesis amendment cites the evidence
   rows that drove it and versions the prior text into thesis_history.
   Never silent rewrites. (CLAUDE.md Evidence integrity rules apply in
   full: judgment surfaces see their evidence; the machinery does the
   assessing, never Claude; no data under guessed labels.)
4. **Shadow-first.** Nothing touches live narrative fields until it has
   run in shadow against pre-agreed acceptance criteria (below) and the
   user has seen the evidence and signed off. Scoring-visible changes
   additionally follow freeze discipline (V2_CONSIDERATIONS + platform
   note with active window).
5. **Honest decay.** Weakness, falsification hits, and failed
   predictions get equal machinery and equal display weight to growth.
   A narrative layer that can only strengthen is marketing.
6. **Plain lexicon** on every user-facing surface.

## Definitions (the shared vocabulary — Phase 0 locks these)

- **Support op**: a ledger operation that strengthens a narrative's
  evidence base: `add`, `strengthen`. **Erosion op**: `weaken`,
  `remove`, plus company-scope prediction misses.
- **Breadth (window)**: count of DISTINCT companies contributing ops to
  a narrative (rolled up through its subtree) in the window.
- **Net support rate**: (support − erosion) / active exposures, over a
  window. Windows: 28d primary, 7d turn-detector.
- **Vital signs**: the weekly stored snapshot per narrative (see
  Architecture) — the trajectory the front page charts.
- **Momentum states**: accelerating / stable / decelerating / quiet.
  Assigned CROSS-SECTIONALLY (relative to the library's distribution in
  the period), never by absolute thresholds alone — the ledger's first
  weeks are seeding-dominated and uniformly positive (organic history
  begins ~2026-08-03; earlier weeks are the instrument opening its
  eyes, not the world changing). "Quiet" = ops below minimum N;
  thin evidence must not flap a label.
- **Corroboration bar**: B distinct companies required for a
  narrative-level event (birth or amendment), M distinct symbols for a
  momentum state change. B_meta > B_sector > B_subsector. Values set in
  Phase 2 calibration, recorded here.
- **Translated into earnings**: share of a narrative's exposed
  companies whose most recent earnings evidence DELIVERED on it —
  checkpoint passes and delivered-typed claims, not management talk.
  (Talk raises exposure; delivery raises translation. The two are
  displayed as different things.)

## Architecture

```
exposure_history (ledger)  ─┐
earnings_claims (extractor) ─┤   weekly vital-signs pass
narrative_checkpoints ──────┼─► narrative_health_history ─► momentum states
filing_themes ──────────────┘         (new table)              (shadow → live)
                                          │
                              amendment judge (weekly, batched)
                              — evidence-cited thesis updates,
                                versioned to thesis_history
```

- **narrative_health_history** (new): narrative_id, week, support,
  erosion, breadth, active_exposures, exposed_board_weight,
  checkpoint_passes, checkpoint_fails, translation_share,
  momentum_state (shadow column first). Backfilled from the ledger to
  2026-07-06; seeding-era rows flagged `seeding=true` and excluded
  from calibration.
- **Post-birth prediction minting**: new typed claims (earnings_claims,
  live again since 2026-08-11) mapped to the company's narrative mint
  checkpoints — deduped against open ones, capped per narrative per
  quarter.
- **Amendment judge**: weekly batched pass; input = the narrative's
  current thesis + the window's evidence rows (CONTENT, not counts —
  rule 1 of Evidence integrity); output = amended thesis or explicit
  "no change", with cited evidence ids. Corroboration bar enforced
  BEFORE the judge is called (no evidence, no call — cost control and
  discipline in one).
- **Two-track boundary**: this system lives entirely in the methodology
  track (pipeline + platform tables). The product reads it via api/
  GET /narratives only.

## Existing-machinery inventory (reuse / replace / retire — the
## anti-mismatch map; verified in code 2026-08-12)

**narratives.momentum — writers today:** (1) birth judges stamp the
initial label (newborns say "accelerating" — that's why they're born);
(2) narrative_lifecycle.py:281-295 downgrades on falsification/decline.
NOTHING re-judges periodically — every narrative still wears its birth
certificate, which is the whole "100% accelerating" pathology.
Phase 2 plan: the vital-signs writer becomes the SOLE periodic writer;
lifecycle's falsification downgrade is retained as an override (Phase 5
integrates with it, never duplicates it); birth stamping changes to an
initial state (see Open decision 5). No other writer may remain.

**narratives.momentum — readers (Phase 2 blast radius, ALL must be in
the board diff):** hidden_gem_scorer (E weights 1.0/0.6/0.2 — scoring),
theme_valuation_gap.py:63 (Dell detector FILTERS on accelerating —
scoring-adjacent screen whose universe shrinks under honest momentum),
buyhold_backtest, narrative_structure census, assessor context, report
surfaces, both UIs.

**Thesis text — writers today: none post-birth** (0/83 amended).
Phase 4's amendment judge becomes the sole writer; thesis_history is
the single versioning convention for ALL tiers including company
dossiers — no second convention may appear.

**narrative_checkpoints — writer today:** company_narrative.py:294
(birth only). Phase 3 ADDS the claims-minting path into the same
table with dedupe; grader (checkpoint_grader.py) unchanged.

**Lifecycle (births, seasoning, promotion, decline):**
narrative_lifecycle.py stays the owner. Phase 5 extends its
falsification checks; the corroboration bar B plugs into ITS birth
path. No parallel lifecycle logic anywhere.

**Source of truth for ops:** exposure_history (append-only ledger).
Vital signs are DERIVED from it and recomputable at any time; the
health table is a cache of the ledger, never an independent authority.

## Acceptance criteria (agreed BEFORE building; measured in shadow)

Momentum (Phase 2 cutover gate):
- Spread: no state holds >60% of non-quiet narratives at calibration.
- Stability: <15% of narratives change state more than twice in any
  rolling 28 days.
- Lead: state downgrades precede exposed-weight declines more often
  than they follow them (measured over the shadow period).
Amendments (Phase 4 cutover gate):
- Every amendment lists ≥B distinct-company evidence ids.
- Grounding audit style check: sampled amendments trace to real rows.
- Rate sanity: metas amend at most ~monthly; a meta amending weekly
  fails the living-not-twitchy principle and recalibrates K.

## Phases

- [x] **Phase 0 — definitions sign-off. DONE 2026-08-12.** User
      confirmed: (1) translation = delivery only, never talk;
      (2) momentum relative/cross-sectional with the "quiet" state;
      (3) acceptance tolerances as written (60% spread cap, <15% flap,
      downgrades lead, metas amend ~monthly max). Definitions and
      Acceptance criteria above are LOCKED — amend only with explicit
      user sign-off recorded here.
- [ ] **Phase 1 — vital signs.** narrative_health_history table +
      weekly pass + backfill to 2026-07-06 (seeding rows flagged).
      Observational only; touches no judgment. Deliverable: the metas'
      trajectory table shown to user (prototype 2026-08-12 already
      demonstrated feasibility from ledger history).
- [x] **Phase 1b — silence decay (user-approved 2026-08-11). BUILT IN
      SHADOW 2026-08-11 — live cutover awaits user sign-off (Progress).** When an
      exposed company REPORTS (call + filing ingested) and its
      extracted themes do not reconfirm the narrative, the weekly pass
      emits a deterministic `decay` erosion op on that exposure (no
      LLM — theme extraction already ran); repeated decay without
      reconfirmation lowers exposure via existing ledger machinery
      (last_confirmed / misses). Ships BEFORE Phase 2 so momentum
      calibrates on history that can go down. Definition of
      "reconfirm" (theme match threshold) is an implementation choice
      the build session documents in Progress.
- [ ] **Phase 2 — momentum in shadow.** States computed from vital
      signs, cross-sectional calibration, corroboration bar M set.
      Deliverable: distribution + flap-rate report AND — because
      momentum weights exposures in E (see How-it-works: accel=1.0,
      stable=0.6) — a full OFFLINE BOARD DIFF showing every tier change
      honest momentum would cause. Cutover is a scoring change: freeze
      discipline in full (user sign-off, V2_CONSIDERATIONS, platform
      note with active window). Product landing page keeps ledger-op
      coloring until then.
- [ ] **Phase 3 — post-birth prediction minting. BUILT + DRY-RUN
      VERIFIED 2026-08-11 (see Progress); live writes await user
      sign-off.** Phase 2 waits on ~2-3 organic weeks of
      two-sided vital signs (earliest gate ~late Aug) but Phase 3 has
      no dependency on it — its feed is flowing (earnings_claims:
      38,659 claims, 813 symbols, current through 2026-08-10, backlog
      zero) and company scope is outside live scoring, so no freeze
      ritual. Build now, in parallel with the decay/vital-signs shadow
      clocks. Claims → checkpoints
      on existing company narratives. Deliverable: minting rate + samples
      to user; this is what makes dossiers breathe and unblocks the
      product's Companies page evidence pane.
- [ ] **Phase 4 — amendments.** Company first, then sector/meta weekly
      digest. Corroboration bar B set per tier. Shadow: proposed
      amendments logged but not applied for 2 weeks → user reviews
      samples → cutover. thesis_history versioning live from day one.
- [ ] **Phase 5 — falsification sweeps.** Kill conditions checked
      against fresh evidence weekly; hits force momentum=decelerating
      and open lifecycle review. platform_notes row whenever a sweep
      changes anything assessor-visible.
      **Scope (user-directed 2026-08-11, "we shouldn't be waiting
      around" — this is the practical design, not a gesture):
      INTERIM CHECKPOINT TRACKING.** Every PENDING checkpoint carries
      a living track status, refreshed whenever new evidence for its
      symbol is processed (each quarter's call/8-K/10-Q at minimum):
      - `on_track` — fresh evidence consistent with the promise
      - `slipping` — timeline/magnitude softening but promise intact
      - `in_doubt` — material contrary signal, not yet conclusive
      - `failed_early` — conclusive refutation (guidance withdrawn,
        project cancelled): the checkpoint FAILS now, with cited
        evidence, months before its deadline if needed
      - `no_signal` — the evidence didn't speak to it (feeds decay's
        silence logic, not a judgment)
      Asymmetry is absolute: early FAIL yes, early PASS never —
      confirmation always waits for the filed number.
      MATURITY DISCIPLINE: only VERDICTS (pass / fail / failed_early)
      move maturity. Interim states inform surfaces, the assessor's
      context, and the amendment judge — talk never earns credit
      (translation principle).
      IMPLEMENTATION HOME: extend the Phase 3 mint judge — it already
      receives each dossier's open checkpoints + the new evidence in
      one call; returning track statuses alongside mint proposals
      costs ~zero extra. Schema: track_status, track_updated,
      track_evidence on narrative_checkpoints. Plain lexicon on
      surfaces ("on track", "slipping", "in doubt", "failed early").
      Weekly falsification sweep remains the backstop for kill
      conditions at NARRATIVE level (untenable thesis → momentum
      forced decelerating + lifecycle review + platform note).
- [ ] **Phase 6 — surfaces.** Streamlit lab bench first (vital signs +
      amendment history per narrative); product Narratives page reads
      the same via API (product track builds it per DESIGN_BRIEF).
      "Starting to see" = CANDIDATES with ages; emerging relabeled
      "gaining corroboration".

## Standing — monthly viability audit (starts after Phase 2)

Fixed metrics, reviewed monthly, tripwires pre-agreed:
- Birth rate vs corroboration bar (0 births/month = bar too high or
  discovery broken; >15 non-company births/month = bar too low).
- Momentum distribution (any state >70% of non-quiet = recalibrate).
- Amendment rate per tier vs the rate-sanity bounds.
- Prediction inflow (0 new checkpoints in a month with earnings =
  minting broken) and pass rate.
- Thesis staleness: any ACTIVE meta untouched >90 days gets a forced
  amendment-judge review (which may return "no change" — but cited).
- Flap rate. Library size vs the ~35-40 active non-candidate watch
  threshold (watch-items memory).

## Open decisions (user gates)

1. Definitions above — confirm or amend (Phase 0, blocks everything).
2. Calibration values (X thresholds, N minimum ops, B/M corroboration
   bars) — proposed with evidence at Phase 2/4 gates, not guessed now.
3. Amendment judge model/cost ceiling (weekly batch across ~83
   narratives + ~60 company dossiers; estimate at Phase 4 gate).
4. Whether translation_share (delivered-vs-talk) also feeds the E
   score itself one day — that is a SCORING change, freeze discipline,
   explicitly out of scope for this spec's phases.
5. What momentum state a NEWBORN narrative gets. Proposal: "quiet"
   until breadth clears the corroboration bar M — a newborn has no
   trajectory yet, and birth-stamped "accelerating" is how the current
   pathology started. Counter-consideration: quiet newborns' exposures
   would enter E at the stable weight (0.6), a small headwind for
   fresh discoveries. Decide at Phase 2 gate with the board diff in
   hand.
6. **DECIDED 2026-08-11 — user approved the silence-decay proposal.**
   The locked erosion definition is AMENDED to: `weaken`, `remove`,
   prediction misses, **and `decay`** (silence at earnings). Build as
   **Phase 1b**, before Phase 2 calibration, so momentum calibrates on
   two-sided history. Original finding preserved below.
   **EROSION ASYMMETRY (Phase 1 review finding, 2026-08-11 — BLOCKS
   Phase 2 calibration; needs user sign-off because it amends the
   locked erosion definition).** Evidence: seeding week had 1,732
   erosion ops; the two ORGANIC weeks — peak earnings season, 163
   transcripts/wk — had 8 and 0. The update judge only erodes on
   active negative evidence; SILENCE is not an event. Net support ≈
   support → "decelerating" could structurally never fire except via
   falsification. Momentum on this data is a one-way ratchet.
   PROPOSAL — "silence at earnings is evidence": when an exposed
   company REPORTS (call + filing ingested) and its extracted themes
   do not reconfirm the narrative, the weekly pass emits a `decay`
   erosion op on that exposure (deterministic, no LLM — the theme
   extraction already ran). Repeated decay without reconfirmation
   lowers exposure via the existing ledger machinery
   (last_confirmed / misses columns already exist for this).
   Corroboration-consistent: one company's silence is one vote.
   Alternative considered: time-based decay regardless of reporting —
   rejected as arbitrary (punishes narratives between earnings seasons
   for the calendar, not for evidence).
7. **DECIDED 2026-08-11 — one canonical weight, both old formulas
   retire.** Exactly TWO numbers describe a narrative's footprint:
   - **Breadth** (already in vital signs): distinct companies carrying
     it — the corroboration count.
   - **Board conviction** (canonical, replaces both old formulas):
     Σ over DISTINCT board companies of (tier weight 3/2/1 × the
     company's STRONGEST exposure anywhere in the narrative's subtree).
     Plain-lexicon label: "board conviction riding on this force."
   Consumer map verified before deciding (2026-08-11): formula A only
   in ui/pages/2_Themes.py + api/routers/narratives.py (display), 
   formula B only in narrative_vital_signs.py; NOTHING reads
   exposed_board_weight yet; scoring/assessor/reports untouched by
   either. Implementation (Phase 1b session, with the decay build):
   update the three files, recompute the 846-row backfill under the
   canonical formula so the series is consistent BEFORE Phase 2's
   lead test ever reads it, relabel the web/Streamlit displays.

## Progress

- Phase 0 complete (2026-08-11; the "2026-08-12" stamps elsewhere in
  this file were written the same day and are off by one): definitions
  + acceptance criteria user-confirmed and locked.
- Phase 1 BUILT (2026-08-11, this session) — awaiting user look at the
  deliverable, then it just accumulates weekly:
  - pipeline/narrative_vital_signs.py: narrative_health_history table
    (support, erosion, breadth, active_exposures, exposed_board_weight,
    checkpoint_passes/fails, translation_share, momentum_state shadow
    column left NULL, seeding flag, UNIQUE(narrative_id, week_start)).
    Derived cache of exposure_history — every run upserts, recomputable.
  - Weekly pass wired into scheduler_light.py weekly_deep_refresh as
    step 5h (after lifecycle 5e/structure 5f): recomputes current +
    previous week each run, self-healing. Observational only.
  - Backfill run 2026-08-11 against live DB: 141 narratives × 6 weeks
    (2026-07-06 → 2026-08-10) = 846 rows. Weeks < 2026-08-03 flagged
    seeding=true. Weeks ending before the ledger epoch (2026-07-27)
    carry NULL state columns + zero ops — the ledger cannot say, so the
    table doesn't pretend. Week-of-7/20 state = the pre-ledger system's
    final narrative_exposures state at the conversion instant (exact).
  - Historical state via backward ledger replay (add/strengthen/weaken/
    remove undone from current narrative_exposures; propose_remove and
    remove_vetoed change no state; trigger='shadow' excluded).
    VERIFIED: leaf-narrative support/erosion/breadth match independent
    raw-ledger queries; current-week replay matches live
    narrative_exposures counts exactly (3/3 spot checks each).
  - Phase 1 implementation choices (NOT locked definitions):
    exposed_board_weight = Σ per-symbol MAX subtree exposure over
    board-tier symbols at latest leaderboard snapshot ≤ week end;
    translation "delivered" = symbol-level proxy (confirmed checkpoint
    on the symbol's company narrative, or delivered-graded claim,
    within 100d) until Phase 3 ties delivery to specific narratives.
  - Metas' trajectory deliverable reproduced from the new table: first
    organic week (8/3) shows real spread — support 20–228, breadth
    17–103, erosion ≈ 0 everywhere (nothing eroding yet — watch this),
    translation ≈ 0 (3 confirmed checkpoints platform-wide; honest).
- Phase 1b BUILT IN SHADOW (2026-08-11, this session) — decisions 6 + 7
  implemented; decay awaits user sign-off before going live:
  - **Silence decay (decision 6)**: pipeline/narrative_decay.py. Report
    event = EARN_CALL + 10-Q/K both theme-extracted within 45 days of each
    other. Reconfirm (the implementation choice the spec left open) =
    EITHER a cited judge support op (add/strengthen) for the pair since the
    report, OR max cosine similarity (MiniLM, same model as
    filing_themes.embedding) between the event filings' themes and the
    narrative's name+thesis >= 0.25. Calibrated on live data 2026-08-11:
    judge-cited driven pairs median 0.42 (92% >= 0.25), random non-link
    pairs median 0.25 — conservative by design; exposure moves only on the
    SECOND consecutive silent report (step −0.25, floor 0.10, NEVER
    removes — removal stays the judge's two-vote job).
  - Deviation from the decision-6 text, documented: a dedicated `decays`
    counter column (narrative_exposures) instead of reusing `misses` —
    the update judge treats silence as "confirm" and resets misses=0
    (would erase decay memory weekly), and a shared counter would let one
    propose_remove vote + one silent quarter trigger a removal neither
    path justifies. Reconfirmation resets decays=0 + last_confirmed.
  - SHADOW RUN against live DB 2026-08-11: 559 report events, 1,994
    exposure pairs checked, 710 reconfirmed by judge ops + 1,109 by theme
    match (91%), 76 already judged, **83 decay ops (4.2%)** — all
    trigger='shadow', zero live rows touched, vital-signs erosion for the
    week verified still 0 (shadow excluded). Samples look right (EMR ~
    GLP-1 adjacency sim 0.10, AMGN ~ Agentic AI sim 0.15). Erosion is no
    longer structurally impossible — this is the two-sided history Phase 2
    needs.
  - Wired into scheduler_light weekly step 5h BEFORE vital signs,
    shadow=True hardcoded until sign-off here; isolated try/except so a
    decay failure cannot break vital signs. DEPENDENCY NOTE: decay needs
    sentence-transformers, which is NOT in requirements.txt/Dockerfile —
    the same gap as the weekly "Embeddings refresh" step (5); wherever
    that step succeeds, decay will too. Resolve at live cutover.
  - **Board conviction (decision 7)**: canonical formula (Σ over DISTINCT
    board companies of tier weight 3/2/1 × strongest subtree exposure)
    now in all three consumers — narrative_vital_signs.py
    (exposed_board_weight), api/routers/narratives.py (both endpoints),
    ui/pages/2_Themes.py — both old formulas retired; web landing label
    changed to "board conviction" (JSON key `board_weight` kept stable
    for the product frontend). 846-row backfill RECOMPUTED under the
    canonical formula 2026-08-11 (series consistent before Phase 2's lead
    test): levels ≈2× old (tier weighting added), meta ordering
    preserved; verified API map vs landing agree (39.0). `decay` added to
    EROSION_OPS, the replay, and every ledger-op display filter
    (shadow rows excluded everywhere).
  - GATE TO GO LIVE (user): flip shadow=False in scheduler step 5h after
    reviewing the shadow numbers above (next weekly runs will accumulate
    more). Live decay writes erosion ops + lowers exposures — methodology-
    live but NOT scoring-visible until Phase 2's momentum cutover.
- Phase 3 BUILT, DRY-RUN VERIFIED (2026-08-11, this session) — live
  writes + scheduler wiring await user look at the samples:
  - pipeline/checkpoint_minting.py: per-symbol Sonnet mint judge. Input
    = each active company narrative's thesis + OPEN checkpoints + the
    full text of candidate claims (evidence-integrity rule 1 satisfied);
    output = new checkpoints (claim/observable/deadline) into the SAME
    narrative_checkpoints table the grader already reads — no parallel
    machinery.
  - Candidates: post-birth calls only, confidence ≥ 0.8, timeframe
    present, claim_type ≠ 'risk' (risks are Phase 5 falsification
    material, not credit-earning predictions). Dedupe: new column
    narrative_checkpoints.source_claim_id excludes already-minted
    claims before the judge runs (column added via ensure_schema;
    NULL for all 252 birth-era rows); the judge sees open checkpoints
    and skips restatements. Cap: 2 minted per narrative per calendar
    quarter (birth checkpoints don't count).
  - DRY RUN against live DB 2026-08-11: 41 candidate claims / 6 symbols
    (small because most dossiers were born 8/7 and birth consumed the
    current call — the pass is built for the NEXT earnings wave), 11
    proposals, 0 errors, zero rows written. Samples look substantive
    (ATO rider-tariff $160–165M, CDE FY26 FCF ~$1.5B, HL Greens Creek
    phase-3 timeline). Review flags: one MCK mint self-describes as
    checking an EXISTING open checkpoint (dedupe bar may need
    tightening); one PODD mint is a timeline reaffirmation rather than
    a new number.
  - GATE TO GO LIVE (user): review the 11 samples (rerun
    `python3 -m pipeline.checkpoint_minting` to reprint). On sign-off:
    run with --live, wire into scheduler weekly step (before
    checkpoint grading so mints age properly), record here. Company
    scope — outside live scoring, no freeze ritual needed.
  - REVIEW 2026-08-11 (methodology session; dry run reproduced 11/6/0
    exactly; schema claims verified — status defaults 'pending',
    created_at defaults now(), so grader + quarterly cap both work).
    TWO FIXES REQUIRED BEFORE --live, no re-review needed once done:
    (1) DEDUPE LEAK: 2 of 11 proposals are restatements of open
    checkpoints (PODD admits it in its own rationale; MCK builds on an
    open one) — harden prompt (reaffirmation = skip, never
    "reinforce") AND add a deterministic post-filter (text overlap vs
    open checkpoints) so echo-predictions can't earn maturity twice.
    (2) DEADLINE VALIDATION: parse each proposal deadline; require
    today < deadline < today+3y; skip invalid rows individually (one
    malformed date currently aborts the whole live insert batch).
  - **GATE APPROVED (user, 2026-08-11): "approved with the two fixes."**
    Next session: implement both fixes, run --live, wire into the
    weekly step before checkpoint grading, record results here. While
    in the mint judge, note Phase 5's interim-tracking extension lands
    in this same judge later — design the output shape with that in
    mind (but do NOT build tracking yet; it ships with Phase 5).
- NEXT: user reviews (a) the Phase 1b shadow evidence and signs off
  live decay, (b) the Phase 3 minting samples and signs off live
  minting + scheduler wiring. Then Phase 2 — momentum states
  computed from these vital signs in
  shadow. Cross-sectional calibration needs non-seeding history: ~2-3
  more organic weeks before the distribution is worth calibrating on
  (earliest useful gate ~late August). Interim: let vital signs
  accumulate via the weekly pass; verify step 5h ran in the next weekly
  log. Momentum cutover remains a SCORING change under full freeze
  discipline. Open decision 5 (newborn state) decides at the Phase 2
  gate with the board diff in hand.
