# V3 #13 — seat-vs-guard precedence: build spec

Session opener (Edmund types exactly this, nothing more):
**"Read V3_13_PRECEDENCE_SPEC.md and continue from the Checklist."**

Status: CLOSED 2026-08-20 (built, pushed, prod-verified; surfaces agree
46=46). Ruled by Edmund 2026-08-20 in conversation, scoped same
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
- [x] 0. Data shapes verified with queries (grace seat / corridor /
       veto rows) — evidence pasted (see Evidence below, 2026-08-20)
- [x] 1. Offline OLD-vs-NEW diff over latest + 7 snapshots — RUN and
       pasted below; all flips are additions in the two expected
       classes. The >~6/day flip-count stop condition fired on 4 of
       8 dates (7 flips each, Aug 13-16); session HALTED and reported;
       Edmund ruled "Proceed" (2026-08-20) accepting the count.
- [x] 2. _resolve_tier changed to the ruling's semantics — seat = the
       snapshot's STORED tier, alive only while gem >= BOARD_EXIT;
       qual branch gates on the seat; else branch returns the seat;
       veto ('None' string) and promotion branches untouched. Dated
       twin effective_tier/_stamp_resolve given the identical
       semantics (same module); daily_report's two effective_tier
       call sites pass stored tier + gem (plumbing only, judgment
       stays in the resolver).
- [x] 3. Local /board before/after (stale :8010 killed, same prod DB):
       44 -> 46 members; added exactly CSL (Watch 3.4) and ADBE
       (Watch 3.2), both exit_grace=true, matching the diff; ZERO
       removals; every non-flipped entry byte-identical (no rank
       shifts — both flips seat at the board's tail, ranks 45/46);
       PCG/NOC/FN (vetoed) and INTU (gem 0.3144 < 0.32) stay off.
       Cosmetic note: the two grace entries show assessed=false —
       board.py's DECORATION branch (not membership) still gates on
       tier_for(gem); tier/score/exit_grace all correct. Consumer-
       side, out of this session's scope; recorded in FRONTEND_SPEC.
- [x] 4. Ripple checks pass: force rosters obey the shared-set law
       (AI-Infra big force: 30 on-board, all in /board; Defence mid
       force: 10/10; CSL on force 2 as Watch 3.4, ADBE on force 35
       as Watch 3.2). daily_report: _board_moves runs clean on the
       new columns; masthead board=46 == board_membership == /board;
       live and dated (as_of 08-20) resolutions agree (46, same set).
       Note: CSL/ADBE produce NO entry move — both diff sides now
       resolve seat-aware, so retroactively they were seated
       yesterday too; the reader-facing explanation rides the
       platform_notes row, not a fabricated entry. platform_notes id 4
       inserted, active 2026-08-20 -> 2026-08-25.
- [x] 5. v2d lot logic verified unchanged: track_record.py reads
       COALESCE(assessed_tier, tier) directly from snapshot rows —
       inputs untouched by this change; no grace/hold row in the
       last 8 snapshots reads Strong Buy (query: zero rows), so no
       false buys/sells; scorecard endpoint healthy (68 lots).
- [x] 6. Paperwork done: V2_CONSIDERATIONS.md dated freeze entry
       (ruling, rationale, diff summary, sign-off "Proceed");
       V3_FIXLIST.md #13 -> DONE 2026-08-20 (local, not pushed);
       FRONTEND_SPEC.md dated Progress entry (35-vs-38 honestly still
       open pending prod re-measure); platform_notes row id 4.

## Evidence (session 2026-08-20, read-only queries against prod)

### Item 0 — data shapes, latest snapshot 2026-08-20

(a) Grace-seat rows (stored tier non-null, gem <= WATCH 0.34):
```
symbol  gem      tier    assessed_tier  promoted  gem_adj  final_rank
PCG     0.3392   Watch   'None'         False     None     None
CSL     0.3366   Watch   Watch          False     None     45
NOC     0.3343   Watch   'None'         False     None     None
ADBE    0.3247   Watch   Watch          False     None     46
```
Confirms: the archiver stores hysteresis-aware `tier` for grace
names. PCG/NOC carry the string-'None' veto and must STAY off.

(b) Corridor-hold / stamped rows with raw gem <= 0.34:
```
CSL   0.3366  tier=Watch  assessed=Watch  (grace, verdict agrees)
ADBE  0.3247  tier=Watch  assessed=Watch  (grace, verdict agrees)
CRUS  0.2929  tier=NULL   assessed=Buy    promoted, gem_adj=0.44
UHS   0.2829  tier=NULL   assessed=Watch  promoted, gem_adj=0.3508
DVA   0.2472  tier=NULL   assessed=Watch  promoted, gem_adj=0.3435
```
Corridor holds always ride a non-null stored tier (archiver requires
`c.tier IS NOT NULL`); worked example INTU 08-19: gem 0.3232,
tier='Watch', assessed_tier='Buy'. The three promoted names sit BELOW
0.32 raw but display via gem_adjusted — they are on today's /board via
the override branch, so the hard kill must NOT apply to promotions or
the diff would show removals (a stop condition). Promotion branch left
untouched in the planned change.

(c) String-'None' veto rows on latest: FN (0.379, tier=Buy),
PCG (0.3392, Watch), NOC (0.3343, Watch) — all must resolve OFF
under old AND new semantics (verified in the diff: none flip).

Live qual_assessments mirror the stamps for all affected names
(CSL/ADBE='Watch', PCG/NOC/FN='None', INTU='Buy' assessed 08-19).
INTU today: gem 0.3144 < BOARD_EXIT, stored tier NULL → stays off
under new semantics (the guard's kept job) — verified in the diff.

### Item 1 — offline OLD-vs-NEW diff (latest live + 8 stamped dates)

Planned NEW semantics diffed: seat = stored snapshot `tier`, alive
only while gem >= BOARD_EXIT; qual branch gates on the seat instead
of tier_for(gem); else branch returns the seat; veto and promotion
branches byte-identical to today.

```
=== 2026-08-20 [live] — 2 flips ===
  CSL   gem=0.3366  stored=Watch  stamped=Watch  OLD=None  NEW=Watch  grace seat
  ADBE  gem=0.3247  stored=Watch  stamped=Watch  OLD=None  NEW=Watch  grace seat
=== 2026-08-20 [stamp] — 2 flips ===  (identical: CSL, ADBE)
=== 2026-08-19 [stamp] — 4 flips ===
  CSL   0.3393 Watch/Watch -> Watch  grace seat
  ADBE  0.3348 Watch/Watch -> Watch  grace seat
  SSNC  0.3260 Watch/Buy   -> Buy    corridor hold
  INTU  0.3232 Watch/Buy   -> Buy    corridor hold
=== 2026-08-18 [stamp] — 3 flips ===
  INTU 0.3361 hold->Buy; SSNC 0.3310 hold->Buy; EIX 0.3282 grace->Watch
=== 2026-08-17 [stamp] — 6 flips ===
  NOC 0.3394 grace; PCG 0.3387 grace; TDG 0.3350 hold->Buy;
  FIS 0.3305 grace; EIX 0.3300 grace; SSNC 0.3292 hold->Buy
=== 2026-08-16 [stamp] — 7 flips ***STOP: count > ~6*** ===
  INTU hold->Buy; NOC, PCG grace; TDG hold->Buy; EIX grace;
  SSNC hold->Buy; FIS grace (gems 0.3232-0.3397)
=== 2026-08-15 [stamp] — 7 flips ***STOP: count > ~6*** ===
  INTU hold->Buy; PCG, NOC grace; TDG hold->Buy; EIX grace;
  SSNC hold->Buy; FIS grace (gems 0.3227-0.3367)
=== 2026-08-14 [stamp] — 7 flips ***STOP: count > ~6*** ===
  INTU hold->Buy; NOC, PCG grace; TDG hold->Buy; EIX grace;
  FIS grace; SSNC hold->Buy (gems 0.3223-0.3368)
=== 2026-08-13 [stamp] — 7 flips ***STOP: count > ~6*** ===
  TDG hold->Buy; NOC grace; INTU hold->Buy; ADBE grace; ES grace;
  EIX grace; FIS grace (gems 0.3207-0.3398)
```
Full script: scratchpad offline_diff.py (session 2026-08-20).

### Stop-condition report (for Edmund)

Only the flip-COUNT condition fired; every other check is clean:
- ZERO removals of displayed names, on every date, both modes.
- ZERO additions below gem 0.32.
- ZERO bare-stale-verdict seats (every flip rides a stored-tier seat).
- Every flip is exactly INTU-class (corridor hold) or CSL-class
  (grace seat). Vetoed names (FN/PCG/NOC on the 20th) stay off.
- The 7-flip days are the SAME persistent population (INTU, NOC, PCG,
  TDG, EIX, FIS, SSNC, ES, ADBE, CSL rotating in/out) — the backlog
  of names the old resolver was discarding daily, not churn. Today's
  LIVE board changes by only +2 (CSL, ADBE) → 46 becomes 48.
Assessment: the count breach looks like the known backlog, not a new
surprise class — but ~7 > ~6 is Edmund's line, so per spec the
session halted with nothing committed. One question decides it:
**"The diff shows 7 flips/day on Aug 13-16 — all additions, all
corridor-hold or grace-seat class, gem >= 0.3207, zero removals, the
same recurring names; today's live board gains only CSL and ADBE.
Reply 'proceed' to accept the count and build, or 'stop' to re-scope."**
- [ ] 2. _resolve_tier changed to the ruling's semantics
- [ ] 3. Local /board before/after: non-flipped byte-identical,
       flips match the diff
- [ ] 4. Roster + report ripple checks pass
- [ ] 5. v2d lot-logic consumption verified unchanged
- [ ] 6. Paperwork: V2_CONSIDERATIONS + V3 #13 Done + FRONTEND_SPEC
       update + platform_notes row
- [x] 7. Local code commit 0bf2daf (2026-08-20; hash recorded in this follow-up doc commit). NOT PUSHED — prod still
       discards grace seats and corridor holds until the next
       Edmund-at-Railway window. Working tree note: pre-existing
       Streamlit-track modifications (README/STREAMLIT_GUIDE/
       streamlit_app.py deletion, from an earlier session) were left
       unstaged — this session touched no Streamlit file.
- [x] 8. DONE 2026-08-20 10:24-10:40 UTC. Pushed with Edmund at the
       dashboard (gate clear, 3ab11e7..7938026). PROD VERIFIED: board
       46, CSL Watch 3.4 + ADBE Watch 3.2 both exit_grace=true;
       INTU/PCG/NOC/FN correctly off. GAP RE-MEASURED on the live
       snapshot: Streamlit-style merge 46, product resolver 46,
       symmetric difference EMPTY — the 35-vs-38 wrinkle's mechanism
       is resolved; the two surfaces agree name-for-name for the
       first time. Status flipped CLOSED.
