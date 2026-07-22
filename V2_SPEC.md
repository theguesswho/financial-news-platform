# V2 Scoring Specification — DRAFT for review (2026-07-22)

Status: **paper draft — nothing implemented**. Iterated with the user against
offline board comparisons until the ranking matches the stated objective, then
implemented in one deliberate cut (v1 archived, fresh track-record table).

## The objective, restated precisely (the Dell test)

Find companies where you buy a decent boring business at a decent boring price
and the narrative exposure comes FREE. Three necessary conditions:
1. **Standalone cheap** — inexpensive on ex-growth multiples for what it
   already is, ignoring the story entirely.
2. **Real exposure** — genuine, filings-evidenced leverage to a live narrative.
3. **Unpriced** — the market is demonstrably NOT paying for that exposure yet.

v1's diagnosed failures (assessment 2026-07-22): narrative conviction
outweighed unpricedness 2.4x to 1.4x; value double-counted the narrative via
consensus-growth PEG (50% of blend); nothing measured hiddenness. Consensus
AI mega-caps at 80–90% of 52w highs topped a "hidden" gem list.

## Components

### Q — Quality (unchanged from v1)
0.70 x margin/ROIC trajectory + 0.30 x absolute rank. It works; keep it.

### V_s — Standalone value (replaces v1 value)
Percentile rank within margin-peer bucket (v1's peer machinery, reused) of
inverted **ex-growth** multiples:
    V_s = 0.45 x fwdPE_pctl + 0.35 x EV/EBITDA_pctl + 0.20 x P/FCF_pctl
**No PEG anywhere in the blend** — growth-adjusted cheapness is consensus
belief wearing a value costume. PEG (vendor, 5-yr expected) survives only as
a DISPLAY stat and a qual-assessor input.

### E — Narrative exposure (REDESIGNED: signed, linkage-weighted, three-tier)
v1's E measured entanglement, not benefit. Canonical failure (2026-07-22):
CPB scored E=0.58 with its DOMINANT driver being the GLP-1 "Weight Loss Drug
Cascade Economy" narrative — a THREAT it is defensively adapting to, scored
as if it were upside. RNR scored 0.40 on the AI buildout because its bond
portfolio earns investment income — a second-order link.

Three changes to the exposure judgement (fields added to the existing LLM
call; evidence is already cited):
1. **Direction** — each exposure is judged `beneficiary` /
   `adapting-under-threat` / `threatened`. E counts beneficiary exposure at
   full weight, adaptation at 0.25x (successful pivots are real but
   unproven), threatened at ZERO (arguably negative in a later revision).
2. **Linkage strength** — how DIRECT is the transmission from narrative to
   this company's P&L? `direct` (sells the picks and shovels) 1.0x /
   `secondary` (supplies the sellers, prices the risk) 0.6x /
   `incidental` (owns assets that drift with it) 0.2x.
3. **Company/sub-sector narrative tier** — promote the lifecycle engine's
   candidate narratives (e.g. CPB's self-discovered "CPG Portfolio Health
   Reformulation") and the narrative_overrides dataset into a first-class
   company-level tier, so a Broadridge's proven company story lifts E
   natively rather than through the override patch. Seeding source: the
   override evidence ledger + candidate-tier narratives with single-company
   evidence concentration.

Expected effect (validated against 2026-07-22 exposures): CPB's E falls to
~0.3–0.4 (reformulation stories at adaptation weight) and it exits the top
30; LDOS/PTC/HII/FDS unchanged (genuine beneficiary, direct linkage).
The call-vs-filing gap component of E carries over unchanged.

### P — Priced-in (NEW: the inverse of hidden)
How much of the story the market already pays for (weights user-approved
2026-07-22 after board iteration):
    P = 0.40 x (1 − gap)            # v1 gap: price-lag 50/mispricing 30/momentum 20
      + 0.30 x pct_of_52w_high      # at the high = repricing already happened
      + 0.30 x analyst_pctl         # coverage crowding
NO market-cap term (user decision: size-agnostic — the sin is being priced,
not being big; Dell was ~$70B when its story was free. Attention is measured
directly by analyst crowding + price action, not proxied by size).
Validated effect: at-the-high insurers (RNR/EG/GL/RGA, 96–98% of 52w highs)
fall out of the top 50; CRM/HCA/ADBE rank on pricedness merits.

### NG — The narrative gap (THE core term)
    NG = E x (1 − P)
A 0.9 exposure that is 0.9 priced-in scores 0.09 — near-nothing, by design.
A 0.6 exposure nobody has priced (P=0.2) scores 0.48 — the Dell shape.

### Velocity guard (from V2 #14)
If narrative velocity is negative (call trajectory "decelerating" on
consecutive readings, or exposure delta down on re-judgement), (1 − P) is
capped at 0.5 — a widening gap during a de-rating is a value trap, not
an opportunity. (Implementation phase; not in the offline draft.)

## Composition

    gem_v2 = sqrt(V_s x Q) x NG^0.75

- sqrt(V_s x Q): same balanced core as v1 — the "decent business, decent
  price" half of the trade.
- NG^0.75: the option half. Exponent < 1 because NG already spans a wide
  range once (1 − P) multiplies in; 1.5-style steepening would re-create
  v1's winner-take-all narrative dominance in reverse.
- Fundamental-momentum penalties (rev & earnings both declining x0.5 etc.):
  kept unchanged.

## Tiers
Re-derived from the v2 score distribution after calibration (v1 cutoffs are
meaningless on a new scale). Target board size stays ~35–50 of ~600.

## Qual assessor realignment (REQUIRED at implementation — user 2026-07-22)
The assessor is a fundamental organ of v2 (override right retained), but its
prompt currently teaches v1 physics. Full rewrite of ASSESSMENT_PROMPT and
the override prompt:
1. **Component legend rewritten for v2**: V_s (standalone ex-growth value —
   "cheap for what it already is; the narrative must be free"), signed E
   (beneficiary-only exposure; adaptation is not upside), P ("how much the
   market already pays — high P near-disqualifies regardless of story
   strength"), NG = E x (1 − P) as THE core signal.
2. **The Dell test as the explicit evaluation frame**: "would you be paying
   for the narrative, or getting it free on top of a fairly-priced boring
   business?" Every upgrade rationale must answer this.
3. **Skepticism duties updated**: interrogate direction/linkage of the top
   exposures (is 'beneficiary/direct' credible from the evidence?); treat
   at-the-high + high-P as near-disqualifying; PEG demoted to a sanity
   stat (vendor 5-yr, with fallback provenance noted).
4. **Override right recalibrated to v2 scale**: the +0.40 narrative boost
   becomes a bounded E-boost for unmapped company narratives (same evidence
   bar, same audit trail, narrative_overrides continues as the dataset);
   v2 tier cutoffs (recalibrated) replace 0.60/0.52/0.47 in the prompt.
5. **Tone-baseline, multi-tier-jump, and anti-speculation rules carry over
   unchanged** — they were hard-won and are formula-independent.

## Transition plan (user-approved direction 2026-07-22)
1. Iterate THIS spec against offline board comparisons until approved.
2. Implement in scorer; recalibrate tiers; update UI component displays.
3. Archive v1 track lots as a closed era (never deleted); start a fresh
   heads-up table (same honesty rules: recorded snapshots, same-day SPY
   twins, buy-and-hold).
4. V1 formula preserved in git history + this repo's docs for the record.
