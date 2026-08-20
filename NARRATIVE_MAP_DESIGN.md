# Narrative Map — design + implementation (PARKED)

Status: PARKED on the to-do list (Edmund, 2026-08-20). No session is
assigned. Do not build from this file until Edmund schedules it with
its own opener. Prototype artifact (design study, private):
https://claude.ai/code/artifact/c13cea2a-6e4b-4237-ada3-ddf71cbbd939

## What it is
A product page that shows the living narrative library itself — the
thing the whole instrument runs on and the site never shows: what the
stories are, their tiers, their vital signs, and how they interact
through shared companies. The prototype was built read-only from prod
on 2026-08-20 and reviewed by Edmund ("this is interesting" — park).

## The two ideas that earned the page (from the prototype review)
1. **The interaction matrix** — the ten broadest narratives crossed
   against each other, cell darkness = shared-company count, hover
   reveals the pair + example tickers. Shows where one story's
   evidence doubles as another's, and where one company's stumble
   bruises several theses at once. Nothing else on the platform
   conveys this.
2. **Per-narrative vital-signs strip** — last week's support-vs-
   erosion bar + open promises (pending checkpoints, next deadline)
   on every narrative card. The "living" in living narratives, made
   visible.

## Content spec (prototype-proven)
- Masthead: library counts (active by tier, open promises, births
  queued), dated "as of" line.
- Macro + sector: full dossier cards — machinery's thesis verbatim
  (truncated), breadth, board names as ticker chips (membership via
  the shared board_membership resolver, never a parallel query),
  vital-signs strip, silent-report flag once decay is live.
- Emerging: compact rows by breadth. Candidates: count + note only.
- Interactions: the matrix + ranked strongest-pairs list (shared
  count bar, example tickers).
- Pulse: weekly ledger ops, support vs erosion, sqrt scale, honest
  annotation (earnings flood vs true quiet).
- Momentum labels: show ONLY what is live. While labels are frozen
  (166 stable / 15 accelerating), either omit them or show them with
  a frozen-until-calibration note — never paint the empty shadow
  states as if live.

## Design language (matches the site; artifact demonstrates it)
- Wire idiom: 11px uppercase kickers, Libre Franklin UI, serif
  (Source Serif 4) for theses — narratives are WRITTEN things — IBM
  Plex Mono for tickers/counts. Tier colors validated for CVD both
  themes: light #008573/#3060C0/#B06A00/#9C4DC4 (macro/sector/
  emerging/candidate), dark #17A186/#6A8FE0/#BC8114/#A971D6; erosion
  reserved rust (#B4442C / #D06A50). Tier chips always carry the
  word, never color alone.
- All 19 surface laws apply. Plain lexicon at the API boundary
  (support/erosion arrive as reader words); no unsourced numbers —
  every figure traces to a stored row; nulls omitted; assessor dark.

## Implementation sketch (product track: api/ + web/ only)
- New read-only endpoint, e.g. GET /narratives/map: one payload —
  narratives (id, name, tier, thesis, breadth, board ticker chips via
  board_membership), last-week health row, pending-checkpoint counts
  + next deadline, top-N overlap pairs (computed in SQL from
  narrative_exposures self-join, active only, floor on shared count).
  Cache by cadence like the other read endpoints. NO writes.
- Web: one page. OPEN DECISION (Edmund's, before build): where it
  lives — the nav is five nouns as decided 2026-08-19 and this page
  was NOT part of that ruling; candidates are inside Forces (a
  "library" view) or a link from the Forces page header. Do not add a
  sixth noun without his explicit word.
- Matrix hover = title-attr tooltip minimum; no charting library.
- Effort estimate: one session (endpoint + page + laws pass), given
  the prototype settles layout questions.

## Dependencies / sequencing
- After: the FIXPACK B push is live (shares the read-endpoint
  patterns) and ideally after the September momentum calibration so
  the page can show honest momentum states instead of a frozen-label
  caveat.
- Unaffected by: V3 #13 (matrix uses board_membership, so it inherits
  whatever precedence Edmund rules).
