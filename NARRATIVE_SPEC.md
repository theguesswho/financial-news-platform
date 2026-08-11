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
- [ ] **Phase 2 — momentum in shadow.** States computed from vital
      signs, cross-sectional calibration, corroboration bar M set.
      Deliverable: distribution + flap-rate report AND — because
      momentum weights exposures in E (see How-it-works: accel=1.0,
      stable=0.6) — a full OFFLINE BOARD DIFF showing every tier change
      honest momentum would cause. Cutover is a scoring change: freeze
      discipline in full (user sign-off, V2_CONSIDERATIONS, platform
      note with active window). Product landing page keeps ledger-op
      coloring until then.
- [ ] **Phase 3 — post-birth prediction minting.** Claims → checkpoints
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

## Progress

- Phase 0 complete (2026-08-12): definitions + acceptance criteria
  user-confirmed and locked. Nothing built yet.
- NEXT: Phase 1 — narrative_health_history table, weekly vital-signs
  pass, backfill from exposure_history to 2026-07-06 (seeding rows
  flagged, excluded from calibration). Observational only: touches no
  judgment, no scoring, no live narrative fields. Deliverable to user:
  the metas' weekly trajectory (a 2026-08-12 offline prototype already
  produced this from the ledger — reproduce it from the new table as
  verification). Deploy gate + batching rules apply as everywhere.
