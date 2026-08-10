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
- **Streamlit stays live and untouched until parity.** Cutover page by
  page; kill `ui/` only when nothing links to it.

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

## API surface (build in this order)

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

## Page migration order (value-first)

1. **Home / Report** — the daily edition is the product's face. The report
   page's editorial language (masthead, board-leaders strip, week grid) is
   the design north star for everything else.
2. **Hidden Gems board** — sortable, filterable, countdown chips.
3. **Stock Detail** — the dossier; richest interactivity win over Streamlit.
4. **Narrative Map** — three layers, just rebuilt in Streamlit; port design.
5. **Portfolio** — last of the big pages because it has mutations + auth.
6. Events / Insiders / News Wire — small, fold in as capacity allows.

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
- [ ] Phase 1: read API — board, stocks, narratives, reports
- [ ] Phase 2: Home/Report page
- [ ] Phase 3: Hidden Gems board
- [ ] Phase 4: Stock Detail
- [ ] Phase 5: Narrative Map
- [ ] Phase 6: read API remainder + Events/Insiders/News
- [ ] Phase 7: auth decision + Portfolio (incl. mutations)
- [ ] Phase 8: parity check, cutover, retire ui/
