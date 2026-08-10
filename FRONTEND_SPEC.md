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

## Page build order (revised 2026-08-10 per DESIGN_BRIEF.md)

Nav is five nouns: The Board / Companies / Narratives / What Changed /
Portfolio. Events, insiders, and news dissolve into Companies and What
Changed — they are not pages.

1. **Signature view + The Board** — the design centerpiece first (2–3
   live variants, user picks, tokens locked into DESIGN_BRIEF.md), then
   the Board built as that view collapsed to a row per stock. Front door.
2. **Companies** — the workbench dossier: signature view, band history,
   assessment, triptych, events/insiders/filings in context.
3. **What Changed** — the daily edition as instrument log.
4. **Narratives** — port the three-layer map.
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
- [ ] Phase 1: read API — board, stocks, narratives, reports
- [ ] Phase 2: signature view (2–3 live variants → user picks → tokens
      locked in DESIGN_BRIEF.md) + The Board page
- [ ] Phase 3: Companies workbench (dossier + events/insiders/filings)
- [ ] Phase 4: What Changed (daily edition as instrument log)
- [ ] Phase 5: Narratives (port three-layer map)
- [ ] Phase 6: read API remainder; anything the pages still need
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
