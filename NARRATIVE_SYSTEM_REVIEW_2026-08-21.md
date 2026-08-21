# Narrative system review — 2026-08-21

Prepared for Edmund's decay-shadow review (NARRATIVE_SPEC Phase 1b
gate), widened per his request to the whole system: growth AND decay.
All numbers pulled read-only from prod on 2026-08-20/21. The decision
this document supports is DECAY LIVE ONLY — momentum labels stay
frozen until the September calibration ritual.

## The library today
170 active narratives: 106 candidate, 43 emerging, 11 sector, 10
macro (11 more absorbed by merges). Birth queue: 61 candidates
pending judgment, 46 accepted this cycle. Live momentum labels read
166 "stable" / 15 "accelerating" — the static-label problem the
September calibration exists to fix; the honest per-week states are
accumulating in narrative_health_history with the label column
deliberately empty.

## Growth side (the half that was already live)
- Ops pulse follows the earnings calendar exactly: w/c Jul 27 —
  2,599 adds / 875 strengthens / 986 removes (the flood, incl.
  backfill); w/c Aug 3 — 742 adds; w/c Aug 10 — 47 adds, 67
  strengthens; this week so far — 11 ops (tape quiet). The system
  breathes with the season rather than churning on nothing.
- The judge touched 898 exposure pairs since Aug 5 — reconfirmation
  through evidence is happening at scale.
- Checkpoints: 383 minted to date (111 in the last 7 days — the
  earnings tail turned into dated promises), 379 pending, 3
  confirmed, 1 missed, 11 due inside 30 days. Verdict flow is just
  starting; the pending book is the system's forward calendar.
- Vital signs, last complete week (w/c Aug 10): 177 support ops vs 5
  erosion ops across 162 narratives.

## Decay side (the shadow under review)
Design recap: at each earnings event, if the extracted themes fail to
reconfirm an active exposure (cosine < 0.25) and the judge saw no
evidence either way, ONE `decay` op is recorded for the pair. Live
mode would: increment the pair's decays counter, mark it waning, and
only on the SECOND consecutive silent report step exposure down 0.25
(floor 0.10). Reconfirmation by either path resets to zero.

Shadow findings (ran on the Aug 11–14 earnings events):
- 85 decay ops, 85 distinct exposure pairs, 69 symbols. Sample
  similarity misses: 0.17–0.23 vs the 0.25 bar — the threshold is
  rejecting genuinely absent themes, not near-matches.
- ZERO pairs have two consecutive silences. Had decay been LIVE for
  this window, NO exposure value would have moved and NO score would
  have changed — the entire effect would have been 85 counters at 1
  and waning flags. First possible step-downs are a full quarter
  away (the next report cycle for those 69 names).
- Live-table proof of shadow isolation: every narrative_exposures row
  still shows decays=0, no waning statuses, exposures untouched.

## Read on the whole system
Working as built. Growth and erosion are both recorded; the ledger is
event-driven, not noisy; checkpoints give the library a forward
calendar; the one dishonest surface (the static momentum label) is
already scheduled for the calibration. The known open methodology
items (V3 #13 corridor/guard precedence, 35-vs-38) are display-layer
questions, not narrative-system defects.

## The decision (Edmund's alone)
Going live with decay today changes nothing immediately: counters
start counting, waning flags appear on silent pairs, and the first
score-affecting step-down cannot occur before a name's NEXT silent
report. The desk's read: safe to enable, with the September
calibration unchanged. Risks worth naming: the 0.25 similarity bar
has only one earnings window of evidence behind it, and 69 names
carrying a first silent strike will step down next cycle unless
reconfirmed — that is the intended teeth, but it is teeth.

Sign-off: SIGNED 2026-08-21 — Edmund, in conversation with the
methodology desk, after reading this review: "Signed off". Decay goes
LIVE at the weekly pass (scheduler_light step 5h flipped shadow=False
same day; counters start from zero, shadow strikes not carried over).
