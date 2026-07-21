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

### 11. New-entrant flag must persist all day (2026-07-12, user)
The ★ New Entrant marker on the Hidden Gems page disappears on refresh — it is
computed against the previous snapshot, so once a NEWER intraday snapshot
exists (3 rescores/day), "new" evaporates within hours. User requirement: a
stock that entered the board today keeps its flag for the ENTIRE day (arguably
until the next trading day), so a refresh can't hide it. Fix: derive "new"
from first-appearance date (e.g. earliest board date == today) rather than
snapshot-over-snapshot diff. Note: pure UI/display logic — freeze-safe, could
ship before v2 if wanted.

### 12. Portfolio integration (2026-07-14, user — tackle after mid-cap rollout settles)
Merge the standalone portfolio-tracker (React+Firebase, ~/Desktop/portfolio-tracker —
DO NOT MODIFY) into the platform. Survey done 2026-07-14:
- Data: Firestore project my-portfolio-tracker-7270a (holdings, portfolio,
  realized_gains), seeded from trades.csv — 720 trades since Aug 2022,
  multi-currency incl. LSE/GBX positions. serviceAccountKey.json in folder.
- Port the DATA (one-time copy into portfolio_holdings + new trades table,
  currency-aware; original untouched) and the CONCEPTS (holdings P&L page,
  benchmark comparison via existing twin mechanics, portfolio news — superseded
  by our filings/qual pipeline). Drop React UI, Firebase functions, movers table.
- PARK CashflowForecast (2,100-line retirement planner — different domain).
- Main lift: multi-currency/FX (FMP fx endpoint; same vendor). Non-US tickers
  get price/P&L only (no EDGAR/earnings coverage) — label honestly.
- Brief personalization: holdings-first signals in daily brief. The user's
  Claude scheduled-task "Daily market briefing" stays AS-IS (additive news
  flash, not replaced).
- Then: Home UI redesign last, informed by usage.
- Housekeeping: rotate the FMP key hardcoded in the tracker frontend when it
  eventually retires.

### 13. Score-impact explanations on earnings & narrative events (2026-07-17, user)
Earnings releases and narrative changes are the two highest-priority event
types. When one lands for a tracked stock, the platform should surface not
just the event but WHAT IT DID TO OUR GRADE AND WHY — unprompted. Canonical
example (NFLX Q2 2026): 8-K captured, fundamentals refreshed, score recomputed
— and the correct answer was "unchanged at 0.197: quality 1.00 and gap 0.78,
but narrative 0.39 is the binding constraint; a revenue beat can't move the
gate; watch Sunday's exposure re-judgement of the new transcript."
Design sketch:
- After each earnings 8-K (or narrative lifecycle event) for a tracked stock,
  generate a short "grade impact note": component deltas, the binding
  constraint, and what pending update could still change the grade.
- Surface attached to the event card (Home feed, Events page) and on Stock
  Detail; earnings + narrative events ranked above other event types.
- Pairs with #10 (two-stage narrative reaction) — stage 1's same-day pass
  produces exactly the inputs this note needs.
- Honors the anti-speculation rule: the note derives from actual component
  arithmetic, never LLM guesses about why the score moved.

### 14. Narrative velocity + sign-aware gap (2026-07-19, user — rank alongside #3 at top of scoring group)
Deceleration is as important as identification. The formula's structural blind
spot: during a deceleration-driven de-rating (e.g. a hypothetical AVGO going
60x -> 20x), gap WIDENS, value RISES (peer-cheapness), quality HOLDS (trailing
financials lag the story) — three components improve while the thesis dies,
and the system would relabel a falling knife "Strong Buy". A wide gap has two
opposite causes wearing the same number: neglect (story ahead of price = the
Dell setup) vs de-rating (price ahead of the narrative layer = value trap).
Design:
- Per-stock NARRATIVE VELOCITY from data already collected: exposure deltas
  across re-judgements, consecutive call-trajectory readings ("decelerating"
  twice = scream), guidance revisions from earnings 8-Ks, analyst estimate
  direction.
- Sign-aware gap decomposition: multiplier rewards only story-led widening;
  price-led widening with negative velocity caps at neutral or inverts.
- "Strong but decelerating" as a first-class board flag, surfaced BEFORE
  falsification triggers — not a sell signal (buy-and-hold), but the evidence
  stream that informs the art of selling.
Existing partial defenses and why insufficient: narrative-level momentum
labels (weekly, theme-coarse), falsification checks (death not deceleration),
gap's 20% narrative-momentum component (price_lag 50% dominates in a crash).
Complements #3: level done right + derivative done at all. NFLX's corrected
assessment ("model lag") is the same gap from the opposite direction.

### 15. Management credibility scoring (2026-07-19, user)
Track what management PROMISED on calls vs what the company DELIVERED — own
results only; the share price and market expectations are irrelevant. Raw
material already exists: earnings_claims (~30k extracted forward-looking
claims) was built for this and never closed into a loop (the empty
narrative_believability table is its stillborn placeholder). Design:
- Quarterly verification pass: match claims made 1-4 quarters ago against
  delivered fundamentals + subsequent call statements (Haiku, cheap).
- Per-management ledger: promise-keeping rate, over/under-delivery bias,
  claim specificity. Accumulates like the narrative evidence ledger.
- USE: weights the call-tone signal — confident calls from proven deliverers
  are the Dell signal; from serial overpromisers, noise. Feeds the qual
  assessor as cited input. Complements the 2026-07-19 tone-baseline prompt
  fix (which stops naive tone-flagging) and #14 (velocity).

### 17. SHIPPED-INTERIM 2026-07-21: Qual narrative-override (company-narrative stopgap)
User-approved deliberate amendment (not piecemeal drift): the qual assessor may
raise the narrative input by at most +0.40 for stocks passing the
"narrative-blind" screen (quality>=0.75, gap>=0.60, value>=0.40,
narrative<0.50, off-board) — genuine company-level narratives the 19-narrative
macro/sector library structurally cannot see (canonical case: BR — SEC
digital-default catalyst, tokenization/DLR leadership; gem 0.16 despite
quality 1.00). Upward-only, evidence-mandatory, raw scores stored untouched;
promotions flagged qual_promoted on board + track lots ($1,000 lots per user
decision, measurable separately vs SPY). Every decision (incl. declines) is
stored in narrative_overrides — the labeled dataset for the proper v2
company-narrative layer (#3/#14). Module: pipeline/narrative_override.py.

### 16. Deploy-eats-cron: startup catch-up for missed job slots (2026-07-20)
Twice now (Jul 7, Jul 20) a git push near a cron slot restarted the Railway
service mid-trigger and APScheduler silently skipped the run (no persistence
across restarts). Fix: on scheduler startup, check whether a slot fired
within the last ~30 min without producing its expected artifact (e.g. no
snapshot update since the slot) and run the job once. Freeze-safe ops
hardening; could ship before v2. Interim discipline: avoid pushing within
~10 min of :00 UTC slots (06/13/18/21).
