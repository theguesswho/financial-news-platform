# TO DO — historical data backfill (window repair for the Sealed Replay)

Status: NOTED 2026-08-25, awaiting full scoping. Do NOT build from
this note — it reserves the work and pins the probe facts; a proper
gated spec (sittings, quotes, date-verification rules) comes first.
Feasibility evidence lives in NARRATIVE_REPLAY_DESIGN.md → "R0 probe
results (2026-08-25)".

## What
Recover the missing 18-month source data so the replay can run the
full window (option (b)) and the live archive stops being text-thin
pre-2026:
1. ~2,775 earnings-call transcripts (vendor archive; probe 4/4 found;
   expect 85–95% recovery).
2. ~2,075 10-K/10-Q texts (every row has its sec.gov URL stored —
   plain re-download).
3. Feb 3 – Apr 4 2025 daily closes, ~845 symbols (yfinance,
   unadjusted — as-printed rule satisfiable).
4. Then: v2-grade the recovered documents (overlay, era-stamped) and
   design-D re-anchor of window 8-Ks (their analyses are complete but
   v1-scale).

## Probe-backed estimates (to be firmed in the scoping spec)
- New LLM spend ≈ $250–350 total; fetching ≈ $0 (existing vendor sub,
  free SEC/yfinance).
- Elapsed 3–7 days, dominated by vendor rate limits — dripped,
  resumable, throttled to protect the nightly pipeline's quota (the
  Aug-16 429 lesson).
- One build sitting for the fetcher; unattended thereafter.

## Non-negotiables the scoping spec must carry
- INTERNAL-DATE VERIFICATION before any transcript stores under a
  label (V3 #2 / the ACM rule) — reject mismatches, count them.
- Quota throttle with headroom for the nightly runs.
- Recovered docs graded v2 with rubric_version stamps; no silent
  rewrites of era-1 rows; a fetch-failure list, not a shrug.
- Cost gates in sittings (firm quote → Edmund's "approved" before any
  paid volume), per the established pattern.
- Prices staged as-printed (auto_adjust=False), never the adjusted
  series.

## Sequencing
- Independent of the September calibration; can drip in the
  background once scoped.
- Unblocks: the replay's (a)/(b)/(c) window ruling — if this runs,
  option (b) FULL WINDOW becomes the default; the ruling is still
  Edmund's at the replay's R0 gate.
- Side benefit either way: the LIVE platform's wire/dossiers gain
  full historical text and honest v2 grades for pre-2026 documents.
