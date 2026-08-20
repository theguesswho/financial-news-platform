# Frontend v2 — scope and build plan

Written 2026-08-09 in the methodology session, as the durable handoff to the
build sessions. The build happens in fresh sessions; this document is the
contract between them. Update it as decisions land — it, not any chat, is
the source of truth.

## Why

Streamlit got us to a working platform fast, but it is a prototyping tool:
every interaction is a full page rerun, design control is coarse, mobile is
poor, and state (filters, drill-downs, cross-page context) fights the
framework. The platform's brain — pipeline, scoring, narratives, Postgres —
is sound and does not change. This project replaces only the presentation
layer.

## Architecture

```
Postgres (Railway)  ←  pipeline / scheduler        (unchanged)
        ↑
   api/  FastAPI    ←  NEW: read layer + portfolio mutations
        ↑
   web/  Next.js    ←  NEW: the actual product UI
```

- **api/** — FastAPI service in this repo. Thin: SQL in, JSON out. Reuses
  pipeline modules (portfolio math, tiers) rather than duplicating logic.
  The existing `api/` folder is a June-era prototype for a different
  product (auth/watchlist, pre-v2 scoring) — **delete and rewrite**, do not
  retrofit. Same for the June `frontend/` folder once salvage is checked.
- **web/** — fresh Next.js + Tailwind app (name it `web/` to avoid ghosts
  of `frontend/`). Deployed as its own Railway service with watch path
  `web/**` so UI deploys never touch the scheduler.
- **Streamlit is permanent** (decision 2026-08-10): it is the
  methodology track's internal lab bench and is NOT retired at parity.
  The product (web/) is a separate track for external users — see
  DESIGN_BRIEF.md for identity/nav/design, CLAUDE.md for the two-track
  boundary (product never modifies pipeline/scoring/Streamlit/platform
  tables; product state lives in new tables).

## Non-negotiables (carried from the methodology — do not relitigate)

1. **Plain lexicon.** No internal jargon on any surface. 10-point scores.
   Direction words spelled out ("got cheaper vs peers — bullish").
2. **News hierarchy.** Strong Buys first (new/exits/news), then Buys, then
   only truly noteworthy movers. Applies to any feed-like surface.
3. **Band-transition memory.** Anywhere a tier change is shown, the prior
   band context must be reachable (what data came before, why it moved).
4. **Honest surfaces.** No celebration framing, no pandering. Losses and
   downgrades displayed with the same visual weight as wins.
5. **Deploy safety.** The web service must be isolated by watch paths so
   its deploys cannot restart the scheduler. Until watch paths are
   confirmed in Railway, every push counts as a scheduler restart — the
   pre-push gate stays in force.
6. **Portfolio-tracker READ-ONLY.** The Desktop folder and its Firebase
   are never touched. Our Postgres portfolio tables are the live store.

## API surface — SUPERSEDED 2026-08-16 (kept for history; a cold
## session must follow THE AGREED ROADMAP section, not this)

Boundary conventions (decided 2026-08-10, Phase 1):
- **Scores cross the API on the 10-point display scale** (the `fmt10`
  rule applied at the boundary, as numbers, 1dp). Internal 0–1 math
  never leaves the API; `None` passes through so "no data" stays
  distinguishable from 0. Helper: `api/deps.py::ten()`.
- Tier names, momentum words, and direction words pass through verbatim
  from the DB (already plain-lexicon).
- Errors: FastAPI HTTPException — 404 for unknown symbol / report date.

Read endpoints first — they carry no risk and unblock all UI work:

- `GET /board` — current leaderboard: symbol, gem (10-pt), tier (final,
  i.e. assessed_tier over tier), components, countdown state.
- `GET /stocks/{symbol}` — dossier: score history, band history, latest
  assessment, fundamentals triptych (10y / last FY / TTM), events, filings.
- `GET /narratives` — the map: parented tree, weights, momentum, exposures
  with final tiers (port the logic just built in ui/pages/2_Themes.py).
- `GET /reports/{date}` + `GET /reports/latest` — session-indexed editions,
  masthead payload, week grid.
- `GET /events`, `GET /insiders`, `GET /news` — current pages' queries.
- `GET /portfolio` — holdings, realized, cash, SPY twin, Dietz windows,
  day movers.

Mutations last, once auth exists:

- `POST /portfolio/transactions`, `DELETE /portfolio/transactions/{id}`
  (soft delete, as today).

## Page build order — SUPERSEDED 2026-08-16 (front door reversed to
## the Board; see THE AGREED ROADMAP. Kept for history only.)

Nav is five nouns: Narratives / The Board / Companies / What Changed /
Portfolio. (FRONT DOOR REVISED 2026-08-10: Narratives is the landing —
"FASTgraphs is the graphs; we are the narratives." See DESIGN_BRIEF.md
Landing page section.) Events, insiders, and news dissolve into
Companies and What Changed — they are not pages.

1. **Signature view + The Board** — the design centerpiece first (2–3
   live variants, user picks, tokens locked into DESIGN_BRIEF.md), then
   the Board built as that view collapsed to a row per stock. (Board is
   no longer the front door but remains the core opportunity-set page —
   none of this work is wasted.)
2. **Companies** — the workbench dossier: signature view, band history,
   assessment, triptych, events/insiders/filings in context.
3. **Narratives landing** (PROMOTED) — the front door: forces with
   company counts, emerging strip, shifts/weakness from the ledger,
   bridge into the Board; three-layer map behind it.
4. **What Changed** — the daily edition as instrument log.
5. **Portfolio** — owner-only; mutations + auth decision.

## Open decisions (user sign-off before the relevant phase)

- **Auth**: single-user platform. Simplest honest option: one shared
  secret (env var) gating mutations; read endpoints private behind
  Railway's network or the same token. Decide before Portfolio phase.
- **Hosting web/**: Railway (one bill, one place) vs Vercel (better Next
  defaults). Default: Railway unless a concrete need appears.
- **Design language**: extend the report page's editorial style across the
  app (recommended) vs a fresh design pass first.
- **News Wire nav placement** (FIXPACK_2026-08-19 Session B): fifth
  noun vs inside "What changed" — Edmund's call, made in conversation
  before B runs; current lean (b), four-noun nav LOCKED until he picks.
  DECIDED 2026-08-19 (scope, not nav — Edmund's words in the FIXPACK
  B1 amendment): besides the separate News Wire page, /home's right
  rail gets one-line News headlines ABOVE the Forces rail, linking
  into the page; same read-only endpoint feeds both.
  NAV DECIDED 2026-08-19, same day (Edmund, option a — his words in
  the FIXPACK B header): News Wire is the FIFTH nav noun, order
  The Board / Forces / What changed / News Wire / Track record, PLUS
  the Board-page rail pane above Forces. Built in Session B (see the
  Session B Progress entry); the STANDING BRIEF's four-noun line is
  amended by the dated update below, per Edmund himself. RESOLVED.

## STANDING BRIEF (2026-08-16 — read FIRST, every session; replaces all
## one-off session notes. Do not reopen closed items to be helpful.)

Source: Grok review ↔ Claude build alignment, pasted by Edmund 16 Aug.
Verbatim; later sessions may append dated updates below it, never edit
it in place.

### Roles
- Claude: implement in this repo. Local commits. Pattern fixes, never
  one-name patches. Stop when the brief says stop.
- Grok: review only. Does not write this repo. ACM/SANM/INTU are worked
  examples of a rule, not tickets.
- Edmund: the only person who pushes, opens Railway, or decides
  methodology freeze items (V3 #11, #12, #13, 35-vs-38). If a step
  needs him, ask first, in one exact sentence, before doing it. Never
  write as if he already did it.

### Done — do not touch
`/` is The Board. Four nav nouns. Assessor fully dark. Hold is silence.
Street labeled. Mention-set + smallest-n. Quality = five FY + TTM,
never a revenue road. Law 17 belt is thick enough (do not widen the
regex). Since-date = first lot (27 Jul). Wrinkle 35-vs-38 stays
visible, not diagnosed. Streamlit untouched. Laptop launchd plists
stay disabled. Pre-Railway leftover files stay in the working tree.
Pair page, Portfolio, product name: not this phase.

### Live on production (already pushed)
- Board, Forces, What changed, Track record, company pages.
- GET /narratives/{id} + roster, scorecard is read-only, ARE
  annual_history from fundamentals_annual.
- Known prod lie, still up: force "on the board" includes names not on
  /board (INTU, PCG, EIX on force 1).

### Local only, not pushed (ahead of origin)
[CLOSED 2026-08-16 07:27 UTC — PUSHED with Edmund at the Railway
dashboard, his explicit "push". Deploy gate clear (post-daily window).
VERIFIED ON PROD 07:35 UTC: forces 1/11/40 — ghosts NONE, field
mismatches vs /board NONE, off-board badges NONE, INTU/PCG/EIX not in
any on_board. The prod lie is DOWN. Scheduler service restarted
07:29:55, all three jobs re-armed (daily 08-17 06:00, after-close
Mon–Fri, weekly 08-21 23:30). Note: /board carried 41 names after the
morning run (SANM machinery-downgraded SB→Buy same run).]
- Shared `board_membership` / `_resolve_tier`. Force rosters intersect
  that set. Off-board attached names get no call badge.
- FRONTEND_SPEC + V3 #13 note.
- These ride the NEXT push, and only when Edmund is at Railway and has
  said "push".

### Rules that keep getting missed
1. No push, no deploy, no `git push`, unless Edmund has just said to,
   and is at the Railway dashboard.
2. Do not ask him to "check Railway" after the fact. If you need him,
   ask before the action, one step: what to open, what "healthy" looks
   like, what to reply.
3. Prefer CLI yourself. Only ping him when the CLI cannot answer.
4. Kill stale :8010/:3100 at the start of every local verify.
   `/health` 200 is not proof. Hit `/board`.
5. Verify on production after a push, and say "prod still has X" when
   the fix is local only.
6. Do not invent a Railway confirmation, a user trip, or a closed
   ticket. If you only recorded a bug, say recorded, not fixed.
7. Methodology files (pipeline/, scheduler, scoring) only when the
   brief names that file. V3 items are logged, not decided here.

### Right now
- Nothing to code. Session is closed.
- Proof still outstanding: the 06:00 UTC `scheduler_light` daily run.
  If it fails, tell Edmund in one sentence. If it succeeds, record it
  and stop. [PROOF RECORDED 2026-08-16: run fired 06:00, "DAILY
  UPDATE COMPLETE" 07:09 UTC, job "executed successfully", next run
  armed 2026-08-17 06:00. Watched live via CLI. 69 min vs ~50 usual —
  two benign notes: FMP quarter-list HTTP 429s near the end of the
  transcript sweep (vendor daily quota; names skipped gracefully,
  ✗1 failed of 822) and Railway's 500 logs/sec cap dropped ~70 log
  lines (cosmetic). Board output normal: 828 scored, 45 on-board,
  overrides promoted 3, all sources fresh, brief generated. SANM
  downgraded SB→Buy by the machinery itself (priced-in threshold) —
  noted only; worked example, not a ticket.]
- Next coding session (only when asked): push the membership fix with
  Edmund present, then confirm ON PROD that force 1/11/40 on_board ⊆
  /board and INTU/PCG/EIX have no call badge.
- Do not start anything else.

### Dated updates (append-only)
- 2026-08-20 HOUSEKEEPING SESSION ASSIGNED (Edmund's review of the
  live board + wire; product track, api/+web/ only, one session,
  local commit no push):
  (1) RAISED-CALL MARKER — SMCI reads Strong Buy at score 3.5 above
      TPL's Buy 4.7. That is CORRECT methodology (the board ranks by
      call first, score within call) and SMCI is NOT promoted — the
      assessor RAISED its tier above the score tier. CORRECTED per
      Edmund 2026-08-20 (two rounds): (i) internally there are TWO
      routes to a call above the score tier — the assessor's direct
      verdict (SMCI) and the narrative-override promotion
      (qual_promoted + gem_adjusted) — but both ARE the qual layer's
      judgment; the reader gets ONE concept, ONE mark, never two
      glyphs for the same judgment. (ii) The denotation IS A SYMBOL,
      not a wordy label (Edmund: "a symbol, or something easy").
      Spec: a small ◆ immediately after the call text (e.g. "Strong
      Buy ◆"), same color as the call chip; ONE legend line at the
      board's foot: "◆ call set by our assessment"; the plain-words
      sentence ("our assessment sets the call; the score alone would
      say <quant tier>") lives ONLY in the hover/tooltip. Detection:
      disagreement.kind=="raised" OR qual_promoted where the
      displayed call outranks the score tier. The session may
      propose a nicer glyph than ◆ at build time, but it must be a
      single quiet symbol in the call's color — no asterisk footnote
      soup, no text badge.
      Same session: grace-seated names (exit_grace) currently show
      assessed=false — decorate honestly (known cosmetic gap,
      recorded 2026-08-20).
  (2) BOARD COLUMN ALIGNMENT — Name/Call/Score/Moved/Story headers
      do not line up with their columns. CSS fix.
  (3) WIRE DELTA TIEBREAK (api, small) — signal_delta uses
      LAG(...ORDER BY filing_date) with NO same-date tiebreak: EL's
      same-day 10-K + call order is ambiguous, so which one counts
      as "prior" is nondeterministic. Add a deterministic tiebreak
      (filing_date, then type priority 10-K/10-Q before call, then
      id) and state it in the router docstring. Semantics otherwise
      CONFIRMED correct: caret = strength vs the symbol's previous
      filing, shown when the move >= 0.5 on the 10-pt scale.
  NOT in this session: V3 #15 positivity skew (methodology, Edmund's
  ruling), any scoring change.
- 2026-08-18: membership fix PUSHED (Edmund at dashboard, explicit
  "push") and CONFIRMED ON PROD same day — forces 1/11/40 clean,
  trio unbadged. That "next coding session" item is CLOSED.
- 2026-08-18 INCIDENT: NaN-poisoned board snapshot took prod /board
  down. Fix session is governed by INCIDENT_2026-08-18_NAN_BOARD.md
  (its own opener sentence, hard 21:30 UTC checkpoint). Nothing else
  runs until it closes.
- 2026-08-18 DECISION (Edmund, verbatim intent): score-driven and
  assessor-driven board moves are EQUALLY valid news — "it doesn't
  matter if it's a pure score putting something on the board or the
  assessor". The report writer currently classes stamp-only tier
  changes as "bookkeeping" (one ledger line; DVA 08-17 got this while
  FDS got the top story). FIX, ASSIGNED to the first session after the
  incident session closes: in pipeline/daily_report.py, any move that
  CHANGES BOARD MEMBERSHIP OR TIER is a real move regardless of
  driver; "bookkeeping" shrinks to stamp changes with NO tier
  consequence. _significance may rank assessor-driven entries; it may
  not bury them. While unfixed: the product under-reports
  assessor-driven moves — treat What-changed as incomplete.
- 2026-08-18 V3 #14 logged: report masthead counted board=36 while
  /board showed 41 the same morning — a THIRD membership definition
  on the report path (pipeline/daily_report.py _masthead). Same
  disease the roster fix cured; belongs to the board_membership
  pattern. Logged in V3_FIXLIST, not decided here.
- 2026-08-18 (later session): BOTH assigned fixes BUILT, LOCAL ONLY —
  NOT pushed; prod still under-reports assessor-driven moves and
  still mastheads its own board count until the next approved push.
  (a) bookkeeping-vs-real-move in pipeline/daily_report.py: any move
  that changes the effective tier is real regardless of driver;
  stamp-driven tier changes get a plain-language assessment cause
  ("our assessment re-rated it / expired") instead of
  bookkeeping_only; "bookkeeping" now requires NO tier consequence.
  Moves carry assessor_driven; _significance caps assessor-driven
  moves at rank 2 (rankable, never ledger-buried). (b) V3 #14:
  _masthead board count + leaders now derive from the shared
  board_membership resolver (api/routers/board.py), own queries
  deleted. Verified read-only against prod DB: DVA 08-17 diff now
  real+assessor_driven with the assessment cause; masthead board=40
  and top-3 ACM/GDDY/LDOS = prod /board exactly. Data quirk seen in
  passing, not touched: CSL 08-18 row has effective tier as the
  STRING 'None' (kind falls to "info") — pre-existing, worth a look.
- 2026-08-19 NAV AMENDMENT (Edmund himself, FIXPACK_2026-08-19
  Session B — amends the "Four nav nouns" line in Done-do-not-touch):
  the nav is now FIVE nouns — The Board / Forces / What changed /
  News Wire / Track record. His words: "For News Wire, we'll have two
  places - alongside Board / Forces / What Changes / News Wire /
  Trace Record" and "I then want a News Wire pane on the right side
  of The Board, just like we have currently for Forces. I think the
  News Wire pane should sit above Forces. It would be a one line
  snipped." Built local-only in Session B (Progress entry below);
  everything else in the do-not-touch list stands unchanged.

## How to build (session discipline)

These are rules, not suggestions. Sessions are disposable; this file is not.

1. One phase per session. The user opens every build session with the
   same fixed sentence — "Read FRONTEND_SPEC.md and continue from the
   Progress section." — and nothing more. The Progress section, not the
   user, says which phase is next; if it is ambiguous or mid-phase, work
   out the state from it and say so before proceeding.
2. **Decisions land in this file, immediately.** Any choice that outlives
   the session — library, endpoint shape, auth approach, design call,
   scope cut — gets written into the relevant section (and Open decisions
   gets resolved/updated) before the session moves on. A decision that
   exists only in chat does not exist.
3. **End-of-session checklist** (do not skip, even mid-phase):
   - Progress section updated with what was actually done and verified
   - any new caveat/gotcha recorded where the NEXT session will see it
   - anything half-finished described precisely enough to resume cold
4. Verify in the browser before any push; the deploy gate applies as usual.
5. **Watch-path proof pending:** isolation is configured but unproven.
   The first web-only push must be followed by a Railway dashboard check —
   if the scheduler service stayed quiet, record it HERE and in CLAUDE.md;
   until then every push counts as a scheduler restart.

## Progress

- [x] Phase 0 (2026-08-10): June-era `api/` + `frontend/` checked for
      salvage (nothing worth keeping — different product: JWT auth,
      watchlists, pre-v2 scoring) and deleted, along with companions
      `start_api.py`, `test_api.py`, `Dockerfile.backend`,
      `docker-compose.yml`, `API_README.md`, `FRONTEND_INTEGRATION.md`.
      New `api/` scaffolded (FastAPI, `api/main.py`, `/health`, reuses
      `db/session.py`; routers mount in Phase 1). New `web/` scaffolded
      (create-next-app: Next.js 16, TS, Tailwind 4, app router; build
      verified). Railway: new `web` service created (root directory
      `web`, watch paths `web/**`); scheduler (`financial-news-platform`)
      and Streamlit (`impartial-heart`) services given watch paths
      `**` + `!web/**` — exclusion, not an allowlist, so scheduler
      redeploys are never silently skipped. Watch-path isolation is
      CONFIGURED but not yet PROVEN by a web-only push — until a
      web-only push is observed to leave the scheduler alone, the
      deploy gate discipline stays as-is (CLAUDE.md rule 5).
      First deploy verified: https://web-production-8b767.up.railway.app
      serves the scaffold (HTTP 200). Committed locally after the Phase 0
      push; rides with the Phase 1 push (no doc-only rebuilds).
      Post-script 2026-08-11: the June prototype's VERCEL project was
      still connected to the GitHub repo and failing on every push
      (emailing the user). The product's home is Railway; user is
      deleting the Vercel project — no code or Railway config involved.
- [x] Phase 1 (2026-08-10): read API for board / stocks / narratives /
      reports, built as ports of the Streamlit pages' queries and merge
      logic (single source of truth preserved: leaderboard_history
      snapshot, never a live re-score). Files: `api/deps.py` (shared
      engine + 10-pt boundary transform), `api/routers/{board,stocks,
      narratives,reports}.py`, mounted in `api/main.py`.
      - `GET /board` — full Hidden-Gems merge: qual layer, narrative-
        override promotions, data-computed disagreement badges (LHX
        rule), first-EVER-appearance NEW flag, tier moves + rank deltas
        vs yesterday's FINAL positions (ACM rule), and `exit_grace`
        (the countdown state: on board but raw score ≤ WATCH — holding
        a hysteresis seat). Returns `board` + `off_board` + counts.
      - `GET /board/scorecard` — track-record lots vs SPY twins
        (pipeline.track_record.get_scorecard passthrough).
      - `GET /stocks/{symbol}` — dossier: snapshot scores, score+band
        history (each history row carries final tier → band-transition
        memory), qual assessment, fundamentals, `annual_history` (10
        annual fundamentals_history rows = triptych raw material),
        earnings calls, 10-K/10-Q, claims, insider decisions (per-
        person-per-day aggregation, entity filers excluded), full price
        series, theme alignments, valuation gaps. 404 if not covered.
      - `GET /narratives` — three-layer JSON: `map` (macros, rollup
        weights, momentum), `what_moved` (salience-ranked, formula
        ported verbatim: weight + 2×ledger-changes-7d + accelerating
        bonus), `library` (full parented tree). Company scope excluded.
      - `GET /reports/latest`, `GET /reports/{date}` — edition grouped
        into masthead / top_story / week_ahead / sections / scoreboard
        + board standings; live race numbers overlaid ONLY on the
        latest edition (stored masthead is the 6am snapshot).
      All endpoints verified locally with uvicorn + curl against the
      live DB (board counts 5/30/12, GDDY dossier full, narratives map
      4 macros, reports latest + archived + 404s). Also removed junk
      Finder duplicate `api/__init__ 2.py`. requirements.txt already
      carries fastapi/uvicorn — no dependency change.
      Pushed 05:02 UTC (deploy gate clear, 58 min before the daily
      slot); scheduler service redeployed and was back scheduling at
      05:00:35 per its logs — verified healthy before the 06:00 run.
      DEPLOYED — the `api` Railway service is live (user did the
      dashboard steps; start command + watch paths were staged BEFORE
      the repo was connected, so the root Procfile never ran):
      - domain: https://api-production-e885.up.railway.app (port 8080)
      - start command: `uvicorn api.main:app --host 0.0.0.0 --port 8080`
        GOTCHA: the PORT is HARDCODED because Railway passes the custom
        start command without shell expansion — `--port $PORT` reached
        uvicorn as the literal string and crash-looped. 8080 must match
        the domain's target port; if the domain is ever regenerated on
        a different port, change the start command to match.
      - watch paths: api/**, pipeline/**, db/**, requirements.txt
      - env: DATABASE_URL, API_CORS_ORIGINS (web prod URL + localhost:3000)
      - root directory `/` (the API imports pipeline/ and db/); never
        add a root railway.json/toml — it would hijack the scheduler
        service's own config (shared repo root).
      Verified on production 2026-08-10: /health ok; /board returns the
      2026-08-09 snapshot (counts 5/30/12, GDDY 5.3 Strong Buy #1);
      /stocks/GDDY, /narratives, /reports/latest, /board/scorecard all
      return correct payloads. Phase 2 (web/) consumes this base URL.
- [x] Phase 2 (2026-08-10): signature view chosen + The Board built.
      Lab route `web/app/signature` (KEPT as the permanent design lab)
      served live variants A/B/C, then refinements B1/B2/C1/C2; user
      picked **C1 (position row) + C2's movement language** for Board
      rows, and **B1 (triptych + band ruler)** as the future Companies
      dossier hero — full decision + locked design tokens recorded in
      DESIGN_BRIEF.md (tier = ordinal blue ramp, validated light+dark;
      up/down and momentum separate roles; momentum orange RESERVED).
      The Board lives at `web/app/page.tsx` + `components/board/
      BoardRow.tsx`, consuming GET /board (prod API): tier-grouped
      sections (news hierarchy), movement cell (NEW / ▲▼ rank / tier
      moves / grace seat), band strip per row, Q·V·G mini-bars,
      off-board summarized to names ≥3.0 + count (full universe was a
      600-symbol wall). Two additions same session (user):
      - rows EXPAND IN PLACE (client component, aria-expanded) to show
        the qualitative call — rationale / bull case / bear case in
        three equal columns (equal weight = honest-surfaces rule),
        unassessed rows say "not yet through the judgment layer";
        "full dossier →" link inside the panel (→ /signature until
        Phase 3, then /companies/[symbol]);
      - the judgment layer's standing adjustment is a BADGE next to the
        tier chip, not a footnote: tinted "▲ judgment raised it" /
        "▼ judgment restrained it" (up/down role), violet "narrative
        promoted" (gap-accent role); the explanatory line ("data alone
        says X") stays under the company name. Nav shell in layout.tsx: five nouns, only The
      Board live. Shared primitives: `components/signature/shared.tsx`
      (TierChip, BandStrip, Sparkline), `evidence.tsx`, `MiniPath.tsx`,
      `CompanySwitcher.tsx` (dossier toggle: dropdown in rank order +
      prev/next — reuse in Phase 3). API client: `web/lib/api.ts`
      (API_URL env, defaults to prod; fetch no-store).
      Verified: light+dark, mobile (responsive ROW_GRID: rank/company/
      tier/score, movement folds under name), hover tooltip on charts,
      `next build` clean. NOT pushed this session — see caveats.
      Caveats for next session:
      - Evidence panes (quality/value/gap) get a DATA PASS in Phase 3
        before shipping on the company page — agreed direction in
        DESIGN_BRIEF.md (margin road + ROIC/FCF chips; P/E AND
        EV/EBITDA vs the NAMED narrative peer set; top narratives with
        trajectory above the gap bar).
      - The "full dossier →" link inside the expanded row points at
        /signature?symbol=X until Phase 3 builds /companies/[symbol];
        repoint it then.
      - Dev server: the preview launcher cannot spawn npm (sandboxed
        cwd, uv_cwd EPERM) — run `npm run dev -- --port 3100` in web/
        via background shell; .claude/launch.json "web" entry is
        url-attach to http://localhost:3100.
      - fundamentals join on the board is by symbol only; company_name
        missing for a few tickers renders blank — cosmetic, revisit.
- [x] Phase 2b (2026-08-10, same session): the NEW FRONT DOOR — the
      Narratives landing per the revised DESIGN_BRIEF.md.
      - api/: `GET /narratives/landing` added (api/routers/
        narratives.py) — forces (macros: thesis, momentum, deduped
        subtree company counts, board count, exposed weight, top board
        stocks), emerging (tier emerging/candidate: age from
        created_at, companies, adds_30d), weakening (LEDGER-derived:
        strengthened/weakened/removed 30d + misses from
        narrative_exposures.misses; included only when net ≤ 0 with
        activity, misses > 0, or status declining — never the momentum
        word). /narratives untouched (regression-checked).
      - web/: The Board moved to `app/board/page.tsx`; landing at
        `app/page.tsx` = four brief sections (forces cards → emerging
        list → losing-support list with down-colored nets and missed
        calls → bridge: top-6 board rows + link). Nav reordered,
        Narratives + The Board live. Momentum orange in use (word
        "accelerating" only). Verified light+dark against the LOCAL
        api (all 9 macros currently read "accelerating" — noise-ish,
        the methodology track's recalibration will fix the input, not
        the display). `next build` clean. Committed locally.
      DEPLOY ORDER CAVEAT: the web landing needs /narratives/landing —
      the api service must deploy BEFORE or WITH the web push (api
      watch paths cover api/**, so one batched push redeploys both;
      that batch also touches scheduler paths → full deploy-gate
      rules, do NOT use it as the watch-path isolation proof).
      Local dev: `venv/bin/python -m uvicorn api.main:app --port 8000`
      then web dev with `API_URL=http://localhost:8000`.
- [~] 2026-08-15 MOCKS FOR REVIEW (PRODUCT_UI_HANDOFF.md analysis —
      decisions NOT yet recorded, user reviewing): review-only routes
      `/home` (Board as landing: masthead search over the universe,
      counts + Book-vs-SPY + edition-count wrinkle visible, TODAY ×3,
      grouped table with Call / Score / Assessor-when-it-moves ("hold
      is silence") / Moved / Story, expanding rows, Forces +
      losing-support rail) and `/companies/[symbol]` (hero with
      tier-domain band strip + STREET line + assessor chip + prev/next,
      evidence triptych with mention-set rule + smallest-n hero gap,
      score components, path + price charts with filing ticks, thesis
      after evidence, calls stack with claims, Stories/Said/Inside
      rail). New helpers: lib/api.ts (Report type, heroGap,
      isMentionSet), BandStrip fixedDomain (tier-scale domain fix),
      components/mock/*. Existing routes moved into app/(site)/ route
      group (URLs unchanged) so mocks carry their own chrome.
      Pending user decisions to record after review: front door
      reversal (Board home vs narratives landing), nav nouns
      ("Track record" vs "Book", "What changed" vs "Edition"),
      movement column kept, per-row band strip dropped.
      NOTE: universe grew to 828 covered / 41 with a call (edition
      2026-08-14); /reports/latest masthead.board=35 wrinkle shown.
      Round 2 (same day, after Grok-sketch feedback + user direction):
      full mock suite, all live data, `next build` clean —
      - /home refined: one-line masthead (tier dots, Book-vs-SPY link
        → /record, wrinkle sentence), TODAY ×3 + "all N moves →",
        filter tabs (All / Strong Buy / Moved / with-a-call),
        name-first rows, Assessor column also prints upgrade/downgrade
        direction words (hold still silence), Forces rail as wt/n
        directory linking /forces/{id}. "Candidates in review" number
        from the sketch NOT built (no sourcing field — no invented
        data).
      - /changed: full newspaper from /reports/{date} — kicker with
        changes_breakdown, date-archive nav, grouped Downgrades →
        Exits → Entries → Upgrades → Also + coverage/birth sections,
        bodies full text, symbols link to /companies.
      - /record: Track record from /board/scorecard — verdict header,
        honesty paragraph ($100 lots, not live capital), AGGREGATED
        per-name rows (invested, open/closed, beating, vs-SPY colored)
        expanding to daily lots vs SPY twins.
      - /forces + /forces/[id]: directory (wt/board/covered + thesis
        clip) and force page = thesis + on-board roster (exposure,
        tier, score) + "attached, not on the board" tail (top 25 by
        exposure — the discovery surface). NEW API endpoint
        GET /narratives/{id}/roster (subtree, deduped, max exposure).
      - Company calls strip: EARN_CALL/10-K/10-Q days as full tabs;
        8-K-only days compress to slim ticks (never hidden — AECOM
        8-K lesson).
      User verdict on the round-2 suite: "This is looking really
      good." — direction approved; execution NOT yet started (user
      instruction 2026-08-15: plan recorded here first, nothing built
      until go).
- [~] 2026-08-15 (build session, same day): ROADMAP STEP 1 DONE +
      READ-LAYER GAP CLOSED IN CODE (addendum items a/b/c — details
      in the addendum block above, rewritten to record what shipped).
      Web-side consumers updated in the same change:
      - /forces/[id] now reads GET /narratives/{id}: THE PULSE chart
        (components/mock/Pulse.tsx — support above / erosion below
        the line in up/down roles, seeding weeks dimmed under a
        labeled "backfill" wash, attached-count under each week, a
        "too short to read as a trend" note while observed weeks < 4,
        NO momentum word anywhere), falsification as "What would
        break it", children as "Inside this force", parent
        breadcrumb, and direction on roster rows ("headwind" in the
        down color; beneficiary stays silent). Forces whose links are
        majority-threatened flip the off-board tail copy: "exposure
        to a headwind is not a candidate list."
      - /companies/[symbol] rail: "Stories" (was legacy
        theme_alignments + gaps mixed) is now "Forces" from
        stock.exposures — plain-words direction ("stands to gain" /
        "adapting to it" / "exposed to the downside"), second-order
        linkage marked, parent named, company-scope narratives set
        apart as "Its own story"; links to /forces/{id}. The peer
        sets moved under their own "Priced against" kicker and link
        by narrative_id. Legacy theme_alignments no longer rendered
        anywhere on the page (two vocabularies on one rail teach the
        reader something untrue).
      Verified: tsc clean, `next build` clean, all 11 routes 200 on
      the local pair (api :8010 / web :3100), sample sweep 32 dossiers
      + 16 force pages clean, /narratives map+landing regression
      unchanged, dark mode + risk-force (id 40) checked in browser.
      NOT deployed; prod api unchanged until step 4.
      Session gotchas for next time:
      - dotenv's find_dotenv asserts inside Bash heredocs — pass the
        path: load_dotenv('/path/.env', override=True), or run a
        script file from the repo root.
      - two stale dev servers (api :8000, next :3100) from the mock
        session were still running and shadowed new code; kill or
        check ports before assuming a route 404s.
- [x] 2026-08-15 (same session, continued): CLAUDE_UI_ADDENDUM.md
      (external localhost review, all ten items) ADOPTED by the user —
      item 4 as written over Claude's objection (UI reconciles edition
      copy against the book; writer-sees-the-book stays a methodology
      item) — recorded as DESIGN_BRIEF laws 15–19 + amendments to laws
      8/12/13, and BUILT:
      - `/` IS The Board (app/page.tsx re-exports home; old (site)
        landing, /board page, and (site) chrome DELETED; /signature
        moved to app/signature as the unlinked lab). Much of roadmap
        step 2's promote work is hereby done; /companies, /forces,
        /changed, /record remain at their mock paths with the mock
        chrome as the real chrome. Still missing from step 2: loading
        / error / 404 states, mobile pass, retiring /home alias.
      - Home: Book line entirely from /board/scorecard (returns, open
        lots, since = min lot_date → "since 27 Jul"); chrome stamped
        with the BOARD date, TODAY stamped "edition {date}" when the
        newspaper lags; "all N moves in the edition →"; Assessor
        column REMOVED (all states dark, incl. direction words);
        Moved = NEW / tier move / grace seat only (rank ticks gone).
      - lib/api.ts: firstLotDate, openLotCounts, reconcileWithBook
        (regex-matched no-position sentence → open-lot fact); applied
        to /changed headlines+bodies and home TODAY. Verified live:
        SANM/FTAI/ENS (3/3/1 lots) replaced, JBL/ARW/POR/PNR/CTRE
        (0 lots) untouched.
      - Company page: Quality pane = DurabilityRoad (user amendment
        same day, superseding the first FY-vs-TTM pair build): per
        metric — ROIC / op margin / FCF margin — up to five fiscal
        years of bars (FY{YY} from period_end) + TTM as the sixth in
        full ink; one shared year axis, per-metric scaling, negative
        values draw below the baseline in the down color; FY FCF
        margin = fcf/rev; null bars omitted (slot stays) — the
        revenue road stays deleted;
        prev/next now a labeled "board neighbours" control above the
        name; assessor hero badge deleted; value copy "cheap against
        this set"; ng_score no longer printed (one gap word);
        Said rail deleted (claims once, in the calls stack);
        CallsStack prints tone/trajectory/strength only when the
        value varies across the company's calls.
      - Pulse: charts OBSERVED weeks only; backfill acknowledged in
        the footnote, never drawn (it would set the scale).
      Verified: build clean; all routes 200 and /board 404; addendum
      verify-triple ACM (Sep-YE) / GDDY (calendar-YE) / EVR (null-TTM
      fcf_margin — cells omitted, no dashes) all render FY | TTM.

- [~] 2026-08-16 (step-3 session): THE THREE MUSTS DONE. Local only —
      NOTHING deployed, prod api/web untouched, Forces still gated on
      the batched push.
      - SWEEP: `scripts/product_smoke_sweep.py` is now the permanent
        pre-deploy smoke test (run against local :8010 this session;
        step 4 runs it against prod). Covers /board, /board/scorecard,
        /narratives(+landing), /narratives/{id}+roster for ALL ids,
        /reports/{date} for ALL dates, /stocks/{symbol} for the full
        universe (828), expected-404 checks, empty-payload and
        null-heavy (>60%) detection — AND the law-17 pass (broad
        negation×position net vs the strict UI regex). Result: zero
        hard failures, zero null-heavy dossiers.
      - LAW-17 all-editions pass: ONE miss found — "Not currently
        held." (2026-08-09, SANM, book holds 3 lots). Fixed with a
        GENERAL pattern (not/currently/presently + held/owned family)
        in web/lib/api.ts NO_POSITION_CLAIM, mirrored verbatim in the
        sweep's STRICT. While generalizing, two FALSE-POSITIVE traps
        were found and guarded: "has not held up/steady/the gains"
        (market prose) and bare "we don't have ..." (now requires a
        position noun). Verified: all 20 strict matches across all 8
        editions are genuine no-position sentences; open-lot ones
        rewrite, zero-lot ones untouched; broad-net gaps now 0; 12
        unit cases incl. traps pass. Also fixed the splice losing its
        leading space ("dominated.The book…") — reconcileWithBook now
        pads + collapses doubles.
      - "11 entrys" in the /changed kicker: pipeline pluralizes kinds
        with a bare "s" (pipeline/daily_report.py — methodology track,
        NOT touched; archive rows store the misspelling anyway). Fixed
        display-side with a general orthography rule, lib/api.ts
        fixPlurals (consonant+"ys"→"ies"; "buys"/"days" untouched).
      - FISCAL TRIPLE re-verified at session end in the browser:
        ACM (Sep-YE) and GDDY (calendar-YE) render FY22–FY25 + TTM on
        all three metrics; EVR renders null cells as omitted bars, no
        dashes (op. margin 1 value, FCF margin 4 + empty TTM slot).
      - tsc clean, `next build` clean, all 9 routes present.
      Gotchas for next session:
      - /board/scorecard triggers an eod_prices INSERT (SPY upsert via
        pipeline.track_record) — a READ endpoint doing a WRITE on
        every call; the remote PG dropped a connection mid-sweep once
        (500, retry fine). Both point at the cache-by-cadence item.
      - Step-3 bullets NOT in the three musts remain OPEN: Streamlit
        cross-check sample, per-page honesty audit, and the two
        discrepancy traces (masthead "since July 23" vs first lot
        Jul 27; masthead.board=35 vs 41 with a call). Do these before
        step 4.
      - Dev pair this session: api :8010, web :3100 with
        API_URL=http://localhost:8010 (web MUST get that env or it
        silently reads prod).

- [x] 2026-08-16 (audit session): THE TWO OPEN STEP-3 ITEMS DONE — local
      only, nothing deployed, nothing pushed. Both items from the
      next-session brief are complete; step 3 is now FULLY done and
      step 4 (deploy, user present) is the next session.
      - (a) STREAMLIT CROSS-CHECK — PASSED, ZERO MISMATCHES. Same DB,
        local pair (api :8010 / web :3100) vs the running lab bench
        (:8601). Sample per the brief: ACM (top rank), MLI (off-board;
        no grace seats existed on the 2026-08-15 board, so off-board
        fills that slot), EVR (null-TTM fcf_margin). Verified equal at
        all three levels: board rows (score, tier, all four components
        — fmt10(raw leaderboard_history values) reproduces the API
        numbers exactly: ACM 0.5186→5.2, EVR 0.3810→3.8, MLI
        0.3376→3.4), header counts (3/30/8/41/0/828 both sides),
        scorecard (+3.28% vs +1.80%, 36/59, 56 open · 3 closed,
        $5,900, first lot Jul 27 — identical), and full dossiers
        (Stock Detail vs /stocks/{sym}: every fundamentals field,
        latest-call date/strength/tone/trajectory, valuation gaps
        incl. Defence 0.72·63 peers 9.8x-vs-22.6x). No port bugs.
        Lab-bench observations (NOT touched, methodology track's to
        take or leave): the sidebar checkbox label "Show full
        universe (all 498)" is a HARDCODED stale string (data is
        828); Stock Detail renders EVR's null fcf_margin as an
        em-dash (allowed on the lab bench; the product omits it).
      - (b) HONESTY AUDIT vs the 19 laws — ALL PASS, zero violations.
        Home: since 27 Jul (derived; July 23 nowhere), wrinkle
        sentence "the edition counts 35; 41 carry a call" visible,
        no Assessor column/badges/direction words (the one "upgrade"
        string on the page is inside an edition story body about
        utility rate cases — prose, not chrome), hold fully silent,
        both clocks stamped (board 2026-08-15 · edition 14 Aug),
        TODAY = 3 cards + "all 10 moves" where 10 = masthead.changes
        (sourced), Moved column silent for unmoved rows, no rank
        ticks. What changed: ALL 8 archived editions audited; law-17
        reconciliation verified on the two stored open-lot claims
        (ENS 2026-08-12 "We do not hold a position." → "The book
        holds 1 open $100 lot"; SANM 2026-08-09 "Not currently
        held." → 3 lots) and all zero-lot claims left verbatim;
        fixPlurals renders "11 entries"/"3 entries" on the two
        stored-typo dates (08-09, 08-07); no Assessor anywhere.
        Track record: first lot 2026-07-27 printed, honesty
        paragraph above the numbers, aggregated per-name rows,
        losses at full weight (ACM −8.60% plain), 56 open · 3 closed
        from the scorecard (masthead.closed=16 not used). Forces:
        checked 9 (Defence) + 40 (risk force) — no momentum word,
        backfill acknowledged never drawn, "too short to read as a
        trend" note at 2 observed weeks, "What would break it"
        present, headwind labels + "not a candidate list" flip on
        the risk force. Companies (fiscal triple): durability road
        FY…TTM on all three; EVR null bars omitted (empty slots, no
        dashes); mention-set label exactly on n≥100 sets (ACM 120,
        137) and absent on smaller (63, 43); hero gap = smallest-n
        set (ACM: 63-peer Defence); Street labeled; "board
        neighbours" control; no ng_score, no Said rail, no judgment
        badges; BandStrip gets fixedDomain=TIER_DOMAIN in
        companies/[symbol]/page.tsx.
      Out-of-scope items honored: law-17 regex untouched, 35-vs-41
      not diagnosed, pipeline/daily_report.py untouched, Forces not
      promoted/pushed. NEXT SESSION = ROADMAP STEP 4 (deploy, user
      at the Railway dashboard; the batched api+web push carrying
      the scorecard write-on-read fix and GET /narratives/{id}).

- [x] 2026-08-16 (deploy session): ROADMAP STEP 4 DONE — the batched
      api/ + web/ push is LIVE on prod. Also two findings that outrank
      the deploy, below.
      - ARE PORT BUG actually FIXED this session (the audit session
        had recorded it but never made the code change): annual_history
        now reads canonical `fundamentals_annual` (fiscal_year AS
        period_end). Verified: ARE renders six FY FCF-margin bars incl.
        2021 at −300% below the baseline; fiscal triple (ACM/GDDY/EVR)
        still passes — EVR's op-margin row now shows all five FYs
        (legacy table's holes are gone).
      - ZOMBIE LOCAL SCHEDULERS FOUND AND KILLED (user sign-off): TWO
        launchd jobs on the Mac (com.finresearch.scheduler +
        com.finews.scheduler, KeepAlive+RunAtLoad) were running the
        LEGACY `scheduler.py` against the PRODUCTION DB — one for 5.7
        days — firing the retired cron set (06:00 daily, 13:00 midday,
        21:00, Sun 18:00) whenever the Mac was awake, and REPLAYING
        slept-through runs on wake. Caught mid-write: on 2026-08-16
        ~10:00 SGT one replayed a stale daily run and archived a
        2026-08-16 board snapshot (45 on-board) 4h before Railway's
        real daily. Both jobs bootout'd, plists renamed *.disabled in
        ~/Library/LaunchAgents, zero scheduler processes remain, no
        crontab. Possibly relevant to past data wrinkles (35-vs-41 NOT
        diagnosed — out of scope per user).
      - KEY CLARIFICATION: Railway's Procfile runs `scheduler_light.py`
        — NOT `scheduler.py`, which is legacy and now runs NOWHERE.
        Its step-3d NameError (sqlalchemy `text` never imported; every
        local daily run's synopsis step failed) was fixed anyway
        (one-line import) with user sign-off; Railway was never
        affected (scheduler_light imports correctly). Whether to
        DELETE scheduler.py + the untracked pre-Railway files
        (AUTOMATION_SETUP.md, run_pipeline.py, plist, logs…) is a
        methodology-track cleanup decision — not taken here.
      - THE DEPLOY (02:5x UTC, gate clear, ~3h before the 06:00 slot,
        user at the Railway dashboard): 15 commits, one batched push —
        everything since f6ea01b incl. the scorecard write-on-read
        fix, GET /narratives/{id} (+roster), the promoted routes, and
        both fixes above. New api live after ~100s, web after ~2 min.
        PROD SMOKE SWEEP PASSED: 828 dossiers, 0 hard failures, 0
        null-heavy, law-17 5 expected strict hits / 0 gaps, expected
        404s correct. Browser-verified on prod: `/` is The Board
        (masthead, wrinkle sentence, Book vs SPY since 27 Jul),
        /companies/ARE (fix live), /forces/9 (pulse, "What would
        break it" — Forces' first time live, its api gate satisfied),
        /changed (law-17 rewrite visible on SANM 3-lots; JBL zero-lot
        untouched), /record (honesty paragraph, ACM −8.60% full
        weight). First prod paint of `/` once showed unstyled column
        (transient stream paint; fine on reload, css 200) — watch it.
      - API_URL env on the web service: NOT set — web/lib/api.ts
        defaults to the prod api URL, which is correct in prod; the
        env exists for local dev (decision recorded, step-4 item
        closed).
      - Watch-path isolation STILL UNPROVEN (this push touched
        scheduler paths by design). The proof push (pure web/**, quiet
        day, dashboard check) remains TODO.
      - Sweep hardened: a failed /board fetch now reports instead of
        crashing the script.
      - STILL OPEN from step 2: loading/error/404 states, mobile pass,
        retiring the /home alias (route still answers).
      NEXT: roadmap item 5 — each its own session: Pair page (still
      BLOCKED on methodology data), Portfolio + auth, full review pass
      vs DESIGN_BRIEF.md, product name. Plus the isolation-proof push.

- [x] 2026-08-16 (roster-definition session, external review directive;
      LOCAL ONLY, not pushed): **"on the board" now has ONE definition.**
      The force-page roster classified membership with a bare
      COALESCE(assessed_tier, tier) while /board's merge (override →
      qual-with-raw-floor-guard → raw) is what readers see — so
      INTU/PCG/EIX showed "on the board" on force pages while absent
      from /board, INTU wearing "Buy" at a Watch-range score. Fix is
      the pattern, not the names: board.py now has `_resolve_tier`
      (THE single tier+score resolver — get_board itself uses it, so
      the definitions cannot drift) and `board_membership(conn)`
      (the shared set); the roster's snap IS that set; off-board
      attached names carry NO tier/score badge. VERIFIED on three
      forces (big: 1 AI Infrastructure — 28 on board, ghosts gone to
      off-board; mid: 11 Data Centre REIT — 16; risk: 40 IT Services
      Federal — 6): every on_board symbol ∈ /board's 38, every
      tier/score field-identical to /board, zero off-board badges.
      Session gotcha confirmed AGAIN: a stale api server on :8010
      from a prior session served old code and faked a failed verify —
      kill ports before trusting a localhost check.
      METHODOLOGY OBSERVATION handed over (V3 #13): the board's
      raw-floor guard silently drops corridor-held tiers whose raw
      score sits below the Watch floor (that is WHY INTU's held Buy
      exists in the DB but not on /board) — corridor-vs-guard
      precedence needs a deliberate decision, not this session's.

- [x] 2026-08-19 (FIXPACK Session B): NEWS WIRE built — LOCAL ONLY,
      NOT pushed; prod still has four nouns and no /wire until the
      next Edmund-at-Railway window.
      - api/: NEW api/routers/wire.py — GET /wire + GET /wire/{date}
        (archive nav dates list included, /reports pattern). Read-only
        port of Streamlit's load_filings_intelligence ONLY (B1 scope:
        narrative filings strength ≥0.60 or shift ≥0.12 last 14d +
        8-Ks |sentiment| ≥2 last 7d, merged, cap 14; NO leaderboard
        moves, NO insiders). Synopses come ONLY from the stored
        llm_analysis cache — the endpoint NEVER generates one (read
        endpoints never write; zero INSERT/UPDATE in the file, code
        path checked). signal crosses at ten(); board tier/score chips
        resolve through pipeline.board_membership — live for /wire,
        as_of=the requested date for /wire/{date} (the A2 lesson: a
        dated page never wears today's board).
      - web/: Chrome nav is FIVE nouns in the decided order (every
        page picks it up from the one NAV constant). New /wire page:
        dated masthead + date archive like /changed, items with type
        label / observed date / company / headline / stored synopsis /
        plain-word signals ("story strength 9.2 / 10", "story
        accelerating", "management confident", "read as positive" in
        up/down colors), board tier chip only for on-board names —
        nulls omitted throughout, assessor untouched (dark). Items
        carry #f{id} anchors. /home right rail: News Wire pane ABOVE
        Forces (B2b): ≤5 lines newest-first, SYMBOL · short company
        (≤18 chars, word-boundary crop) — headline snippet (cropped at
        word boundaries via cropWords, never rewritten) · compact date;
        no scores/tiers in the rail; each line links /wire#f{id}.
      - VERIFIED on the local pair (stale :8010/:3100 killed first;
        api :8010, web :3100 with API_URL): tsc + `next build` clean
        (/wire in the route list); five nouns render on every page;
        /wire and /wire?date=2026-08-14 both render with their own
        dates; rail shows 5 word-boundary-cropped lines above Forces
        and #f22893 click-through lands on the FN item (browser
        check). PARITY PROVEN: the Streamlit loader run verbatim
        against the same DB returns the IDENTICAL 14-item id set as
        GET /wire, every compared field equal (symbol, type, date,
        strength→signal ×10, trajectory, tone) — mismatches zero.
      - Recorded: nav amendment in the STANDING BRIEF dated updates +
        Open decisions (RESOLVED) + DESIGN_BRIEF Navigation section.
      - NOT done here: no push, no deploy — prod api has no /wire and
        prod web still shows four nouns until the next approved push.
- [x] 2026-08-20 (V3 #13 session, Edmund's ruling): PRODUCT BOARD NOW
      HONOURS METHODOLOGY SEATS — LOCAL ONLY, NOT pushed; prod still
      discards grace seats and corridor holds until the next
      Edmund-at-Railway window.
      - Ruling: seat wins above the exit line (0.32); the guard only
        kills below it. Change lives ONLY in
        pipeline/board_membership.py (resolver rides the stored
        snapshot tier, hard kill below BOARD_EXIT; both twins);
        daily_report's two effective_tier call sites pass the stored
        tier + gem (plumbing only). No product surface re-implements
        the merge — /board, force rosters, wire chips, masthead all
        inherit. Full evidence + mandatory offline diff:
        V3_13_PRECEDENCE_SPEC.md; freeze entry: V2_CONSIDERATIONS.md.
      - Verified locally against the live DB (stale :8010 killed):
        /board 44 -> 46 (+CSL Watch 3.4, +ADBE Watch 3.2, both
        exit_grace=true), zero removals, non-flipped entries
        byte-identical (rank fields aside — none shifted); vetoed
        names (FN/PCG/NOC) and below-exit INTU stay off; force
        rosters obey the shared-set law (big force AI-Infra + mid
        force Defence checked; CSL on force 2, ADBE on force 35);
        masthead board=46 == membership == /board; v2d lot logic
        reads snapshot columns directly — inputs untouched, no
        grace/hold row reads Strong Buy in the last 8 snapshots, lot
        behaviour unchanged. Streamlit untouched (git status).
      - Known cosmetic gap (out of scope, consumer-side): the two
        grace entries show assessed=false on /board because board.py's
        DECORATION branch still gates on tier_for(gem) — tier and
        score are correct; rationale/direction chips absent for
        grace-seated names until a product-track session updates the
        decoration condition to ride the seat.
      - 35-vs-38 wrinkle: NOT closed yet — expected to close on
        deploy, but per the ruling it must be RE-MEASURED on prod
        (Streamlit count vs product /board count) at the next push
        window and the outcome recorded here honestly.
      - platform_notes row inserted (active 2026-08-20 → 08-25):
        board display now honours corridor holds and grace seats
        above the exit line; reappearances are not company news.

## THE AGREED ROADMAP (2026-08-15 — supersedes Phases 3–5 below)

The product's page architecture is now the mock suite: home (Board) ·
Forces · What changed · Track record · /companies/[symbol]. The mock
routes at /home, /forces, /forces/[id], /changed, /record,
/companies/[symbol] plus components/mock/* ARE the design of record —
promote them, do not rebuild them. Steps, in order; 1–3 are local;
4 needs the user at the Railway dashboard. NONE STARTED YET.

**REVIEW ADDENDUM (2026-08-16, methodology session + external review,
both concur — these BLOCK step 2):**
- **READ-LAYER GAP — CLOSED IN CODE 2026-08-15 (this session), NOT
  YET DEPLOYED** (prod still serves the old 8 paths until the step-4
  push). What was built, all verified locally against the live DB:
  (a) GET /narratives/{id} — thesis + falsification, parent/children
      (with per-child roster counts), board_weight, the roster, and
      the HEALTH SERIES from narrative_health_history. Honesty rules
      in the payload itself: momentum_state is NOT returned (shadow
      column until NARRATIVE_SPEC Phase 2 passes its gate) and every
      week carries its `seeding` flag so surfaces must distinguish
      backfill from observation. /narratives/{id}/roster kept.
      Roster rows now carry `direction` (a force can be a headwind;
      a roster hiding "threatened" reads as a recommendation).
      Perf note: child rosters computed from ONE links query (the
      per-child version cost ~4.3s/page against remote PG; now ~1.6s,
      which is DB round-trip latency — the cache-by-cadence item
      remains the real fix).
  (b) /stocks/{symbol} returns `exposures` keyed by narrative_id
      (exposure, direction, linkage, status, misses, decays, dates,
      parent) from narrative_exposures.
  (c) BONUS, verified in code + data: theme_valuation_gaps.
      meta_theme_id is a LEGACY COLUMN NAME that actually holds a
      narrative_id (pipeline/theme_valuation_gap.py writes it from
      narrative_exposures; all 15 distinct id/name pairs match
      narratives, none match meta_themes). The API now exposes it as
      valuation_gaps[].narrative_id — so the value peer sets were
      never name-matched, and the company rail links them to
      /forces/{id} by id. stock_theme_alignment remains genuinely
      meta-themes (legacy); the company page no longer renders it.
- **ASSESSOR BADGE BLOCKED pending provenance**: since 2026-08-15 the
  materiality corridor also writes assessed_tier (corridor-pending
  and materiality-hold states) — the "▲ judgment raised it" badge
  would mislabel them. Methodology track must stamp provenance
  alongside assessed_tier (judge / corridor_pending / materiality_hold
  — V3 item); the badge ships only after it can tell them apart.
- **Cache by cadence**: data changes twice a day; responses are
  immutable between snapshots. Add response caching keyed to the
  snapshot/edition date before any external user (P-C at latest).
- **One since-date**: Track record and masthead both say "since
  Jul 27, 2026" (the first lot); Jul 23 is the signal start and may
  appear only as a footnote. (The board=35-vs-41 wrinkle remains a
  methodology-track question; keep it visible.)

1. **Lock decisions in DESIGN_BRIEF.md** — DONE 2026-08-15 (this
   session). The brief now carries: nav DECIDED (four nouns, Board is
   home, Companies via search not nav, Portfolio joins when it
   exists); the page architecture (mock suite = design of record); and
   fourteen numbered SURFACE LAWS (hold-is-silence, STREET labeled,
   mention-set + smallest-n, tier-domain band strip, no unsourced
   numbers, nulls omitted, movement on the row, aggregated track
   record, 8-K ticks, momentum orange re-reserved, assessor badge
   dark until provenance, one since-date, wrinkles visible). The old
   landing section is kept marked SUPERSEDED; its ledger-derived
   weakness rule survives. Signature-view section amended: board row
   drops band strip + mini-bars (law 8); B1 hero and evidence panes
   marked BUILT; FCF chips noted absent (no field — law 5).
2. **Promote mocks → real routes**: /home → `/`; mock Chrome becomes
   the site chrome; retire app/(site)/ (old landing, /board,
   /signature page — keep the signature components; lab route may stay
   unlinked). Add the states mocks skipped: loading, error, 404,
   mobile pass, dark-mode pass.
   TWO HARD GATES INSIDE THIS STEP (do not promote around them):
   - The raised/restrained ASSESSOR BADGES ship DARK (not rendered).
     The mocks paint every assessed-vs-raw gap as judge conviction,
     but assessed_tier is also written by the materiality corridor —
     rendering the badge before provenance (V3 #11) ships the exact
     mislabel we're blocking. Dark until provenance is stamped AND
     exposed via /board.
   - The Forces directory and /forces/[id] pages DO NOT go live until
     GET /narratives/{id} (+ roster) is deployed and verified on prod
     — the endpoint now EXISTS in code (2026-08-15) and the force
     page consumes it (pulse chart, children, headwind labels), so
     this gate is now only about the api/ deploy landing before or
     with the web push (same batched-push rule as Phase 2b).
3. **Data-accuracy pass** (before any deploy):
   THREE MUSTS for this session (2026-08-16, Grok + Claude concur —
   do not skip, do not add anything else to the session)
   — ALL THREE DONE 2026-08-16, see the step-3 Progress entry; the
   unstarred bullets below (Streamlit cross-check, honesty audit,
   discrepancy traces) remain open:
   **NEXT SESSION BRIEF — COMPLETED 2026-08-16 (audit session): both
   items done, all pass, zero mismatches / zero law violations — see
   the 2026-08-16 audit-session Progress entry. Step 3 is FULLY done;
   next session is step 4. (Brief kept below for history.)**
   **(external review 2026-08-16 — LOCAL ONLY, no
   push, no deploy; the three musts are accepted as done, do not
   reopen them). Scope to the two open items, then STOP:**
   (a) **Streamlit cross-check** (same DB): sample must include a
       top-rank name, a grace-seat/off-board name, and a null-heavy
       name; product and Streamlit must show the SAME numbers; any
       mismatch is a PORT BUG, not a one-ticker fix; do not change
       Streamlit.
       **PRE-FOUND PORT BUG (user caught it on ARE, 2026-08-16; root
       cause verified — fix it as part of this item):** the API's
       `annual_history` reads LEGACY `fundamentals_history`, where
       fcf is NULL in 799/3,933 annual rows (ARE: all years) and roic
       values DIFFER from canonical (ARE 2025: −5.1% legacy vs −3.7%
       canonical) — the durability road was lawfully omitting bars
       fed from a holey, differently-defined table. FIX: switch the
       annual_history query (api/routers/stocks.py ~line 70) to
       canonical `fundamentals_annual` (fiscal_year AS period_end;
       same column shape). VERIFY: ARE renders six FY FCF-margin bars
       including 2021 NEGATIVE below the baseline; the fiscal triple
       still passes; cross-check numbers then match Streamlit by
       construction (both canonical).
   (b) **Per-page honesty audit vs the 19 laws**: The Board, What
       changed (EVERY archived edition date), Track record, one
       force page, three company pages (Sep-YE / calendar-YE /
       null-TTM). Confirm: no unsourced number; nulls omitted not
       dashed; mention-set labeled; hold silent; assessor fully
       dark; TODAY's count equals TODAY's cards; one clock;
       since-date = min(scorecard.lots[].lot_date); 35-vs-41
       wrinkle visible.
   OUT OF SCOPE for that session (external review, binding): do NOT
   widen the law-17 regex again — a missed phrasing gets RECORDED
   here and left (V3 #12 is the durable fix); do NOT diagnose
   35-vs-41 (the why is methodology's); do NOT touch
   pipeline/daily_report.py; do NOT promote or push Forces
   (GET /narratives/{id} still local). End of session: record the
   Streamlit sample results + audit findings here, commit locally,
   do not push, do not start step 4.
   **SCORECARD WRITE-ON-READ: FIXED 2026-08-16, methodology track,
   same day it was reported (the ENS rule — agreed fixes get built,
   not logged).** GET /board/scorecard was upserting eod_prices via
   _ensure_benchmark_prices on every call — it 500'd mid-sweep and
   would have written production on every Track-record pageview.
   get_scorecard is now PURE READ (verified: no fetch, no write,
   ~0.9s warm); SPY benchmark freshness moved into the scheduler's
   price steps (daily step 1 AND after-close step 1). Committed
   locally; MUST ride the step-4 batched push — step 4 stays blocked
   until this deploys.
   - the 828 sweep PLUS a law-17 honesty pass over EVERY edition date
     in the archive — the reconciliation regex will fail on phrasings
     it hasn't seen; any miss gets a GENERAL pattern fix, never a
     one-name patch (both the regex belt and V3 #12's writer fix stay
     until the writer ships);
   - re-verify the Quality durability road on the fiscal triple after
     any further changes: a Sep year-end (ACM), a calendar year-end
     (GDDY), and a null-TTM field (EVR) — the triple that already
     passed must still pass at session end;
   - Forces pages stay behind the batched api+web push — GET
     /narratives/{id} is still local-only; do not soft-launch them.
   - automated sweep: script hits every endpoint + /stocks/{symbol}
     for all ~828 names; catches 500s / empty payloads / null-heavy
     pages. Becomes the permanent pre-deploy smoke test.
   - cross-check vs Streamlit lab bench (same DB): sample of names
     (top rank, grace seat, off-board, null-heavy) must show the same
     numbers on product and Streamlit pages. Mismatch = port bug.
   - honesty audit per page: no unsourced number, mention-set labels,
     hold silent, nulls omitted (no em-dashes).
   - trace two open discrepancies (diagnose, don't paper over):
     masthead "since July 23" vs earliest scorecard lot 27 Jul; and
     edition masthead.board=35 vs 41 snapshot rows with a call (the
     wrinkle stays visible either way; the WHY belongs to the
     methodology track).
4. **Deploy** — DONE 2026-08-16, see the deploy-session Progress
   entry (prod smoke passed; isolation proof still pending):
   (user present): one batched api/ + web/ push in a clean
   deploy-gate window — touches scheduler watch paths, so full gate
   rules; user watches Railway dashboard. Set API_URL env on the web
   service. Prod smoke test (the step-3 script against prod). The
   watch-path isolation PROOF still requires a separate pure web/**
   push on a quiet day — this batched push cannot be it.
5. **After that, each its own session**: Pair page (BLOCKED on a real
   meta_themes ↔ narratives linkage — methodology-track data work, no
   name-matching hacks); Portfolio + auth decision (old Phase 7);
   full review pass vs DESIGN_BRIEF.md (old Phase 8); product name
   before anything public.

- [x] ~~Phase 3: Companies workbench~~ SUPERSEDED — built as the
      /companies/[symbol] mock (roadmap step 2 promotes it)
- [x] ~~Phase 4: Narratives landing as front door~~ SUPERSEDED —
      front-door decision reversed 2026-08-15; the narratives work
      lives on as the Forces directory + force pages
- [x] ~~Phase 5: What Changed~~ SUPERSEDED — built as /changed mock
- [ ] Phase 6: read API remainder; anything the promoted pages still
      need (roster endpoint shipped; Pair blocked, see roadmap 5)
- [ ] Phase 7: auth decision + Portfolio (owner-only; mutations)
- [ ] Phase 8: single-user product complete — full review pass vs
      DESIGN_BRIEF.md; Streamlit stays (lab bench, permanent)

Product-track phases (other people using it — sequenced after 8, each
needs user sign-off to start):
- [ ] P-A: legal/compliance framing — impersonal research publication,
      not personalised advice; disclaimers; product name/masthead
- [ ] P-B: data licensing check — FMP/Yahoo redistribution terms for
      displaying derived metrics to third parties (BLOCKER for any
      external user; verify before anyone but the owner has access)
- [ ] P-C: accounts — multi-user auth, product tables (users/sessions),
      owner vs visitor roles; Portfolio becomes per-user or owner-only
- [ ] P-D: public track record page — the twin comparison as the
      product's proof, wins and losses unconditionally
- [ ] P-E: onboarding/education — methodology explained in plain words
      (what the lens is, what the bands mean, what the twin is)
