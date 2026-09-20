# DESK — shared board (Grok / Claude / Edmund)

Updated 2026-09-20 (away-lane sitting 0: triage). **Rule:** any sitting
that changes plans or status updates this file in the same PR. Chat-only
status essays do not count.

## Status

- **Prod SHA:** `a7aafee` on `main`. Edmund: R1 deployed after this SHA.
  Code commit is `a32ab72` (05:36 UTC); ceilings commit `a7aafee` (06:00
  UTC, daily-slot start).
- **R1 (V3 #26):** **SHIPPED** on main. Ceilings 240 / 300 / 360 min
  (Edmund 2026-09-20: do not raise).
- **Health / freshness:** NEEDS PROD CHECK. This sitting did not hit
  Railway or the DB. Do not assume green. Queries in
  `TRIAGE_2026-09-20.md`.
- **Scorecard ghost:** `DATA_SCORECARD.md` still says "PROD STILL YAHOO
  until the #20 push". #20/#21 code is an ancestor of `a7aafee`. Confirm
  with the growth_source query in the triage file.

## Active sitting

Away-lane 0 — **docs / triage only** (this PR): `DESK.md` +
`TRIAGE_2026-09-20.md` + light `V3_FIXLIST.md` stamps. No feature work
under `pipeline/` or `scheduler_light.py`.

## Next sittings (ordered, 3)

1. **Universe: no ETFs** — Edmund ruling 2026-09-20. Not "mute GLD".
   Identify how extras enter `fundamentals` vs `tickers.txt`; exclude
   ETFs from score / fetch / onboard. Fold in the FMP-empty
   classification KPI (ETF vs quota vs true hole). Size M.
2. **V3 #23 Gap honesty A+B** — Grok rulings locked 2026-09-08; **no
   score math**. Opens when Edmund opens it.
3. **Hold for Edmund** — FMP quota redesign (#25 note) needs his plan
   tier before any code. Do **not** start #24 (freeze) or
   embeddings / decay Phase 2 / replay.

## Open incidents / parked

- **15–17 Sep** snapshots / editions / lots: real gap. `platform_notes`
  id 7 already labels it (active 09-15 → 09-22). **Never backfill.**
- **FMP 429 evenings** (#25 design note): parked pending Edmund's plan
  tier. Not sitting 1.
- **Embeddings / silence decay / NARRATIVE_SPEC Phase 2:** parked
  (V3 #0; Edmund 2026-09-05). Decay still starved.
- **Replay:** design only (`NARRATIVE_REPLAY_DESIGN.md`). Parked.
- **#24 Gap math C+D:** freeze; Edmund GATE; not next.
- **Watch-path isolation:** still unproven (CLAUDE.md / FRONTEND_SPEC).

## Handoff

**Grok decided (this sitting):** #26 is SHIPPED; #1 HIGH is stale (wired
2026-08-11, `6963384`); "NOT PUSHED" on #20/#21/#25/#13/#14 is a ghost
if prod is `a7aafee`; ETF exclusion is sitting 1, not an alarm mute;
FMP-empty rate is a KPI (GLD vs LW/MAS); #24 / embeddings / replay /
quota stay parked. Away-lane writes **branch + PR only** — standing
brief "Grok never writes this repo" does not license main or Railway.

**Claude next:** after Edmund merges this PR, wait for him to **open
sitting 1**. Follow `TRIAGE_2026-09-20.md`. Update `DESK.md` in that PR.
Do not implement #23/#24, FMP quota, embeddings re-embed, scorer
behavior, or 15–17 boards.

**Needs Edmund:** (1) prod checks in the triage file — `/health/platform`,
today's daily, migrate line, growth_source, ETF inventory, freshness
rows; (2) external monitor on `/health/platform` + site root; (3) open
sitting 1 when ready; (4) freeze items stay his. This PR is not a
Railway deploy.
