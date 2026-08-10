# Platform operating rules (for Claude)

## Deploy safety (user directive 2026-08-09 — the Saturday lesson)
Pushes restart Railway services and KILL live scheduler runs. Rules:
1. NEVER push during a scheduler slot or within 10 min of one:
   - daily:       06:00 UTC (~50 min) — 2pm Singapore — EVERY day
   - after-close: 22:00 UTC (~40 min) — Mon-Fri — 6am SGT; generates the
     session report edition at its end
   - weekly:      23:30 UTC Friday (~60 min) — 7:30am Saturday Singapore;
     regenerates Friday's edition with weekly results
   (midday run retired 2026-08-09 — it fired pre-open and produced noise)
2. The pre-push gate (.githooks/pre-push -> scripts/deploy_gate.py)
   enforces this mechanically. DEPLOY_ANYWAY=1 only for emergencies.
3. Batch pushes; two rebuilds back-to-back once broke the live site.
4. Dead-run rescue exists (scheduler catch-up, 20h window) as backstop —
   it repairs damage, it does not license causing it.
5. Railway watch paths (once set): scheduler service redeploys only on
   pipeline/scheduler/requirements changes; UI-only pushes touch only the
   web service. Until confirmed set, treat EVERY push as a scheduler restart.

## Frontend v2 (api/ + web/)
- ALL frontend work is governed by FRONTEND_SPEC.md. Read it BEFORE
  touching api/, web/, or anything frontend-related — even for a "quick
  fix". Its Progress section is the state; the previous chat is not.
- Every decision and every phase completion is written into
  FRONTEND_SPEC.md before the session ends. A decision that exists only
  in chat does not exist.
- Watch-path isolation (web-only pushes skipping the scheduler) is
  CONFIGURED but NOT YET PROVEN. Until a web-only push is observed
  leaving the scheduler service untouched — then recorded here — every
  push counts as a scheduler restart and full deploy-gate rules apply.

## Other standing rules
- Scoring changes: freeze discipline — explicit user sign-off, log in
  V2_CONSIDERATIONS.md. Offline before/after board diff ritual for big ones.
- Methodology changes visible to the assessor: add a platform_notes row
  with an active window (never let it narrate our changes as company news).
- User-facing surfaces: plain lexicon, 10-point scores, no internal jargon.
- The portfolio-tracker folder on Desktop and its Firebase are READ-ONLY.
