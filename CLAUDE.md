# Platform operating rules (for Claude)

## Deploy safety (user directive 2026-08-09 — the Saturday lesson)
Pushes restart Railway services and KILL live scheduler runs. Rules:
1. NEVER push during a scheduler slot or within 10 min of one:
   - daily:       06:00 UTC (~50 min) — 2pm Singapore — EVERY day
   - midday:      13:00 UTC (~5 min)  — Mon-Fri
   - after-close: 21:00 UTC (~30 min) — Mon-Fri
   - weekly:      22:00 UTC Friday (~60 min) — 6am Saturday Singapore
2. The pre-push gate (.githooks/pre-push -> scripts/deploy_gate.py)
   enforces this mechanically. DEPLOY_ANYWAY=1 only for emergencies.
3. Batch pushes; two rebuilds back-to-back once broke the live site.
4. Dead-run rescue exists (scheduler catch-up, 20h window) as backstop —
   it repairs damage, it does not license causing it.
5. Railway watch paths (once set): scheduler service redeploys only on
   pipeline/scheduler/requirements changes; UI-only pushes touch only the
   web service. Until confirmed set, treat EVERY push as a scheduler restart.

## Other standing rules
- Scoring changes: freeze discipline — explicit user sign-off, log in
  V2_CONSIDERATIONS.md. Offline before/after board diff ritual for big ones.
- Methodology changes visible to the assessor: add a platform_notes row
  with an active window (never let it narrate our changes as company news).
- User-facing surfaces: plain lexicon, 10-point scores, no internal jargon.
- The portfolio-tracker folder on Desktop and its Firebase are READ-ONLY.
