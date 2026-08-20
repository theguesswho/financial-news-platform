# V3 #13 — seat-vs-guard precedence: build spec

Session opener (Edmund types exactly this, nothing more):
**"Read V3_13_PRECEDENCE_SPEC.md and continue from the Checklist."**

Status: OPEN. Ruled by Edmund 2026-08-20 in conversation, scoped same
day. CLAUDE.md + STANDING BRIEF bind. This IS a board-membership
change → freeze discipline: the offline diff below is MANDATORY and
gates the commit; the change is logged in V2_CONSIDERATIONS.md as
part of this session.

## The ruling (Edmund, 2026-08-20)
Option (a) with the keep: **the seat wins above the exit line; the
guard only kills below it.** In full:
1. A name whose raw gem score is below BOARD_EXIT (0.32 / 3.2) is OFF
   the displayed board, always — no verdict, hold, or seat overrides
   a collapsed score. (The guard's real job, kept.)
2. At or above BOARD_EXIT, a seat granted by the methodology is
   HONOURED on every product surface: a materiality-corridor hold
   displays at its held tier (INTU class), and an exit-hysteresis
   grace seat displays (CSL class), with the assessor's verdict
   layered on top exactly as the normal merge does.
3. Above the entry line nothing changes — today's behaviour is
   already correct there.
Effect: the product board stops silently discarding what the
methodology grants; Streamlit and /board should agree (the 35-vs-38
wrinkle is expected to close — VERIFY, do not assume, and record
whether it does).

## Where the change lives — ONE place
`pipeline/board_membership.py :: _resolve_tier` (and nothing else):
the shared resolver that /board, the force rosters, and
daily_report's masthead/moves all consume. Change it there and every
surface inherits; touch NO consumer. Today's defect is precisely that
the resolver recomputes `tier_for(gem)` and requires it non-null,
which erases seats the archiver granted.
- New semantics: the "raw seat" is the SNAPSHOT'S STORED `tier`
  column (the archiver already writes it hysteresis-aware — CSL
  08-19: gem 0.339, tier='Watch'), not a fresh tier_for(gem). Add
  the hard kill: seat counts only while gem >= BOARD_EXIT.
- Corridor holds arrive as a stamped assessed_tier (materiality
  hold): honour them under the same >= BOARD_EXIT kill.
- VERIFY THE DATA SHAPES FIRST, with queries, before coding: how the
  archiver stores `tier` for (a) grace-seat names, (b) corridor-held
  names whose raw sits under the entry line, (c) the 'None'-string
  assessor veto (must STILL exclude — a veto is a ruling, not a
  seat). Paste the evidence into the checklist.
- Streamlit is NOT touched (it is already correct per the ruling).
- The existing `exit_grace` flag keeps working; do not invent new
  reader-facing badges in this session.

## MANDATORY offline diff (gates everything; freeze ritual)
Before any commit: run the resolver OLD vs NEW over the LATEST
snapshot AND the last 7 snapshots (read-only). Produce, per date:
every symbol whose displayed membership or tier flips, with gem,
stored tier, assessed_tier, and which rule seated it.
- EXPECTED flips: additions only, all of them INTU-class (corridor
  hold) or CSL-class (grace seat), all with gem >= 0.32.
- STOP CONDITIONS — halt, commit nothing, report to Edmund: any
  REMOVAL of a currently displayed name; any addition with gem <
  0.32; any addition seated by a bare stale verdict (no hold, no
  stored-tier seat); or a flip count that surprises (>~6/day).
- Paste the full diff into the Checklist. This is the evidence
  Edmund's ruling was implemented and nothing else.

## Ripple checks (inherit, verify, don't re-implement)
- /board: flipped names appear with correct tier/score; exit_grace
  true where seated by grace; counts move accordingly.
- Force rosters: on_board still == /board exactly (the shared-set
  law) — flipped names now inside.
- daily_report: masthead count == membership; the NEXT edition will
  narrate the flips as entries — that is CORRECT news ("restored by
  rule change" needs no special-casing; but DO add a platform_notes
  row with an active window so the assessor never narrates the
  methodology change as company news — CLAUDE.md standing rule).
- v2d track record: lifecycle reads tiers for lots — confirm the
  after-close lot logic consumes the same resolution and that no
  false buys/sells result (grace-seat Watch names are not Strong
  Buys, so lot behaviour should be unchanged — VERIFY).

## Paperwork (same session, before it ends)
- V2_CONSIDERATIONS.md: dated entry — ruling, rationale, diff
  summary, Edmund's sign-off quote.
- V3_FIXLIST.md #13 → Done with date + commit; note both worked
  examples resolved.
- FRONTEND_SPEC.md dated update: product board now honours seats;
  35-vs-38 outcome recorded (closed or still open, honestly).
- platform_notes row (active ~5 days): "board display now honours
  corridor holds and grace seats above the exit line; several names
  reappeared without new company news."

## Acceptance (all with pasted evidence)
1. Offline diff produced, within expected classes, no stop condition.
2. Local /board (stale :8010 killed, same DB): non-flipped entries
   byte-identical to pre-change; flipped names present per the diff.
3. Force roster on_board == /board on the big force + one mid force.
4. daily_report masthead == membership for the same as_of.
5. Streamlit untouched (git status proves it).
6. Local commit(s); NO push — push happens with Edmund at Railway,
   then prod verify: flipped names visible, Streamlit-vs-product
   count gap re-measured and recorded.

## Guardrails
- Scope is _resolve_tier + the paperwork + platform_notes. No scoring
  math, no archiver changes, no Streamlit, no new UI, no other V3
  items, no 2-day rule.
- Machinery does the assessing; recorded ≠ fixed; stop on surprises.
- No `git push` unless Edmund has just said "push" AND is at the
  Railway dashboard; deploy-gate slots bind.

## Checklist
- [ ] 0. Data shapes verified with queries (grace seat / corridor /
       veto rows) — evidence pasted
- [ ] 1. Offline OLD-vs-NEW diff over latest + 7 snapshots — pasted,
       classes as expected, no stop condition
- [ ] 2. _resolve_tier changed to the ruling's semantics
- [ ] 3. Local /board before/after: non-flipped byte-identical,
       flips match the diff
- [ ] 4. Roster + report ripple checks pass
- [ ] 5. v2d lot-logic consumption verified unchanged
- [ ] 6. Paperwork: V2_CONSIDERATIONS + V3 #13 Done + FRONTEND_SPEC
       update + platform_notes row
- [ ] 7. Local commit; push status stated honestly
- [ ] 8. (post-push, Edmund present) prod verify + 35-vs-38 outcome
       recorded; Status flipped CLOSED
