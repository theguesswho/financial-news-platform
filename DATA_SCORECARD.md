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
| revenue_growth_yoy | Yahoo quarterly statements (`_quarterly_trends`→`_yoy_growth`), info fallback | FMP quarterly income stmt | filing day + same evening (step 3d) — ACTUAL: weeks (Yahoo) | growth penalty (0.5x/0.75x), trajectory, assessor line, stock page | RED — V3 #20 |
| earnings_growth_yoy | same | FMP quarterly income stmt | same | growth penalty, PEG conflict class, assessor line | RED — V3 #20 |
| fcf_growth_yoy | Yahoo quarterly cash-flow | FMP quarterly cash-flow | same | trajectory (score.py `_traj_score_live`) | RED — V3 #20 |
| quarterly_trends (JSON: dates, revenue, gross/op margin, net income, fcf; 8 quarters) | Yahoo | FMP | same | margin trend (score.py), fcf trajectory, themes stash, weekly fundamentals_history | RED — V3 #20 |
| gross_margin, operating_margin, net_margin | FMP TTM sync (`fmp_canonical.sync_to_fundamentals`) | FMP | weekly full sweep + same evening for just-reported (step 3d) | value bucket (gm), P/S eligibility (om), quality | OK |
| roic | FMP TTM sync | FMP | weekly + step 3d | quality | OK |
| roe | Yahoo info DAILY (fundamentals.py:296) AND FMP sync WEEKLY | FMP | — | selected by the quality query (hidden_gem_scorer:465) but never used in the math (verified 09-06); assessor/stock page | DUAL — resolve in #20 sitting |
| debt_to_equity | Yahoo info DAILY (fundamentals.py:305) AND FMP sync WEEKLY | FMP | — | score.py debt_safety only — its callers (daily_score_archiver, retired 2026-08-04; screener; backtest) are OFF the live scheduler path; not a live scoring input | DUAL — resolve in #20 sitting |
| TTM revenue (P/S leg) | historical_metrics lateral SUM(last 4 revenue) — table written weekly from FMP key-metrics + income stmt | FMP | weekly (≤10 days) — ACTUAL: dead since ~May; MAX(date) 2026-05-10; 334/831 symbols no rows | value P/S rank (mcap / rev_ttm) | RED — V3 #21 |
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
| fundamentals | MAX(fetched_at) | 8d | Checks the FETCH, not the CONTENT — passed throughout the ACM lag. #20c adds a per-symbol quarter-vs-filing check. |
| historical_metrics | MAX(date) | 115d | Wrong bar for a weekly table; violating since 2026-09-04, unread by the desk. #21 cuts to 10d. |
| eod_prices / leaderboard / daily_brief / 8-K / transcripts / qual / narrative_exposures / narrative_history / insider_trades | MAX(timestamp) | 2–9d | Fetch-recency checks; adequate for document feeds where arrival = content. |

Standing rule (CLAUDE.md, 2026-09-06): every status/board readout
reads back the open rows in env_diagnostics source='freshness'. Silent
green while a row is red is forbidden.

## D. Change log

- 2026-09-06 — created. Findings #20 (growth block on Yahoo, weeks
  late; FMP same-day), #21 (historical_metrics dead — missing UNIQUE
  (symbol,date)), DUAL roe/debt_to_equity. No code changed; no push.
