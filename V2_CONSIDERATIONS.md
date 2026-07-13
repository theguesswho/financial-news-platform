# V2 Considerations

Deferred scoring/system changes. The v1 methodology is FROZEN (2026-07-07) so the
track record stays untampered — nothing here ships until a deliberate v2 revision,
informed by the accumulated record. Log every candidate here with date, origin,
and rationale. Do not implement piecemeal.

## Scoring

### 1. Qual-assessor component re-scoring (2026-07-12, user)
The qual assessor may correct component scores it can show are distorted — e.g.
Jacobs (J) scored value 1.00 off a PEG of 0.40 whose growth denominator was
inflated by the 2024 Amentum spin-off. Design: assessor outputs
`<component>_adjusted` + mandatory cited reason; store raw AND adjusted (same
pattern as tier/assessed_tier); UI marks adjusted values; adjustment bounded
(±0.4) so a bad rationale can't zero a stock. Overrides become an auditable
dataset evaluable against outcomes.

### 2. Event-distortion guard on growth inputs (2026-07-12, from the J case)
PEG/growth inputs have no defense against spin-offs, mergers, or one-off comps.
Cross-check growth vs fundamentals_history for discontinuities; haircut or flag
PEG when YoY comps are dirty. Complements #1 (quant-side prevention vs
qual-side correction).

### 3. Narrative-as-the-gap unification (2026-07-08, user)
Narrative should not be its own multiplier; the signal is the GAP between
genuine narrative exposure and what the market has priced. Fold n and the
mispricing terms into one component: exposure × (1 − priced-in), where
priced-in derives from narrative-peer premium + price action. A strong
narrative fully priced ≈ 0; a moderate narrative nobody has priced = high.

### 4. Consensus / "hiddenness" discount (2026-07-08, review finding)
The system has no concept of "the market is already looking here". Candidate
inputs we already store: analyst count, price vs 52w high, market cap
percentile, narrative-peer premium. Would demote crowded mega-caps without
banning them.

### 5. Narrative gate saturation (2026-07-08, review finding)
n^1.5 rewards 0.93 exposure ~1.85× more than 0.62. Above ~0.75, more exposure
is not more edge. Saturate the gate's top end.

## Infrastructure / hygiene

### 6. Tier thresholds single source of truth (2026-07-07)
0.60/0.52/0.47 currently duplicated in leaderboard_archiver + two UI pages
(drift caused the 134-vs-44 board bug). Move to one shared constant.

### 7. MDY attribution view (2026-07-12, user decided SPY-only)
SPY remains THE benchmark. Optional secondary view pairing mid-cap lots vs MDY
for skill attribution. Plumbing exists, inactive (BENCHMARKS tuple).

### 8. Track-record growth chart (2026-07-11)
Portfolio-vs-SPY line over time + per-lot detail became worth charting once a
few months of divergence exist.

### 9. Qual assessor model diversity (2026-07-12, objectivity review)
Claude extracts themes, writes narratives, judges exposure, AND qual-assesses —
one model's worldview to the fourth power; errors correlate. Consider a
different model family (or adversarial prompt) for the qual layer as devil's
advocate.

### 10. Exposure re-scoring cadence (2026-07-11)
Exposures refresh weekly; a transformative 8-K (major acquisition, segment
sale) should trigger same-day re-judgement of that stock's exposures.
