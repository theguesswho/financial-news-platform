# DESK — shared board (Grok / Claude / Edmund)

Updated 2026-09-21 (away-lane sitting 1: no ETFs in the universe).
**Rule:** any sitting that changes plans or status updates this file
in the same PR. Chat-only status essays do not count.

## Status

- **Prod SHA:** `a7aafee` on `main` (R1). Sitting 0 docs landed as
  `d1c1736`. This sitting is **branch + PR only** — not on prod.
- **R1 (V3 #26):** SHIPPED on main. Ceilings 240 / 300 / 360 min
  (Edmund 2026-09-20: do not raise).
- **Sitting 1 (this PR):** ETF exclusion wired. GLD soft-excluded
  from score / fetch / growth / onboard / assessor / theming.
  History row stays. FMP-empty KPI logs the full list + buckets.
  `DATA_SCORECARD` "PROD STILL YAHOO" ghost corrected (prod
  2026-09-20: 830 fmp / 1 null = GLD).
- **Health / freshness:** still a prod-check item (sitting 0 did
  not hit Railway). Open freshness: unknown until Edmund reads
  `env_diagnostics`. Do not write "none open".
- **Watch-path isolation:** still OPEN. A docs-only push still
  counts as a scheduler restart until a web-only push is observed
  leaving the scheduler untouched. Every push of this PR will
  restart the scheduler.

## Active sitting

Away-lane 1 — **Universe: no ETFs** (this PR):
`pipeline/universe.py` + consumers + FMP-empty KPI + DESK / scorecard
/ FIXLIST stamps. No score-math. No Railway. No prod DB writes.

## Next sittings (ordered)

1. **V3 #23 Gap honesty A+B** — Grok rulings locked 2026-09-08; **no
   score math**. Opens when Edmund opens it. Report-back before code.
2. **Hold for Edmund** — FMP quota redesign (#25 note) needs his plan
   tier before any code. Do **not** start #24 (freeze) or
   embeddings / decay Phase 2 / replay.

## Open incidents / parked

- **15–17 Sep** snapshots / editions / lots: real gap. `platform_notes`
  id 7 already labels it (active 09-15 → 09-22). **Never backfill.**
- **FMP 429 evenings** (#25 design note): parked pending Edmund's plan
  tier. Sitting 1 only *measures* empties (KPI). Not a redesign.
- **Embeddings / silence decay / NARRATIVE_SPEC Phase 2:** parked
  (V3 #0; Edmund 2026-09-05). Decay still starved.
- **Replay:** design only (`NARRATIVE_REPLAY_DESIGN.md`). Parked.
- **#24 Gap math C+D:** freeze; Edmund GATE; not next.
- **Watch-path isolation:** still unproven (CLAUDE.md / FRONTEND_SPEC).
  Docs or pipeline push = scheduler redeploy.
- **Operating-company extras** ASND, CHKP, GTLS, OZK (in fundamentals,
  not in tickers.txt): NOT ETFs. Left in place. Separate hygiene.

## Handoff

**This sitting built:** ETFs out of the live universe (pattern, not a
GLD mute). Onboard rejects ETF / grantor trust via known list + Yahoo
`quoteType` + FMP `isEtf`/`isFund`. Growth / canonical logs keep the
full empty list and classify etf / quota_429 / transport / true_hole.
Sentinel imports `pipeline.universe.ETF_SYMBOLS`. Soft exclude — no
DELETE of the GLD fundamentals row.

**Verify (after merge, on a box that can import the branch):**
1. `python -c "from pipeline.universe import ETF_SYMBOLS; assert ETF_SYMBOLS == frozenset({'GLD'})"`
2. `python scripts/test_universe_hygiene.py` — GLD dropped from
   filter/score-skip/onboard known-list; empty list of 25 not truncated;
   ASND/CHKP/GTLS/OZK stay; SPY/MDY not in ETF_SYMBOLS.
3. Onboard: `phase_validate(["GLD"])` rejects without a vendor call.
   A live ETF (any `quoteType=ETF`) is rejected when Yahoo answers.
4. After the first post-merge daily: GLD must not appear in
   `score_all_stocks` output. Growth log must print `empty=[...]` in
   full (no `[:20]`).

**Claude next:** after Edmund merges and **opens sitting 2 (#23)**.
Do not implement #23/#24, FMP quota, embeddings, scorer math, or
15–17 boards. Update `DESK.md` in that PR.

**Needs Edmund:** (1) merge this PR when ready; (2) **push only at
Railway in a clear window** — every push still restarts the
scheduler until watch paths are proven; (3) prod checks still in
`TRIAGE_2026-09-20.md` if not yet done; (4) open #23 when ready.
This PR is not a Railway deploy.
