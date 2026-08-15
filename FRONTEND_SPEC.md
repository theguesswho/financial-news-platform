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
4. **Deploy** (user present): one batched api/ + web/ push in a clean
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
