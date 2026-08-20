# V3 #15 — story-grading recalibration: worked design

Status: DESIGN for Edmund's ruling (2026-08-20, prepared at his
request: "not arbitrary, in either direction, just reflective of what
we see"). Nothing here is built. This IS a scoring change —
narrative_strength feeds compute_call_vs_filing_gap in the live
scorer — so freeze ritual applies in full: shadow first, offline
diff, era-stamping, Edmund's sign-off.

## The evidence (30d window, measured 2026-08-20)
Trajectory 72% "accelerating" (962/1335), 7.5% decelerating. Strength:
36% of ALL filings in the 0.9–1.0 bucket, ~92% at 0.7+, near-nothing
below 0.6. Tone 66% "confident". 8-K impact 11:1 positive (795:71).
The wire's display floor (>=0.60) then hides the weak tail, so the
surfaced feed reads rosier still.

## Root cause (the scale, not the season)
The extractor asks "how clearly is management signalling a strategic
direction? 0.0–1.0" — an ADJECTIVE scale graded from the document's
own self-presentation. Every competent IR team signals clearly, so
the frame is absorbed and everything lands 0.8+. Same mechanism for
trajectory: the document SAYS accelerating, so the grade does.
Additional real-but-partial factors: a quality-screened universe and
a genuinely strong season explain SOME tilt; they cannot explain 36%
in the top decile or 72% accelerating.

## Constraint (Edmund's, governing everything)
Not arbitrary in either direction — no quotas, no curves, no
deflation knobs. The grade must become a summary of what is CHECKABLE
in the documents, so the distribution lands wherever reality puts it.

## Considered and REJECTED
- Percentile-as-score / forced distribution: grading on a curve. In a
  genuinely great season it manufactures pessimism; it also converts
  compressed top-end noise (8.9 vs 9.2) into fake 30-point spreads.
  Rejected on the constraint. (A quiet transparency line about the
  season's distribution may ride the wire masthead later — display
  only, never the score.)
- Post-hoc bias deflation (calibrate against a labeled set and shift):
  a thumb on the scale; the mapping itself becomes the arbitrary bit.
- Ensemble second-opinion grading: cost without attacking the frame-
  absorption cause.
- Doing nothing pending believability feedback: narrative_believability
  is EMPTY (0 rows — measured). The protection Edmund cited is not
  operating; waiting on it is waiting on nothing. Populating it is a
  separate item below.

## THE DESIGN — grade the claim-number relationship, not the prose

### A. Anchored strength bands, evidence-cited (the core)
Replace the adjective scale with bands defined by falsifiable content
inside the document. Extractor must OUTPUT the evidence for its band;
uncited numbers don't count; no numbers cited = hard cap at 6.
- 9–10: guidance RAISED + acceleration visible in the numbers the
  document itself quotes + specific named new business (contract,
  capacity, product — with figures). All three, cited.
- 7–8: at least one concrete, quantified positive development; no
  negative guidance action.
- 5–6: steady state; claims are mostly adjectives; numbers flat.
- 3–4: a negative guidance action, OR the numbers contradict the
  narrative (prose claims growth, filed figures flat/declining).
- 0–2: cuts, withdrawals, impairments; the narrative in retreat.
No distribution target of any kind: a great quarter may legitimately
fill the top bands — but it must PAY for them in cited numbers.

### B. Trajectory = the company against its own prior artifact
Pass the PRIOR filing's extracted claims into the prompt. "Accelerating"
only if this document claims MORE than its predecessor (higher
guidance, faster claimed growth, new initiatives added); "decelerating"
when walking back; "stable" otherwise. Self-referential anchor: 72%
of companies cannot forever claim more than they claimed last
quarter, so the skew collapses structurally — with zero quota. This
also aligns trajectory with the promise/checkpoint philosophy (the
document graded against its own record, which IS "what we see").

### C. Tone → groundedness
Rename the axis to what is checkable: grounded (confident WITH cited
numbers) / promotional (confident WITHOUT them — the new, load-bearing
category) / cautious / defensive. The wire pill becomes information.

### D. 8-K impact anchors (small companion)
±bands defined by quantified thresholds (e.g. |4–5| requires a
quantified guidance/portfolio/charge figure material to revenue or
book); routine governance/financing housekeeping pinned 0. The 8-K
population's voluntary-good-news tilt is real and stays — anchors
just stop routine buybacks grading +4.

## Validation & rollout (freeze ritual, in order)
1. SHADOW SAMPLE: re-grade ~150 stratified filings (known-weak set —
   EL's sales-decline year, SANM thin-economics, GIS negative-ROE,
   LHX around the CEO exit; known-strong — NDSN record+raise; plus
   random fill). Cost ~ $3 (Haiku). Present old-vs-new distribution +
   a case table. ACCEPTANCE: known-weak land <=5 with correct cited
   evidence, known-strong stay high, spread emerges naturally. No
   distribution target — discrimination, not quota.
2. CONSUMER IMPACT: recompute call_vs_filing_gap old-vs-new for the
   sampled symbols; then offline board diff. Expected small (the gap
   is a difference of averages, uniform inflation partially cancels)
   — VERIFY, never assume.
3. ERA-STAMPING (the practical crux): filing_themes gains
   rubric_version. The scorer's 18-month gap window must never mix
   eras blindly. The window holds 9,094 rows (4,385 calls, 3,829
   10-Qs, 880 10-Ks); full re-extraction ≈ $150–200 at Haiku prices
   (estimate to be firmed in-session and put to Edmund BEFORE
   running — V3 #1 rule). Recommended: full 18-month re-extraction
   so the gap stays one-era; fallback if cost declined: compute gap
   within-era only, old era frozen until it ages out.
4. CUTOVER with Edmund's sign-off recorded in V2_CONSIDERATIONS +
   platform_notes row (assessor must not narrate the re-grade as
   company news). Wire keeps displaying whatever era a filing was
   graded under until its era is re-extracted — no silent rewrites.

## Companion item (separate build, not this change):
POPULATE BELIEVABILITY. narrative_believability is empty because
claims resolution never runs. Wire the claims-grading pass (claims
mature at next report → confirmed/missed → per-company claim_accuracy)
into after-close; backfill the resolved backlog. Once populated, the
extractor prompt gains the per-company caution ("this management's
graded claim accuracy: X%") — Edmund's long-run protection, made real.

## Sequencing note
Independent of the September momentum calibration (different fields),
but both touch narrative honesty — reasonable to run this design's
steps 1–2 NOW (shadow only, ~$3), and schedule cutover alongside the
calibration window so the freeze rituals batch.

## SHADOW SAMPLE RESULTS (2026-08-20, 141 of 150 graded; ~$3)
Distributions (old → new):
- Strength: mean 0.77 → 0.59, median 0.78 → 0.50. Top bucket
  (0.9–1.0) went from 33% of the sample to TWO filings (1.4%) — and
  both paid for it (WCC: record $6.7B sales +13% reported AND
  organic, four straight double-digit quarters; URI: +12% to $4.4B).
  The mode is now the 0.5–0.6 "steady state" band (43%) — adjectives
  without numbers land there, exactly as specified.
- Trajectory: 67% accelerating → 26% accelerating / 40% stable / 33%
  decelerating. The self-referential anchor balanced it with zero
  quota.
- Groundedness: 13 filings graded "promotional" (confident without
  numbers) — the category catches EL's 10-K, NDSN's May 10-Q, ENS's
  10-K.
Known cases (the acceptance test):
- EL 10-K (sales-decline year): 0.82/accelerating → 0.50/decelerating,
  promotional. EL May 10-Q → 0.30 (cites the 5,800–7,000 position
  eliminations). EL's call stays 0.80/accelerating GROUNDED — the
  call genuinely carries numbers; the divergence is the signal.
- LHX 10-Q post-CEO-exit: 0.85/accelerating → 0.40/decelerating.
  LHX call keeps 0.85 — guidance raised WITH figures, cited.
- ACM Aug call (the charge + cut): 0.82/accelerating →
  0.50/decelerating.
- Calls still outgrade filings (SANM/SMCI/ENS calls 0.75–0.85
  grounded) — the call_vs_filing_gap signal SURVIVES, now
  evidence-based rather than tone-based.
One defect found, one rule added: a single output (PAG call) returned
0.00 with EMPTY evidence — a failed extraction, not a grade. CUTOVER
RULE: any output whose band is not accompanied by at least one cited
evidence string is INVALID and retries; never stored. (This also
protects the top bands symmetrically.)
Next decision (Edmund's): cutover ruling + the 18-month re-extraction
(~$150–200, firm quote before running), recommended batched with the
September calibration freeze window.
