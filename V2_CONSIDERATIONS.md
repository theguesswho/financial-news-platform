# V2 Considerations

STATUS 2026-07-22: **v2 SHIPPED** (see V2_SPEC.md). The v1 freeze ended with a
deliberate, user-approved cutover: gap-centric scoring (NG = signed E x (1-P)),
standalone value, priced-in hiddenness, velocity guard, qual realignment, fresh
track-record era (v1 lots archived). Items #3, #4, #5, #6, #14 (velocity guard
portion), and #17 (override, recalibrated to v2) shipped in that cut. Remaining
items below stay open for v2.x iterations — same discipline: log first, ship
deliberately.

Historical preamble (v1 freeze, 2026-07-07 – 2026-07-22): deferred
scoring/system changes; nothing shipped piecemeal while the v1 track record ran.

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

### 18. Earnings Radar — calendar-driven anticipation (2026-08-01, user; SCOPED, not built)
EarningsCall.biz's calendar API (subscribed, Starter tier) gives forward
earnings dates for 9,000+ companies. Today the platform is purely REACTIVE
to earnings; the calendar makes it ANTICIPATORY. Scope:
- INGEST: nightly calendar pull for the universe (1-2 API calls/day) into
  an earnings_calendar table (symbol, call datetime, confirmed/estimated).
- SURFACE: (a) "Reporting this week" strip on Home, board stocks first, each
  with score/tier chip; (b) next-earnings date on Stock Detail hero; (c)
  brief section: "3 board stocks report tomorrow: GDDY (5.2, Strong Buy)...".
- PRE-EARNINGS POSTURE (the interesting half): before a board stock reports,
  auto-generate a one-paragraph "what to watch" note from its existing
  assessment + open catalysts/risks — so the post-call verdict has a stated
  prior to be judged against ("we said watch ad-tier bookings; they missed").
  Pairs with continuity framing and management-credibility (#15).
- OPS USE: calendar tells the scheduler WHICH evenings need a fast-transcript
  sweep and primes the dirty-symbol list before the 8-K even lands.
- Cost: negligible (calendar calls + a few Sonnet notes/week).
- Build order when green-lit: ingest -> Home strip + Detail date (display
  only) -> brief section -> pre-earnings posture notes last (new LLM output,
  needs its own prompt discipline).

### 16. Deploy-eats-cron: startup catch-up for missed job slots (2026-07-20)
Twice now (Jul 7, Jul 20) a git push near a cron slot restarted the Railway
service mid-trigger and APScheduler silently skipped the run (no persistence
across restarts). Fix: on scheduler startup, check whether a slot fired
within the last ~30 min without producing its expected artifact (e.g. no
snapshot update since the slot) and run the job once. Freeze-safe ops
hardening; could ship before v2. Interim discipline: avoid pushing within
~10 min of :00 UTC slots (06/13/18/21).

## 2026-08-06 — Divestiture guard on the growth penalty (APPROVED, shipped)
PTC case: sold a division; reported revenue growth -6.8% while cc ARR
ex-divestiture grew +9.1% and guidance was RAISED. The both-negative
growth penalty (x0.5) read the divestiture as deterioration, halved the
score 5.1 -> 2.5, exited the board, and nearly force-sold two lots under
the new position rules. Change: when filings within 12 months disclose a
divestiture/spin-off, the automatic growth penalties stand down; judgment
falls to the qual assessor (summoned by the score-change trigger anyway).
User approved 2026-08-06 ("Yes to both").

## 2026-08-07 — Component floor 0.05 on value/quality (APPROVED, shipped; WATCH)
Peer-bucket percentiles guarantee a bottom stock; the multiplicative gem
turned bottom-percentile value into a hard zero (XOM/AWK/STZ/PLTR case).
Floor 0.05 on both components keeps worst-percentile stocks low, never
annihilated. WATCH: if bottom-bucket churn ever matters near the board,
revisit percentiles-vs-z-scores properly (shadow-lane A/B candidate).

## 2026-08-07 — Universe hygiene: 12 delisted tickers removed, BK->BNY renamed
M&A-wave zombies (JNPR/ANSS/HES/PARA/WBA/IPG/K/DAY/MMC/HOLX/FI/CTRA) had
stopped trading months ago but were still fetched (daily 404s) and scored
off stale prices (BK showed 1.9 on a 3-week-old close). Fundamentals rows
archived to fundamentals_delisted_archive, then removed. History (prices,
filings) retained. TODO monthly: staleness check — no price 10+ trading
days -> report bookkeeping line.

## 2026-08-09 — P4 CUTOVER: quality v3 + shrunk value + profiles + doctrine
QUALITY_DURABILITY_SPEC shipped end-to-end (user-approved at every gate):
canonical FMP data (P1), single-definition metrics + triptych assessor
(P2), and now live scoring on 10y trend-fit quality (40 level / 20 slope /
30 consistency / 10 cycle), sector profiles (BANK/REIT), hierarchical
value shrinkage (w=n/(n+8)), and the cyclical entry doctrine (flag at
nmad>0.15; unpunished cyclicals capped below Watch). Board ~65 -> ~48 by
merit. Held positions LHX (quality re-read: post-merger economics) and
HUBB (shrunk value mid-pack) go through the normal machinery — no
special-casing, user directive. No era reset: thesis unchanged, its
measurement improved.

## 2026-08-10 — Fiscal-calendar row hygiene (LHX audit follow-through)
User caught the report misattributing LHX's exit; the forensic exposed a
data class the P1 audit never checked: fiscal-calendar structure. Two
defects, both in quality_v3 row assembly: (1) 52/53-week fiscal years
ending Jan 1-14 collided with the next year's calendar key, silently
dropping a real year (19 symbols, incl. LDOS/LHX/TXT/DY); (2) vendor
zero-fill rows (revenue present, ROIC+op margin exactly 0) passed the
no-revenue guard as catastrophic readings (11 symbols). Fix: FY keyed to
the year it mostly covers (Jan 1-14 -> prior year), better-populated row
wins residual collisions, fake zeros treated as missing. Offline diff
(user-reviewed, approved): 8 movers >=0.03, one tiered — TXT 0.81->0.74
(the fake-zero year had manufactured an improvement trend; stays Buy).
LDOS 0.829->0.841. LHX 0.564->0.558 — exit verdict unchanged, countdown
proceeds on merit. Verified live == offline before push.

## 2026-08-14 — Track record v2d era: daily $100 lots, symmetric 2-day rules
User: "Strong Buys that remain Strong Buys don't tell us when to buy —
we can only ever buy randomly or consistently. Consistently is more
honest." Entry now mirrors exit: 2 consecutive Strong Buy readings ->
buy at the NEXT session's close; 2 consecutive below-Buy -> sell at the
next close; one $100 lot per episode; SPY twin on identical dates and
prices; fills only in the after-close run (morning fills would use the
signal close — look-ahead). Weekly era (v2) frozen complete at Aug 13
closes; v2d backfilled from Jul 23 and verified against the
user-approved offline simulation to the digit (13 lots, +2.28% picks vs
+2.31% twins — honest flat start; ACM's post-charge slide is now a
measured $100 position, LDOS +19pts vs twin). SMCI's 1-day Strong Buy
correctly never enters under the 2-day bar. Close fills for now;
day-average fills possible later once OHLC is stored (T+1 discipline
either way).

## 2026-08-14 (later) — v2d corrected to DAILY ACCUMULATION (user caught the miss)
The first v2d deploy implemented one lot per entry episode — wrong.
User's design: $100 EVERY day the last two readings are Strong Buy
(conviction weighted by its duration), all lots sold together at the
close after two straight readings below Buy, proceeds never reinvested
(equal-weight decision ledger, user-ratified). Re-backfilled from
Jul 23: 61 lots, $6,100 deployed, picks +3.63% vs twins +1.87%
(+1.76pp), 45 open / 16 closed — verified against the user-approved
simulation to the digit before deploy. LDOS carries 12 lots (+9.0pp),
ACM 7 (−9.1pp): long conviction and long mistakes both weigh fully.

## 2026-08-15 — v2d record finalized (user-directed corrections, disclosed)
Final basis, user-approved table verified to the digit before deploy:
Jul 23 start; $100/day per Strong Buy (2-reading confirmation); hold at
Buy; sell all below Buy; next-close fills; twins identical. USER
DECISIONS, disclosed on the site: MCK/LHX/RMBS excluded (only-SB
readings were error-era, pre-Aug-9 correction); PTC's Aug 3-5 sub-Buy
readings treated as Buy (error dip — held, not sold; its 6-lot Aug 5
"sale" removed). Result: 59 lots, $5,900; picks +3.28% vs twins +1.80%
(+1.47pp); sells on record: EIX +$2.31, HUBB +$9.05 (both Aug 12).
Deploy was executed ONLY on explicit user instruction after one halted
attempt (permission rule reinforced in memory). Anomaly noted: interim
v2d rows (61-lot version + Friday live buys) were absent before the
final wipe — end state verified correct; track_lots has no created_at
so the gap is untraceable → audit column added to V3.
