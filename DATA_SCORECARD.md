# DATA_SCORECARD — every number the score reads, where it comes from, how old it may be

Born 2026-09-06 from the AECOM growth lesson (V3 #20/#21; CLAUDE.md
"Data integrity AND data coherence"). This is the oversight document:
anyone must be able to answer "where does this number come from and
how old can it be" for every scoring input FROM THIS FILE, not from
memory. It is updated in the same change as any data-path change.
A latency that is stated here is accepted. A latency found to differ
from what is stated here is an incident (V3_FIXLIST), not a footnote.

Owners (doctrine 2026-08-09, now enforced field by field):
- FMP — what companies REPORT (statements, statement-derived ratios)
- Yahoo — what the market SAYS (prices, multiples, analyst fields,
  PEG-vendor)
- SEC EDGAR / EarningsCall.biz / FMP transcripts — the DOCUMENTS
- Our own LLM passes — narrative facts derived from the documents

Status key: OK = coherent and within stated latency; RED = known
breach, ticket named; DUAL = two writers on one field (forbidden).

## A. Quant score inputs (pipeline/hidden_gem_scorer.py, pipeline/score.py)

| Field (fundamentals.*) | Source today | Owner should be | Expected latency | Consumer | Status |
|---|---|---|---|---|---|
| revenue_growth_yoy | FMP quarterly income stmt, `revenue` Q vs Q-4 by position (pipeline/fmp_quarterly.py `refresh_growth_block`: daily step 2a full universe, 22:00 step 3d just-reported, weekly 2a). Yahoo `_quarterly_trends` writes ONLY while growth_source != 'fmp' (never returned a block) | FMP | filing evening (3d) or next 06:00 daily; sentinel bar 3 days after the latest 10-Q/10-K | growth penalty (0.5x/0.75x), trajectory, assessor line, stock page | OK in code 2026-09-07; provenance on row (growth_source, growth_quarter_end, growth_filing_date = FMP vendor stamp, growth_fetched_at). PROD STILL YAHOO until the #20 push |
| earnings_growth_yoy | FMP quarterly income stmt, `netIncome` Q vs Q-4 by position, denominator abs(prior) | FMP | same | growth penalty, PEG conflict class, assessor line | OK in code 2026-09-07 — same row provenance. PROD STILL YAHOO until push |
| fcf_growth_yoy | FMP quarterly cash-flow stmt, `freeCashFlow`, aligned to the income rows BY POSITION (52/53-week filers carry different period stamps: ACM income 06-30 / cash-flow 07-03) | FMP | same | trajectory (score.py `_traj_score_live`) | OK in code 2026-09-07. PROD STILL YAHOO until push |
| quarterly_trends (JSON: dates, revenue, gross/op margin, net income, fcf; 8 quarters; `_provenance` block inside) | FMP quarterly income + cash-flow (same module); '_'-prefixed stash keys preserved | FMP | same | margin trend (score.py), fcf trajectory, themes stash, weekly fundamentals_history | OK in code 2026-09-07. PROD STILL YAHOO until push |
| gross_margin, operating_margin, net_margin | FMP TTM sync (`fmp_canonical.sync_to_fundamentals`) | FMP | weekly full sweep + same evening for just-reported (step 3d) | value bucket (gm), P/S eligibility (om), quality | OK |
| roic | FMP TTM sync | FMP | weekly + step 3d | quality | OK |
| roe | FMP TTM sync only — the Yahoo daily writer was removed 2026-09-07 (fundamentals.py) | FMP | weekly + step 3d | selected by the quality query (hidden_gem_scorer:465) but never used in the math (verified 09-06); assessor/stock page | OK in code (DUAL resolved). PROD Yahoo writer still live until push |
| debt_to_equity | FMP TTM sync only — Yahoo daily writer removed 2026-09-07 | FMP | weekly + step 3d | score.py debt_safety only — its callers (daily_score_archiver, retired 2026-08-04; screener; backtest) are OFF the live scheduler path; not a live scoring input | OK in code (DUAL resolved). PROD Yahoo writer still live until push |
| historical_metrics (per-quarter pe_ratio, roic, op_margin, revenue, …) | table written weekly (step 6, pipeline/fmp_historical.py) from FMP key-metrics + income stmt; upsert ON CONFLICT (symbol,date) DO UPDATE, fetched_at stamped every run | FMP | weekly (≤10 days on fetched_at); newest quarter ≤60 days | LIVE: `compute_gap_score` multiple_inertia (30% of gap → priced-in multiplier ×(0.70+0.50×gap)): pe_ratio now vs 12 months ago, roic & op_margin now vs prior row. NOT LIVE (corrected 2026-09-07): the P/S rank in `compute_value_score` (TTM revenue lateral SUM) has NO caller — score_all_stocks takes value from quality_v3.value_v3 | OK ON LIVE DB since 2026-09-06 13:43 UTC: UNIQUE (symbol,date) restored, 827/831 symbols (missing OZK ASND CHKP GTLS GLD — all zombie/stale-price names), MAX(date) 2026-08-02; upsert re-proven 2026-09-07 (10 symbols, 200 rows, 0 errors, 0 duplicate pairs) |
| ev_to_ebitda, pe_forward, pe_trailing, price_to_fcf, ev_to_fcf, price_to_book, market_cap, enterprise_value | Yahoo info | Yahoo (market says) | daily 06:00 fetch (≤24h) | value ranks (EV/EBITDA, P/E, P/FCF, P/S numerator) | OK |
| peg_ratio (+ peg_vendor, peg_source) | Yahoo vendor PEG, `_vendor_peg_writable` guard, `peg_normalizer` sustainable-growth replacement | Yahoo + our normalizer | daily; conflict class same run | assessor context ONLY — absent from scoring math (V3 #17) | OK |
| price_vs_52w_high, analysts_count, analyst_target_price | Yahoo info | Yahoo | daily | priced-in / crowding inputs, assessor | OK |
| sector, industry | Yahoo info | Yahoo | static | value bucket cascade | OK |
| eod_prices | Yahoo (`yf.download`, pipeline/prices.py) | Yahoo | daily after close (22:00) + 06:00 | priced-in, track record fills, momentum context | OK (sentinel max 4d) |

## B. Narrative / qual inputs

| Input | Source | Expected latency | Consumer | Status |
|---|---|---|---|---|
| 8-K, 10-Q, 10-K text | SEC EDGAR (steps 3, 3b) | same day (22:00 run) | wire, extractor, assessor, decay events | OK (sentinel: 8-K max 5d) |
| Earnings-call transcripts | EarningsCall.biz fast path (~15 min post-call) → FMP fallback (days) | same day; FMP fallback up to days — KNOWN | claims, themes, assessor, decay events | OK (sentinel max 7d) |
| narrative_exposures / filing_themes | our extractor (V3 #15 rubric v2) | same evening as the filing | narrative score, wire grades | OK |
| filing_themes.embedding | step 5 embeddings — PARKED since week of 08-10 | n/a while parked | decay silence path (starved — V3 #0) | KNOWN-INERT, decoupled; not this arc |
| qual_assessments | assessor (steps 8 / 6) on movers + unassessed Buy/SB | same run as the move | assessed_tier, promotions | OK (sentinel max 8d) |
| insider_trades | SEC Form 4 | daily | assessor context | OK (sentinel max 7d) |

## C. Sentinel expectations vs reality (pipeline/freshness_sentinel.py)

| Source | Checks | Max age | Note |
|---|---|---|---|
| fundamentals | MAX(fetched_at) | 8d | Checks the FETCH, not the CONTENT — passed throughout the ACM lag. The content check is the growth_quarter row below. |
| historical_metrics | MAX(fetched_at) | 10d | Refresh heartbeat (stamped on every row the weekly upsert touches). 115d on MAX(date) hid a dead table for four months (V3 #21). |
| historical_metrics newest quarter | MAX(date) | 60d | Newest quarter-end; lags 30-50 days by construction (10-Q lag). |
| growth_quarter:SYMBOL (per symbol) | fundamentals.growth_quarter_end vs latest 10-Q/10-K filing_date in `filings` | breach when the filing is >3d old AND (quarter_end IS NULL OR quarter_end < filing_date − 95d) | Content check, one alarm row per symbol. Keys on the QUARTER END, not FMP's fillingDate (a vendor stamp: earnings-release date for NUE, period-end placeholder for MDLN/PNFP). Calibrated 2026-09-07: healthy gap 10..62d across 820 symbols; a quarter that predates the filed one sits ≥~100d behind (ACM stale March quarter vs 08-11 10-Q: 133d). Symbols with no 10-Q/10-K on record (10) are not checked. Open at build: GLD only (ETF, no statements, never had a quarter). |
| eod_prices / leaderboard / daily_brief / 8-K / transcripts / qual / narrative_exposures / narrative_history / insider_trades | MAX(timestamp) | 2–9d | Fetch-recency checks; adequate for document feeds where arrival = content. |

Standing rule (CLAUDE.md, 2026-09-06): every status/board readout
reads back the open rows in env_diagnostics source='freshness'. Silent
green while a row is red is forbidden.

## D. Change log

- 2026-09-06 — created. Findings #20 (growth block on Yahoo, weeks
  late; FMP same-day), #21 (historical_metrics dead — missing UNIQUE
  (symbol,date)), DUAL roe/debt_to_equity. No code changed; no push.
- 2026-09-06 evening / 2026-09-07 — freeze sitting (V3 #20/#21), GATE
  presented, NOT PUSHED. #21 applied on the live DB (constraint,
  fetched_at, full refresh). #20 built: growth block re-homed onto FMP
  for 830/831 rows on the live DB with provenance (GLD: FMP empty,
  Yahoo empty, no statements); Yahoo fallback gated on growth_source;
  roe/debt_to_equity Yahoo writers removed; sentinel 10d/60d bars +
  per-symbol growth_quarter check. CORRECTION to this file: the
  historical_metrics live consumer is compute_gap_score (multiple
  inertia), not the P/S rank — compute_value_score has no caller.
  Proofs: ACM FMP income fillingDate 2026-08-10 (accepted 16:35),
  cash-flow 2026-08-11; live row source=fmp quarter 2026-06-30 rev
  −14.18% earn −166%; this-week filers HPE / MDT / LULU (10-Q 09-03)
  carry quarter 07-31 / 07-31 / 08-02 with filing 09-03. Until the push
  the prod daily (06:00 UTC) still runs the Yahoo writer: values revert
  to Yahoo while growth_source reads 'fmp' — the cutover closes it.
