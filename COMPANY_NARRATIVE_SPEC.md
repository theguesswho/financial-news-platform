# Company Narrative Layer — Specification (DRAFT for final sign-off)

Status: scoped 2026-08-04, user-shaped. Nothing built until this document
is approved. The last unbuilt piece of the v2 exposure redesign: narratives
that belong to ONE company, held to a stricter evidentiary bar than any
other object in the platform.

## 1. Definition — what qualifies (the anti-hallucination core)

A company narrative is **a change, not a description**. All four required
at birth; any failure = no narrative:

1. **Direction and a timeline.** "Otis has a service moat" is a business
   description — timeless, unfalsifiable, disqualified. "AA is integrating
   South32's alumina assets to capture upstream margin" is a narrative.
   A narrative may be COMPOSITE ("EM healthcare transition with AI as
   catalyst") — one story, several dynamic elements, each checkpointable.
2. **Company-specific causality** — the company's own actions/position,
   not a shared tailwind (that's the sector layer's job).
3. **Falsifiable checkpoints written at birth** — each a testable claim
   with an observable and a timeframe, status pending/confirmed/missed.
4. **Evidence only from the company's own filings and calls.** Never price
   action, never analyst opinion (the market's view is not evidence —
   platform first principle).

**Structural guards:**
- **ONE active company narrative per company.** The judge must name THE
  story. Scarcity is the strongest anti-tagging device. The story itself
  can be as composite as reality requires.
- Two-vote Sonnet birth (single-vote establishment variance is measured
  and real — the LDOS precedent).
- 28-day seasoning before any scoring effect.
- Births capped at 5/week (queue, not discard, above the cap).
- **Negative-control audits**: monthly, the birth judge is fed ~5 stocks
  chosen for having no plausible company story; any birth from a control
  is a measured false positive. FP rate > ~10% freezes births pending
  prompt tightening. The judge's error rate is a tracked number, never
  an assumption.

## 2. The stored artifact — a living dossier, not a tag

Per narrative (reusing the narratives-table machinery, scope='company',
parent = sector narrative, plus a symbol column):

- **Thesis**: full-paragraph current understanding, synthesized from the
  TOTALITY of source material. VERSIONED — updates append the prior text
  to history; we never lose what we used to believe.
- **Falsification checkpoints**: structured rows (claim, observable,
  deadline, status, evidence link) — not prose.
- **Evidence ledger** (narrative_evidence, finally wired): append-only,
  dated, source-cited rows — the record the thesis must answer to.
- **Maturity state** (0–1): what scoring reads. A function of checkpoint
  outcomes, evidence freshness, and seasoning — never of narrative
  enthusiasm. Born low; earns its way up via confirmations; decays on
  misses or evidence silence (slow decay, ~90-day half-life on staleness;
  fast on missed checkpoints).
- Standard lifecycle: candidate → active → declining → falsified/dormant,
  full event history.

**Event-driven maintenance**: new filings route here through the existing
dirty-symbol machinery. Checkpoints are checked when their relevant filing
type arrives; the thesis is revised in the presence of its own history
(building/reinforcing/shifting/diverging — same continuity discipline as
qual assessments). No scheduled rewrites, ever.

## 3. Birth channels

1. **Migration (one-time)**: all 40 override-corpus theses run through the
   birth judge with FULL source material (not the override summaries).
   The judge's verdicts — accept with checkpoints, or reject with reason —
   are recorded per thesis. User-delegated 2026-08-04: the mechanical bar
   decides, uniformly; the curation table (13 recommend / 5 borderline /
   22 hold) is a prior the judge may overrule either way.
2. **Ongoing**: the override mechanism becomes the birth channel. Its
   screen finds quant-qualified narrative-blind stocks; its gate already
   applies full assessment. An endorsed thesis births a PERSISTENT
   narrative (replacing the transient boost). The override is promoted
   from patch to organ, then the boost path retires.
3. **Event births**: a transformative filing (major acquisition, platform
   launch) may nominate directly via the ledger update pass flagging
   "possible company narrative" for the birth judge. Same bar, same votes.

## 4. Scoring integration — decided by measurement, not preference

Three candidate designs, ALL run as parallel shadow scores during the
calibration window (pure arithmetic; negligible cost):

- **Design A**: company narrative as an additional exposure in the E
  noisy-OR (strength = maturity). Risk: universal E-inflation.
- **Design B**: dual-channel — E = max(E_market, E_company × maturity).
  A stock's exposure is its BEST story, never the sum. Matches the Dell
  test's semantics ("THE unpriced story").
- **Design C**: company channel occupies the override-boost slot —
  bounded additive, most conservative, current calibration untouched.

**Calibration protocol:**
- Shadow lane computed daily for all three designs alongside the live
  score. Live scoring untouched throughout.
- **Communication**: the daily brief carries a Shadow Lane line (board
  positions each design would move; notable disagreements). **Interim
  report at day 5** — early call if one design is clearly broken/winning;
  else run to day 14–28. Final decision report with full evidence; ONE
  design goes live only after user sign-off (same ritual as v2 cutover).
- **Yardsticks**: (1) board-diff sanity — moves look like information,
  not churn; (2) qual-assessor referee — on disagreements, does the full
  assessment side with the shadow or the live score; (3) retrospective
  micro-backtest on the override corpus (gate-endorsed vs gate-declined
  subsequent performance) — small-N, earnings-season-biased, reported
  with those caveats explicitly.

## 5. Phases (each gate = explicit user go)

- **P1 — Foundations** (~2 days): narrative_evidence wired for real;
  symbol + maturity + checkpoint schema; migration run through the birth
  judge; founding verdicts recorded and reported to user.
- **P2 — Birth machinery** (~2 days): override→birth channel; negative-
  control BASELINE measured before anything scores; event-birth flag.
- **P3 — Shadow lane** (5–28 days passive): daily shadow scores + brief
  reporting + day-5 interim.
- **P4 — Live integration**: winning design ships; override boost
  retires; delivery checkpoints feed management-credibility (#15) later.

## 6. Decisions taken (user, 2026-08-04)

- One narrative per company: APPROVED (narratives may be composite).
- Migration curation: DELEGATED to the mechanical bar, uniformly applied.
- Calibration window: approved; day-5 interim with early-call option;
  brief carries the Shadow Lane during the window.
- Design A/B/C: no prior imposed; the shadow data decides.
