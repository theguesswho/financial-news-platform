# Quality & Data Foundation Redesign — Scope (DRAFT for sign-off)

Status: scoped 2026-08-09 after the Evercore case (cyclical recovery leg
scored as improving quality; assessor quoted a mis-computed "26% ROIC").
Nothing ships until this document is approved and the offline before/after
board review passes user sign-off. Same ritual as the v2 cutover.

## 1. The problem being solved

- Quality reads a 2-year improvement window: cannot tell a compounder
  from a cyclical's recovery leg (EVR ROIC 21→11→14→19 read as "improving").
- Three different numbers all named "ROIC" (crude net-income/(equity+debt)
  at 25.2%, FMP TTM 23.7%, history-table 18.6%) — the assessor was fed the
  flattering wrong one.
- History starts 2021: too short to see any full cycle, and starts at a
  cycle top. FCF for 2021-22 missing entirely for some names.
- Yahoo cannot fix this: 5 annual years max, no ROIC at all, unreliable
  TTM FCF. FMP (already paid) has 15 years + proper roicTTM. Verified
  2026-08-09 across mature names (15y), IPOs/spin-offs (full life), ETFs
  (none — correctly excluded).

## 2. Data foundation (approved in principle: FMP 15-year backfill)

- New canonical tables:
  - `fundamentals_annual`: symbol, fiscal_year_end, revenue, gross/op/net
    margin, fcf, roic, roe, debt_to_equity, shares_out — FMP key-metrics +
    statements, annual, up to 15 years, one-time backfill then yearly append.
  - `fundamentals_ttm`: same metrics TTM, FMP key-metrics-ttm, refreshed on
    the dirty-symbol cadence (earnings events), full sweep weekly.
- CANONICAL DEFINITIONS: one vendor (FMP), one definition per metric,
  used by scorer, assessor, and UI alike. The crude in-house ROIC formula
  is retired (column kept, repointed to FMP TTM). fundamentals_history
  stays for continuity but scoring stops reading its roic.
- Backfill mechanics: ~700 symbols x 2 endpoints, one-time, run through
  the Railway job queue in chunks; ETFs and index rows skipped; failures
  logged per symbol, never silent. Estimated cost: API quota only.

## 3. The metric triptych (user directive 2026-08-09)

Every metric that matters is always presented and consumed as THREE views:

1. **The road here** — backward window (5y standard; 10y for
   scoring-critical metrics): where is this company coming from?
2. **Last financial year** — the most recent audited snapshot.
3. **TTM** — how it is tracking since that snapshot (incl. delta vs FY).

Applies to: scorer inputs, qual assessor context tables, Stock Detail
display. The assessor prompt is updated in the same package so its
narrative voice must reconcile all three views (no more single-number
cherry-picking; "26% ROIC" becomes "23.7% TTM, vs 12.5% FY2025, vs a
volatile 10-year path peaking at 23.5%").

## 4. Quality v3 — durability-aware (10-year lookback for scoring)

Scoring-critical metrics (ROIC, FCF, revenue, operating margin) computed
over up to 10 years with the TREND-FIT method (median rejected by user —
punishes legitimate growth paths; validated on GDDY vs EVR):

- **Level**: TTM, canonical.
- **Slope**: recency-weighted regression over available history — growth
  paths rewarded, whatever their shape.
- **Consistency**: residual volatility AROUND the fitted trend, using a
  robust measure (median absolute deviation) so one blip year does not
  dominate — GDDY's monotonic climb scores high; EVR's boom-bust cannot
  hide. This is cyclicality, measured not guessed.
- **Cycle position**: TTM vs own 10-year peak (a "recovering toward prior
  peak" flag distinct from "at new highs").
- Young companies: full available life; minimum 3 annual points for a
  trend; below that, level+slope only with a neutral consistency prior.
- Composition/weights: decided OFFLINE by board comparison, not a priori.
  Peer-bucket percentile mechanics preserved (the composed quality feeds
  the same percentile slot the scorer already consumes; the 0.05 floor
  stands).

## 5. Rollout ritual (each gate = explicit user go)

- **P1 — Backfill + canonical tables** (data only; zero scoring impact).
- **P2 — Metric canonicalization**: assessor + UI fed the triptych from
  canonical tables; ROIC bug retired. (Prompt change — reviewed with user.)
- **P3 — Quality v3 offline**: compute for full universe; deliver
  before/after board diff (named test cases: EVR should fall / carry a
  cyclicality flag; GDDY-class compounders should hold or rise; steady
  industrials should be unmoved). User picks weights from evidence.
- **P4 — Cutover** on sign-off; V2_CONSIDERATIONS logged; SPY-twin record
  continues unbroken (no era reset — quality internals changed, thesis
  did not).

## 6. Risks / notes

- FMP annual ROIC differs from our history table's (definition change):
  the board WILL shift on canonicalization alone — P3's diff report
  isolates how much comes from data vs formula.
- Cyclicality consistency-penalty interacts with sectors that are
  legitimately cyclical but investable at the right point (miners on the
  board today: CDE, HL). The penalty should reduce QUALITY, while the
  story/price layers may still justify them — watch the diff for
  over-punishment.
- No new LLM cost; API one-time backfill + weekly TTM sweep within quota.
