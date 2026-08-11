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

## Two tracks (user directive 2026-08-10)
The platform is now TWO projects with a hard boundary:
- METHODOLOGY track: pipeline/, scheduler, Streamlit ui/, scoring,
  assessor, narratives. Streamlit is the permanent internal lab bench —
  it is NOT retired when the product reaches parity.
- PRODUCT track: api/ + web/ — a product for OTHER PEOPLE to use,
  governed by FRONTEND_SPEC.md + DESIGN_BRIEF.md.
Boundary, absolute in both directions: product work never modifies
pipeline, scoring, scheduler, Streamlit, or platform DB tables (reads
via api/ only; product state like users/auth lives in NEW tables).
And no methodology decision is ever made to please product users —
the instrument's honesty IS the product.

## Frontend v2 — the PRODUCT track (api/ + web/)
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

## Evidence integrity (user directive 2026-08-11 — the AECOM lesson)
A $337M charge was adjudicated as "noise" by an assessor that was told an
8-K existed but never shown its content; a wrong-quarter transcript was
then hand-inserted under a guessed label. Both were integrity failures.
Rules, absolute:
1. JUDGMENT SURFACES SEE THEIR EVIDENCE. Any LLM that renders a verdict
   (assessor, report writer, judges) must receive the CONTENT of the
   events it is judging, not a notification that they happened. When
   adding a trigger, add its payload to the context in the same change.
2. THE MACHINERY DOES THE ASSESSING — NEVER CLAUDE. When an assessment
   is wrong or stale, fix the inputs/context and RE-RUN the platform's
   assessor. Never hand-write, steer, or "correct" an assessment
   narrative directly, and never tell the assessor what conclusion the
   user or Claude expects. (Recurring failure mode — user has caught
   it more than once.)
3. NO DATA UNDER GUESSED LABELS. Before inserting any externally
   fetched artifact (transcript, filing, price), verify the content
   IS what the label claims (check dates/quarter/entity inside the
   document). A mislabeled row poisons every downstream judgment
   silently. Vendor quarter conventions differ — verify, never assume.
4. NEVER CLAIM A MODEL SAW SOMETHING WITHOUT CHECKING. "Assessed with
   X in context" may only be said after confirming the context builder
   actually includes X. Trace the code path, don't infer it.

## Narrative system (the living-narratives build)
ALL narrative-system work (momentum, vital signs, amendments,
checkpoint minting, lifecycle) is governed by NARRATIVE_SPEC.md — read
it BEFORE touching any of it. Its Progress section is the state.
Shadow-first is absolute: no live narrative field changes without the
spec's acceptance criteria met and user sign-off recorded there.

## Other standing rules
- Scoring changes: freeze discipline — explicit user sign-off, log in
  V2_CONSIDERATIONS.md. Offline before/after board diff ritual for big ones.
- Methodology changes visible to the assessor: add a platform_notes row
  with an active window (never let it narrate our changes as company news).
- User-facing surfaces: plain lexicon, 10-point scores, no internal jargon.
- The portfolio-tracker folder on Desktop and its Firebase are READ-ONLY.
