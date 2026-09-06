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

## Standing alignment brief (user directive 2026-08-16 — EVERY session)
The full brief lives in FRONTEND_SPEC.md ("STANDING BRIEF") — it
replaces all one-off session notes and is read at session start; do
not reopen closed items to be helpful. The push rules bind EVERY
session, both tracks:
1. No push, no deploy, no `git push` unless Edmund has JUST said to
   AND is at the Railway dashboard. One-off approvals never carry over.
2. If a step needs Edmund, ask BEFORE the action, in one exact
   sentence: what to open, what "healthy" looks like, what to reply.
   Never ask him to "check Railway" after the fact; never write as if
   he already did something.
3. Prefer the Railway CLI yourself; ping him only when the CLI cannot
   answer.
4. Local verifies: kill stale :8010/:3100 first; `/health` 200 is not
   proof — hit `/board`.
5. After any push, verify ON PROD; while a fix is local-only, say
   "prod still has X". Recorded ≠ fixed — never claim a confirmation,
   a user trip, or a closed ticket that didn't happen.
6. Grok is review-only and never writes this repo; its worked examples
   (ACM/SANM/INTU) illustrate rules, they are not tickets. Freeze
   items (V3 #11/#12/#13, 35-vs-38) are Edmund's alone.

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

## Data integrity AND data coherence (user directive 2026-09-06 — the
## AECOM growth lesson; real money was on it)
AECOM's 10-Q (11 Aug) showed revenue −14% and a loss. Our wire had the
filing the same day. The quant score did not see it for 25 DAYS,
because revenue/earnings growth still came from Yahoo's statement
tables, which publish a quarter weeks after the filing — while FMP
(the vendor we pay for, declared owner of "what companies report" on
2026-08-09) had it stamped the same afternoon. The error was not that
a source lags — some of our data is not immediate and that is a known,
accepted quantity. The error was that EVERYTHING statement-based ran
off FMP except two values, the two that decide the growth penalty,
and nobody knew, because nobody had listed the fields when the vendor
was re-homed and nothing compared what the score used to what the
company had filed. That is a lack of coherence and of oversight.
Edmund bought the stock on our review. Rules, absolute:
1. DATA COHERENCE: one source owns each fact (FMP: what companies
   report; Yahoo: what the market says; SEC/EarningsCall: the
   documents). Two vendors' versions of the same fact never coexist in
   a scoring path — ES and INTU carried positive Yahoo earnings growth
   while FMP showed negative for the same quarter. The wire, the
   assessor and the quant score see the SAME quarter for a company.
2. KNOWN LATENCY, NOT DISCOVERED LATENCY. Every scoring input has a
   stated source and a stated expected latency, written down. A lag
   that is known and accepted is fine; a lag nobody knew about is an
   integrity failure. If the actual latency is found to differ from
   the stated one, that is an incident, not a footnote.
3. A REFRESH IS NOT PROOF. "fetched_at is recent" says nothing about
   content. Scoring inputs carry provenance (source, quarter end,
   filing date), and the sentinel compares the quarter in the score to
   the latest filing on record against the stated latency — a breach
   is an alarm in the daily brief, by name, the day it opens.
4. WHEN A VENDOR IS RE-HOMED, EVERY FIELD IS LISTED AND EVERY FIELD IS
   MOVED OR EXPLICITLY LEFT, with the reason written down. A doctrine
   sentence is not a migration. Oversight means someone can answer
   "where does this number come from and how old can it be" for every
   field in the score, from a document, not from memory.
5. VERIFIED, NOT ASSUMED. After any data-path change, pick a company
   that filed this week and show its filed quarter in the score's
   inputs before calling the change done.
6. READOUTS READ BACK THE ALARMS. Every "how's the board" / status
   answer states the open freshness violations (env_diagnostics
   source='freshness') by name, or says "none open". Silent green
   while a source is red is forbidden — historical_metrics was red
   from 2026-09-04 through three board readouts nobody surfaced.
The living inventory is DATA_SCORECARD.md (field → source → expected
latency → consumer → status). It is updated in the same change as any
data-path change; the incidents are V3_FIXLIST #20/#21/#22.

## Narrative system (the living-narratives build)
ALL narrative-system work (momentum, vital signs, amendments,
checkpoint minting, lifecycle) is governed by NARRATIVE_SPEC.md — read
it BEFORE touching any of it. Its Progress section is the state.
Shadow-first is absolute: no live narrative field changes without the
spec's acceptance criteria met and user sign-off recorded there.

## Communication (user directive 2026-08-12)
Answers must be straightforward and clear. Lead with the direct answer
in plain words. Short sentences. Detail after, and only what the user
needs to decide. If an answer needs three readings, it failed.

## Incident fixes (user directive 2026-08-13 — the ENS lesson)
When an incident produces a fix the user has agreed to, it gets built
IN THAT CONVERSATION or explicitly assigned to the very next session —
never parked on a list. "High priority" with no owner and no date is
how SMCI's diagnosed bug was left to hit ENS the next day. Lists hold
ideas and designs; agreed fixes get built.

## Other standing rules
- Scoring changes: freeze discipline — explicit user sign-off, log in
  V2_CONSIDERATIONS.md. Offline before/after board diff ritual for big ones.
- Methodology changes visible to the assessor: add a platform_notes row
  with an active window (never let it narrate our changes as company news).
- User-facing surfaces: plain lexicon, 10-point scores, no internal jargon.
- The portfolio-tracker folder on Desktop and its Firebase are READ-ONLY.
