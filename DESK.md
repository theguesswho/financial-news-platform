# DESK — shared board (Grok / Claude / Edmund)

Updated 2026-10-09 (CLAUDE_TASKS T1: deploy triggers + E_DIAG).
**Rule:** any sitting that changes plans or status updates this file
in the same PR. Chat-only status essays do not count.

## Status

- **Prod SHA:** `ea3d730` on `main` (Sitting 1 merged; Railway
  scheduler `a53b08b4` + api `2cc5c225` SUCCESS 2026-09-21 12:14 UTC
  — verified from the deployment list 2026-09-28). R1 = `a7aafee`,
  sitting 0 docs = `d1c1736`, both included.
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

**CLAUDE_TASKS T1 (opened 2026-10-09)** — watch-path isolation + flap
diagnostic logging, one push. Local only; NOT pushed. Commits:
`014f665` (new CLAUDE_TASKS) on top of `e6c59d8`, plus the T1 code
commit. Logging only — no score math.

### Deploy triggers (read from `railway status --json`, 2026-10-09)

No `railway.json` / `railway.toml` / `nixpacks.toml` in the repo.
Watch paths, root dir and start command all live in the Railway
dashboard (service settings), not in a repo file.

| Service | Root | Build | Start | Watch paths NOW |
|---|---|---|---|---|
| `financial-news-platform` (scheduler) | `/` | `/Dockerfile` | `python scheduler_light.py` | `**`, `!web/**` |
| `api` | `/` | `/Dockerfile` | `uvicorn api.main:app` | `api/**`, `pipeline/**`, `db/**`, `requirements.txt` |
| `impartial-heart` (Streamlit lab bench) | `/` | `/Dockerfile` | `streamlit run ui/Home.py` | `**`, `!web/**` |
| `web` | `web` | Railpack | (default) | `web/**` |

So today: ANY push outside `web/` — markdown included — rebuilds
and restarts the scheduler AND Streamlit. `api` already skips
docs-only pushes (not yet observed). Dockerfile is `COPY . .`; only
the paths below change runtime behaviour.

What each process actually loads (static import trace + file reads,
2026-10-09): scheduler → `scheduler_light.py`, `pipeline/`, `db/`,
`config/` (tickers.txt, company_map.json), `requirements.txt`.
api → `api/`, `pipeline/`. Streamlit → `ui/`, `pipeline/`, `db/`.
Not loaded by any service: `scripts/` (deploy gate + one-off tests
only), `common/`, `scheduler.py` (legacy), every `*.md`.

**Proposed watch paths (to set in the dashboard — not yet set):**
- scheduler: `pipeline/**`, `db/**`, `config/**`, `scheduler*.py`,
  `requirements.txt`, `Dockerfile`
- api: `api/**`, `pipeline/**`, `db/**`, `config/**`,
  `requirements.txt`, `Dockerfile`
- impartial-heart: `ui/**`, `pipeline/**`, `db/**`, `config/**`,
  `requirements.txt`, `Dockerfile`
- web: `web/**` (unchanged)
None of these match `*.md`, `docs/**`, `TRIAGE_*`, `CLAUDE_TASKS.md`.
Proof still owed: a markdown-only push after T1 shows scheduler,
api and impartial-heart SKIPPED (record date + deployment ids here).

### E code paths (T1 item 5)

Every E computation goes through ONE function,
`hidden_gem_scorer.compute_call_vs_filing_gap`, which reads the era
from the environment at call time. The `E_DIAG` line is logged there,
so it covers every caller (two lines per full re-score: once via
`compute_narrative_score`, once for display). Callers:
- scheduler child jobs daily / after_close / weekly →
  `_score_and_archive` (tagged `run=<job>@<slot>`)
- scheduler PARENT thread `_process_job_queue` (onboarding re-score)
  → `score_all_stocks` (shows `run=adhoc`, `via=…_process_job_queue`)
- fallbacks: `leaderboard_archiver.archive_leaderboard`,
  `qual_assessor` (when no gems passed), `deep_dive_batch`,
  `shadow_lane`
- Streamlit `ui/app.py` (`load_gem_scores`, `get_gem_for`)
- legacy `scheduler.py` (launchd jobs disabled 2026-08-16)
No path computes E with its own SQL or bypasses the era clause. So
the flap is not a bypass: the clause itself must be coming out empty
in some runs (env unset/empty in that process), or the row set
differs. `E_DIAG` logs `era_env`, `clause`, `qualifiers`, `max_gap`,
`rows_by_era_in_window`, pid/ppid and the call chain to tell which.
Local check 2026-10-09 against the prod DB: era=2 → 329 qualifiers,
max gap 0.4643; unset → 806, max gap 0.55 (rows in window: era-1
4066, era-2 5092). The scorer writes nothing, so a mixed read in
Streamlit cannot reach the board.

### Lab bench (T1 item 6)

`FILING_THEMES_RUBRIC_ERA` is set ONLY on the scheduler service
(=2). It is unset on `api` and `impartial-heart`. The Streamlit
bench therefore computes E under the mixed read. Not the prod cause
(read-only), but bench and prod must agree — fix belongs in T2
(era rule enforced in the query helper, default 2).

## Next sittings (ordered)

1. **V3 #23 Gap honesty A+B** — Grok rulings locked 2026-09-08; **no
   score math**. Opens when Edmund opens it. Report-back before code.
2. **Hold for Edmund** — FMP quota redesign (#25 note) needs his plan
   tier before any code. Do **not** start #24 (freeze) or
   embeddings / decay Phase 2 / replay.

## Open incidents / parked

- **Universe-wide E flap** (was the parked 28 Sep T1; now
  CLAUDE_TASKS T2, un-parked 2026-10-09): E for ~800/822 names
  toggles between era-2 and mixed reads, on and off since 25 Sep.
  T1's `E_DIAG` line is the instrument; T2 is the fix.
- **15–17 Sep** snapshots / editions / lots: real gap. `platform_notes`
  id 7 already labels it (active 09-15 → 09-22). **Never backfill.**
- **FMP 429 evenings** (#25 design note): parked pending Edmund's plan
  tier. Sitting 1 only *measures* empties (KPI). Not a redesign.
- **Embeddings / silence decay / NARRATIVE_SPEC Phase 2:** parked
  (V3 #0; Edmund 2026-09-05). Decay still starved.
- **Replay:** design only (`NARRATIVE_REPLAY_DESIGN.md`). Parked.
- **#24 Gap math C+D:** freeze; Edmund GATE; not next.
- **Watch-path isolation:** still unproven (CLAUDE.md / FRONTEND_SPEC).
  Docs or pipeline push = scheduler redeploy. Now CLAUDE_TASKS T1;
  current state under "Deploy triggers" above.
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
