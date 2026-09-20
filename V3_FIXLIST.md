# V3 fix list

Started 2026-08-11 (user directive). Known defects and improvements not
yet actioned — distinct from V2_CONSIDERATIONS.md (the scoring-change
log; anything here that touches scoring still goes through that ritual
when actioned). Move items to a Done section with date + commit when
fixed.

## High priority

1. **Claim extractor orphaned (HIGH — user 2026-08-11).**
   pipeline/claim_extractor.py has no caller; earnings_claims stopped
   2026-06-12. 674 transcripts unextracted incl. 42 tiered names and all
   7 held positions. Not redundant with narrative_checkpoints (user):
   claims are per-company vendor-verbatim; checkpoints are per-narrative
   judged. Fix: wire into after-close right after transcript ingestion +
   backfill the June 12 -> now backlog (est. one-time LLM cost — check
   extractor's model, give user the number before running). Feeds the
   product track's Companies dossier ("promised vs delivered" pane).

2. ~~Transcript fetch cadence~~ VOID (2026-08-11): the after-close run
   already pulls transcripts (step 2, before the assessor at step 6) —
   the architecture was right all along. Replaced by:
   **Fast-path quarter fallback can fetch the WRONG call (corrected
   diagnosis 2026-08-11).** The vendor indexes by FISCAL quarter (same
   as FMP) — the earlier "calendar/fiscal collision" diagnosis was
   WRONG. Real behavior: the sweep guesses calendar quarter from the
   8-K date; for offset-FY companies the guess misses (404 — correctly,
   transcript not yet published) and the q-1 fallback can fetch the
   PRIOR quarter's call, whose insert then no-ops on the existing FMP
   row (harmless) — but a hand-ingest trusting the fallback's label
   stored ACM's MAY call as "Q3" (caught + deleted same night; see
   CLAUDE.md Evidence integrity rule 3). Fix: derive the FISCAL quarter
   from FYE month (fundamentals_annual) before requesting, and verify
   the returned transcript's internal date before insert; drop the
   blind q-1 fallback.
   RESOLVED SAME NIGHT (the deeper finding): **assessor was blind to
   8-K content** — judged filings it never read; the LHX/ACM class.
   get_stock_context now passes the last 14 days of 8-K analyses into
   every assessment (RECENT MATERIAL EVENTS block); ACM re-assessed
   through the machinery with the charge + guidance cut in view (SB
   held, honestly argued, sharper bear case). Codified as CLAUDE.md
   "Evidence integrity" rules 1-4.

## Methodology (freeze ritual applies)

3. **Narrative momentum — SCOPED 2026-08-11 (user: "we need to nail
   this bit"; build shadow-first, NO live push without sign-off).**
   Today every macro reads "accelerating" = zero signal. Design:
   - Source: the exposure LEDGER, not judge vibes. Per narrative,
     two trailing windows (28d primary, 7d turn-detector):
     support = adds + strengthens; erosion = weakens + removes +
     misses. Net support rate = (support − erosion) / active exposures.
   - States: accelerating (28d rate ≥ +X% and 7d not negative),
     decelerating (28d ≤ −X%, OR any falsification condition hit, OR
     checkpoint failures outweigh passes), stable otherwise; "quiet"
     when ops < minimum N (thin evidence must not flap the label).
   - Company scope: checkpoint verdicts (delivered vs missed) count as
     first-class ops.
   - Calibration: compute over ledger history since July; tune X and N
     so the library actually spreads across states (roughly 20/60/20,
     not 100/0/0). Present distribution to user BEFORE cutover.
   - Rollout: shadow field alongside the current one for ~2 weeks,
     diff shown, then cutover with sign-off. Product landing page
     colors stay ledger-driven until this ships.

4. **EVR consistency knob revisit.** If EVR still smells wrong after the
   fiscal-calendar hygiene: measure residuals against the 15-year
   history or a harsher tail measure.

5. **BAH override-screen candidate.** Offline 5.2 vs live 2.6 — superb
   quality/value, low story exposure. Watch as the BR-class narrative-
   blind override case.

## New analytics (scoring-adjacent — reads scores, never writes them)

8. **Re-rating room ("how big is the opportunity") — DESIGN APPROVED
   2026-08-13, build-ready.** Solves the two factors from the SMCI
   whiplash: a Strong Buy must not die on one good day (thin gaps
   masquerade as real ones because value is a RANK, which hides
   depth), and we want compounders, not trades.
   THE MEASURE — re-rating distance: how far price would move if the
   stock were priced like the MEDIAN company in its story (narrative
   peers; thin groups <~8 fall back to sector, labeled thin evidence
   like the PEG analyst count). ONE multiple per category (user
   2026-08-13, no blended conflicts): most stocks forward P/E; banks
   P/B; REITs P/FCF. No forecasts, no assumptions — today's prices,
   today's peers.
   THE INTERPRETATION — two engines, shown side by side, never
   merged: re-rating room (one-time) + the business engine (quality
   trend: growing/flat/shrinking). Shrinking-earnings cheapness is
   fiction — flag, don't celebrate. Plain-words surface: "Priced X%
   below the typical company in its story (N peers). Business engine:
   growing." Nightly, dated, "on the numbers alone" (assessed layer
   sits on top).
   Companion (from the same episode, still valuable): tier-band
   ceilings/re-entry prices via price-override re-scoring of the REAL
   scorer (never a parallel formula; nightly self-test must reproduce
   today's live score or publish nothing), incl. cyclical cliffs
   (SMCI's punished flag dies at 75% of 52w-high ≈ $44).
   SEQUENCE: build room measure + ceilings → assessor context line +
   surfaces → Dell backtest as validation (how many +20% sessions
   could Dell absorb during its re-rating vs SMCI's one) → THEN the
   doctrine decision (minimum headroom for SB) with the distribution
   in hand, not before.

9. **DONE 2026-08-13 (after ENS became the second victim — the cost of
   logging instead of building).** Two-part fix in the qual trigger:
   (a) earnings-8-K reaction lines now carry an explicit caution that
   an after-hours release makes the quoted move pre-release; (b) a
   DEFERRED REACTION CHECK re-fires the assessment once, after the
   first post-release close, whenever that close moved >=3% (one-shot
   via a 21h assessed_at bound). Verified: full trigger query clean;
   ENS simulation fires tonight at +14%; two backlog victims (MTSI,
   ABNB, Aug 6 releases) caught by the 7-day window and re-assessed
   tonight. Release timestamps aren't stored (SEC acceptance time not
   ingested), so morning-vs-evening can't be distinguished directly —
   the >=3% next-session gate is the proxy; storing acceptance time is
   the eventual clean fix.

## Data / pipeline hygiene

0. **STALE LIVE-SCORING INPUT (found 2026-08-11, highest item here):**
   the weekly embeddings build requires sentence-transformers, absent
   from Railway requirements → it has failed silently on every Railway
   weekly. stock_theme_alignment (its downstream) froze 2026-07-12 —
   and it supplies the 20% "narrative momentum" leg of the priced-in P
   component in LIVE scoring. A fifth of P has run on July-12
   trajectories for a month. Decision needed (belongs at the
   NARRATIVE_SPEC Phase 2 gate, alongside the momentum board diff):
   REPLACE P's leg with narrative-brain honest momentum and RETIRE the
   legacy embeddings/meta-theme-alignment path (recommended — one
   narrative system, no 2GB torch in the image), vs revive the
   dependency (itself a scoring change: unfreezing shifts P).
   Either way the change is freeze-discipline. Interim: it has been
   stale a month with slow-moving trajectories; two more weeks of
   documented staleness beats a rushed unfreeze.
   INTERIM ACTIONED 2026-08-11 (user-approved): sentence-transformers
   added to requirements (unblocks decay SHADOW accumulation on
   Railway) and legacy step 5 explicitly PARKED with a loud weekly
   warning — the P leg stays frozen-and-documented; nothing unfreezes
   outside the Phase 2 ritual.
   **BLAST RADIUS WIDER THAN RECORDED (found 2026-09-05, diagnostic
   only).** This item was logged as freezing stock_theme_alignment
   (the 20% leg of priced-in). It ALSO starves SILENCE DECAY, which
   reads the same field: narrative_decay._event_embeddings requires
   filing_themes.embedding IS NOT NULL. With step 5 parked, NO
   filing_themes row has carried an embedding since week-of
   2026-08-10 (rows/embedded by week: 08-10 51/0, 08-17 22/0,
   08-24 63/0, 08-31 30/0; the 08-03 week still has 534/560 from
   before the park).
   CONSEQUENCE — LIVE DECAY HAS BEEN INERT SINCE ITS 2026-08-21
   CUTOVER. Not crashed: starved. Counters reproduced read-only from
   the pass's own logic for the last two weeklies:
     weekly 08-28: events 58, pairs_checked 286, reconfirmed_judge
       108, already_judged 0, reconfirmed_themes 0, reached
       similarity 14, SKIPPED-NO-EMBEDDING 164; symbols with usable
       embeddings 4 of 58.
     weekly 09-04: events 49, pairs_checked 246, reconfirmed_judge
       95, already_judged 0, reconfirmed_themes 0, reached
       similarity 7, SKIPPED-NO-EMBEDDING 144; symbols with usable
       embeddings 2 of 49.
   (Earnings were plentiful — the earlier "no reports" reading was
   WRONG and is corrected here.) Zero live decay ops exist: all 85
   decay rows carry trigger='shadow', 2026-08-11..14.
   THE SILENT-FAILURE SHAPE: the skip at `if best is None: continue`
   has NO stat key, so the pass reports success with zeros and no
   reason — the same shape as the NaN incident (run completes,
   output empty).
   GATE IMPACT: the Phase 2 decay-tail precondition (NARRATIVE_SPEC)
   is BLOCKED — unsatisfiable until embeddings are restored for new
   filings. Waiting for the October wave does NOT fix it.
   NOT ACTIONED (Edmund 2026-09-05): step 5 stays parked,
   stock_theme_alignment stays frozen, Phase 2 stays shut. Scope note
   for a later sitting is recorded in NARRATIVE_SPEC.

6. **processed_at is vestigial — retire it.** Full-audit finding
   2026-08-11: the huge processed_at NULL counts are NOT unprocessed
   content. Real coverage metrics are healthy: 8-Ks 100% llm_analysis
   within 30d; 10-K/Q and transcripts are themed (0 unthemed in 14d),
   and llm_analysis was never their channel. processed_at is written
   only by legacy paths (analyzer.py, events.py). Drop or stop reading
   it; it misleads audits (it misled this one).

6b. ~~theme_extraction has no prompt caching~~ CORRECTED 2026-08-11
   (user challenge): 0% cache is STRUCTURAL, not a miss — instructions
   are ~220 tokens (cache minimum 1024; padding costs more than it
   saves) and the spend is dominated by unique filing text, uncachable.
   The original cost audit adjudicated this correctly; the 2026-08-11
   audit note briefly mislabeled it as free savings. Real cost lever if
   ever needed: theming BREADTH (830-symbol universe) — but narrowing
   blinds narrative discovery; methodology call, user-only, not
   recommended.

6e. **Yahoo refresh still writes legacy TTM margins into the
   fundamentals snapshot** (fundamentals.py ~137-141). Harmless today
   — scorer/assessor take margins from canonical FMP tables and the
   sync overwrites — but it is a mixed-definition trap for any future
   snapshot consumer. Stop writing gross/operating/net margin from the
   Yahoo path; canonical owns statement-derived fields.

6c. **LIVING NARRATIVES — SCOPED 2026-08-11 (user: "the whole point is
   that it should be living and breathing"). Supersedes the narrower
   checkpoint-inflow question; user answered YES and went further:
   narratives must absorb everything — calls, 8-Ks, 10-K/Qs —
   continuously.** Design, in dependency order:
   a. **Post-birth prediction minting**: new typed claims on EXISTING
      company narratives mint checkpoints (not only at birth). Feed:
      earnings_claims (extractor re-wired 2026-08-11) mapped to the
      company's narrative; dedupe against open checkpoints; cap per
      narrative per quarter. This alone makes dossiers breathe.
   b. **Thesis amendments, evidence-cited**: when a narrative
      accumulates K new evidence rows or a checkpoint resolves, an
      update judge amends the thesis — versioned into thesis_history,
      each amendment citing the evidence rows that drove it (grounding
      discipline as in P2). Never silent rewrites.
   c. **Sector/macro narratives breathe too**: weekly evidence digest
      per narrative (child exposures' ledger ops + filing themes) into
      the same amendment judge. Macro theses currently only change at
      lifecycle events — that is the "static meta-narrative" the user
      rejects.
   d. **Falsification sweep**: kill conditions checked against fresh
      evidence every weekly pass; hits force momentum = decelerating
      and open a lifecycle review.
   **CORROBORATION PRINCIPLE (user, 2026-08-11 — governs all of the
   above):** one company reporting something new is NEVER a narrative
   event above company scope. A new narrative is born — or an existing
   one develops up or down — only when a NUMBER of companies say
   similar things in a similar direction. Single-company signals feed
   that company's own dossier and count as ONE vote toward any broader
   narrative. Mechanically: sector/meta thesis amendments and births
   require evidence from >= B distinct companies within the window
   (B calibrated per tier — higher for metas than subsectors); the
   momentum measure (#3) likewise requires breadth — ops from >= M
   distinct symbols, so one company's repeated ledger activity cannot
   move a narrative's momentum alone.
   Cost bound: (a) event-driven off claims (cheap); (b)+(c) batched
   weekly. Depends on: claim extractor (live), momentum #3 above.
   Sequencing: (a) first — it unblocks the product dossier page.

6d. **qual_assessor cache share is 53.6%, not the ~85% hoped.** The
   warm-up fix works within a run, but runs are spaced further apart
   than the cache TTL, so cross-run misses are structural. Either
   accept (cost is ~$1.4/day) or restructure prompts; recalibrate the
   expectation in any case.

7. **OZK filing-mapping** still open (chunk-3 exclusion note).

8. **Assessor cache hit rate** — verify the warm-up fix moved ~55% to
   ~85% in llm_usage after a week of runs (check ~Aug 16).

20. **GROWTH INPUTS LAG THE FILING BY WEEKS — the ACM class
    (found 2026-09-06; confirmed by external review against the live
    DB; real money was on it). NOT FIXED. Owner: a freeze sitting
    Edmund opens; no build, no push before that.**
    WHAT HAPPENED: ACM's 10-Q and call were ingested 2026-08-11 (the
    8-K with the $337M charge on 08-10). The wire had them the same
    day; the assessor read them 08-11 and held Strong Buy. The QUANT
    score kept gem ~5.15 through 2026-09-05. On 2026-09-06
    revenue_growth_yoy = -0.1418 and earnings_growth_yoy = -1.4794
    appeared, the both-shrinking 0.5x penalty fired, gem 2.57, off
    the board — 25 days after the filing.
    WHY: revenue/earnings/FCF growth come from Yahoo's quarterly
    statement tables (pipeline/fundamentals.py `_quarterly_trends` →
    `_yoy_growth`, info-field fallback), NOT from the filing text we
    already hold and NOT from FMP, which on 2026-08-09 was declared
    owner of "what companies report". Everything statement-based was
    moved to FMP except the quarterly block — the two values that
    decide the growth penalty were left on Yahoo, unlisted. Yahoo
    published ACM's June quarter between our 09-05 and 09-06 morning
    fetches. FMP had it stamped fillingDate 2026-08-10 (checked live
    09-06; SEC XBRL also had it 08-11). freshness_sentinel checks
    MAX(fetched_at) only — a fresh fetch of a stale quarter is "fresh".
    The 22:00 dirty-symbol re-fetch (step 3d) re-fetches Yahoo, so it
    re-fetched March numbers on 08-11.
    SCALE (offline diff 2026-09-06, FMP quarter vs stored, growth
    multiplier only): 831 symbols; 46 multipliers change (29 harsher,
    17 softer); 156 differ >2pts on revenue growth for the SAME
    quarter (two vendors, two definitions of net income — ES: Yahoo
    earnings +10%, FMP -85%; INTU: +9% vs -5%). Board: ES, INTU, BDX
    would fall below the exit line; DTE, ZTS, EMN would enter as Buy,
    CMI as Watch; CSL's grace seat would end. 11 symbols' stored
    quarter still older than their latest 10-Q on 09-06 (GATX, CMI,
    LNT, AEIS, BEN among them).
    THE SITTING (scoring-input change — freeze ritual, before/after
    board diff incl. margin-trend and FCF-trajectory effects, Edmund's
    sign-off, push with him at Railway):
    a. Re-home the quarterly block (dates, revenue, gross/op margin,
       net income, FCF) onto FMP quarterly income + cash-flow
       statements for ALL symbols; growth computed from it; Yahoo
       only when FMP returns nothing. Align income/cash-flow by
       position not date (52/53-week filers: ACM 06-30 vs 07-03).
    b. Store provenance on the row: source, quarter end, filing date.
    c. Sentinel: per symbol, quarter in the score vs latest 10-Q/10-K
       on record, against the stated latency in DATA_SCORECARD.md;
       breaches named in the daily brief.
    d. Prove, in the sitting, on a company that filed that week, that
       the filed quarter is in the score's inputs the same evening.
       Prove FMP had ACM's June quarter on/near file day (fillingDate
       2026-08-10 shown live 09-06 — re-show it in the sitting).
    OUT OF SCOPE FOR THIS ARC: redesigning the one-off vs structural
    growth penalty; embeddings/decay/Phase 2; replay; backfill.
    STATUS 2026-09-07 — BUILT, GATE PRESENTED, NOT PUSHED (freeze
    sitting 2026-09-06 evening + 2026-09-07). (a) pipeline/fmp_quarterly.py
    re-homes the block (income + cash-flow by position; Q vs Q-4
    positional growth; 2 FMP calls/symbol, 4 workers); scheduler daily
    2a + weekly 2a (full universe) + 22:00 step 3d (just-reported);
    fundamentals.py writes the block only while growth_source != 'fmp'.
    Applied on the LIVE DB 2026-09-07 10:15–11:17 UTC: 830/831 rows
    source=fmp (GLD: FMP and Yahoo both empty — an ETF). (b) provenance
    columns growth_source / growth_quarter_end / growth_filing_date
    (FMP fillingDate — a VENDOR STAMP, not the SEC date) /
    growth_fetched_at, mirrored as `_provenance` inside the JSON.
    (c) sentinel per-symbol growth_quarter check — keys on quarter end
    vs the latest 10-Q/10-K (>95d behind = not the filed quarter; 3d
    latency), after the first cut on fillingDate false-alarmed NUE /
    MDLN / PNFP; open at build: GLD only. (d) PROVED: ACM FMP income
    fillingDate 2026-08-10 16:35 (cash-flow 08-11); live row quarter
    2026-06-30 rev −14.18% earn −166% (Yahoo had −148%: two vendors,
    two net-income definitions). This-week filers HPE / MDT / LULU
    (10-Q 2026-09-03): quarter 07-31 / 07-31 / 08-02, filing 09-03 in
    the score inputs. Yahoo guard proved on ACM: fetch_fundamentals ran
    11:17 UTC, growth fields and provenance untouched.
    BOARD DIFF (real scorer, mid2→after = #20 alone, same day): 0
    membership changes, 0 tier flips, 11 growth multipliers changed
    (7 harsher: CHWY CPT CTVA ILMN MDLN SYF UNM; 4 softer: CHE STWD
    TTEK VOYA). The 09-06 preview's 46 / ES-INTU-BDX exits / DTE-ZTS-EMN
    entries applied the raw growth rule; the live scorer's divestiture
    guard (233 flagged names incl. ES BDX DTE ZTS EMN CMI) and the
    narrative<0.40 gate (INTU 0.71, CSL 0.57) remove 33 of the 44 raw
    changes. 153 revenue-growth and 136 earnings-growth values differ
    >2pts from Yahoo's for the same quarter; 34 earnings signs flip.
    FMP quarter newer than Yahoo's for 75 names (GATX CMI AEIS PATH
    DOCU TTC a full quarter ahead), same 675, "older" 73 — all date
    convention (69 ≤7d; AZO COST PEP DPZ 16–22d are Yahoo month-end
    rounding of 52/53-week quarter ends). PROD STILL YAHOO until the
    push; until then the 06:00 UTC daily rewrites the values while
    growth_source reads 'fmp'.

21. **historical_metrics IS BROKEN — value score's TTM revenue (P/S
    leg) dead since spring (found 2026-09-06; confirmed by external
    review). NOT FIXED. Same sitting as #20 or its own; no build, no
    push before Edmund opens it.**
    hidden_gem_scorer's value pass reads TTM revenue as the lateral
    SUM of the last 4 historical_metrics rows. The weekly refresh
    (scheduler step 6, pipeline/fmp_historical.py, FMP key-metrics +
    income-statement quarterly) upserts ON CONFLICT (symbol, date) —
    and the live table has NO unique constraint on (symbol, date)
    (only NOT NULLs + ix_hm_symbol; the Railway migration dropped it,
    the 2026-07-05 constraint repair missed this table). Friday
    2026-09-04's weekly log: every one of 827 symbols failed with
    "no unique or exclusion constraint matching the ON CONFLICT
    specification". MAX(date) = 2026-05-10 (~119 days). ACM has ZERO
    rows; ~334 of 831 symbols have none — their P/S leg is scored as
    "no data". FMP itself returns the June quarter fine (checked live).
    env_diagnostics has recorded the freshness violation
    (historical_metrics age ~117-119d vs max 115) on every run since
    2026-09-04, including 09-06 — and this desk's board readouts that
    week did not read it back to Edmund. Swept all 29 ON CONFLICT
    targets in the codebase against the DB: this is the only broken
    one.
    THE FIX: restore UNIQUE (symbol, date) (dedupe first if needed);
    re-run the refresh for the universe; cut the sentinel max age
    from 115 days to 10 (weekly table); prove ACM and a board sample
    have current TTM revenue; before/after board diff (P/S leg moves
    for all 831).
    STATUS 2026-09-07 — APPLIED ON THE LIVE DB 2026-09-06 13:43 UTC,
    code local, GATE presented, NOT PUSHED. UNIQUE (symbol,date)
    `_hm_symbol_date_uc` re-asserted (0 duplicate pairs), fetched_at
    column added and stamped on every touched row, upsert switched to
    ON CONFLICT DO UPDATE; full-universe refresh: 828 symbols, 7036
    rows, 0 errors; 827/831 with rows (missing OZK ASND CHKP GTLS GLD —
    zombie/stale-price names); MAX(date) 2026-08-02; ACM 20 quarters
    through 2026-06-30, TTM revenue 15.39B. Upsert re-proved
    2026-09-07 on 10 symbols: 200 rows, 0 errors, counts unchanged,
    fetched_at moved. Sentinel: 10d on MAX(fetched_at) + 60d on
    MAX(date) (was 115d on date). CORRECTION: the live consumer is NOT
    the P/S rank — compute_value_score has no caller (score_all_stocks
    takes value from quality_v3.value_v3). historical_metrics feeds
    compute_gap_score's multiple_inertia (pe_ratio now vs 12m ago,
    roic/op_margin trend), 30% of the gap → priced-in multiplier.
    BOARD DIFF (real scorer, before→mid = #21 alone, same evening):
    27 names moved ≥0.2; ES 3.66→3.21 (Buy→off, above the exit line),
    EXC Buy→Watch, FTAI Strong Buy→Buy, INTU Buy→Watch, BSY Watch→Buy;
    CW / MORN / XYL enter as Watch. All via gap_score / priced_in; 328
    names gained rows they never had. DATA_SCORECARD corrected.

22. **PROCESS: coherence and oversight failures, encoded as hard
    rules + a living inventory (Edmund 2026-09-06). RECORDED —
    CLAUDE.md "Data integrity AND data coherence" section +
    DATA_SCORECARD.md (new). Rules: one owner per scoring fact; every
    scoring input listed field → source → expected latency → consumer;
    known latency allowed, undiscovered latency is an incident;
    fetched_at ≠ content current, alarm on quarter/filing mismatch by
    symbol; vendor re-homes list every field moved or explicitly left;
    after any data-path change prove a this-week filer's quarter in
    the score inputs; status/board readouts MUST read back open
    freshness violations — silent green while a source is red is
    forbidden.**
    Also logged in the scorecard: roe and debt_to_equity are written
    DAILY by the Yahoo fetch (fundamentals.py 296/305) and WEEKLY by
    the FMP canonical sync — the same field alternates vendors within
    a week. Not LIVE scoring inputs today (verified 09-06: roe is
    selected by the quality query but unused; debt_to_equity feeds
    only score.py, whose callers are off the scheduler path), but a
    live example of the rule being broken; resolve in the #20 sitting.
    RESOLVED IN CODE 2026-09-07 (with #20, not pushed): fundamentals.py
    no longer writes roe or debt_to_equity; the FMP canonical sync is
    the only writer. Prod's Yahoo writer stays live until the push.

23. **GAP HONESTY — sitting 1 (A + B). Grok rulings locked 2026-09-08,
    pasted 2026-09-10. NOT BUILT. Opens only when Edmund opens it; no
    score math; one push when Edmund says, at Railway.**
    THE CASE (closed): INTU Buy→Watch on 2026-09-07 was caused by the
    V3 #21 historical_metrics repair landing on a seat partly built on
    a stale cross-quarter P/E (Apr-26 8.75 vs Jul-25 144.33 → after
    repair Jul-26 58.97 vs the same Jul-25). multiple_inertia 0.970 →
    0.796 is the entire gap move (0.7909 → 0.7387); price_lag 1.000
    both days (saturated), narrative_momentum 0.0 both days (parked
    table). No price input changed — last INTU close 2026-09-04
    $332.70, Labor Day 09-07. Scorer code not in ef825ee. The sitting
    DIFF listed INTU (DIFF_20260907.txt line 7). The evening report
    still wrote "the market catches up" because daily_report.py VOICE
    hard-wires "priced_in UP = the market caught up" and only forces
    the "our measuring stick changed" language when the LEADING cause
    is a quality or value re-reading — never for priced_in.
    platform_notes id 6 (active 09-07 → 09-14) DID name the
    historical_metrics repair and said priced-in readings would shift
    ("that is our measuring stick, not the market") — the note was
    adequate; the VOICE rule was the gap. Grok's ruling accepted with
    that one correction.
    A — pipeline/daily_report.py: per moved symbol, pass the writer
    input-change flags since the prior snapshot: new close y/n;
    growth_quarter_end / growth_source changed; historical_metrics
    latest date changed; narrative rows changed. Prompt rule: "market
    caught up / backed off" ONLY when a price input changed; otherwise
    plain words that our data was updated/repaired and the corrected
    figures moved the reading. platform_notes row mandatory for every
    data-path deploy, naming WHICH measurement paths changed (growth,
    HM/P-E, sentinel, …); the measuring-stick rule must bind priced_in
    and gap leads, not only quality/value.
    B — pipeline/freshness_sentinel.py + DATA_SCORECARD.md: per board
    name, latest historical_metrics quarter vs latest 10-Q/10-K on
    record against a stated latency; breaches named in the brief.
    Scorecard rows for the three gap inputs: (1) eod_prices + live SPY
    fetch (+ median-fallback health); (2) historical_metrics P/E path
    + fundamentals_history annual ROIC/op-margin; (3)
    stock_theme_alignment — parked/frozen until embeddings revive.
    Preferred if cheap: snapshot price_lag / multiple_inertia /
    narrative_momentum per name so the report can name which piece
    moved without reverse-engineering.
    OUT OF SCOPE: any compute_gap_score math; TTM P/E; ±30 band /
    tanh; Phase 2 decay / re-embed.
    REPORT BACK BEFORE CODE: exact flag schema for A, latency bar for
    B, scorecard row text.

24. **GAP MATH — sitting 2 (C + D), FREEZE. Grok rulings locked
    2026-09-08. NOT BUILT. Full before/after board DIFF; Edmund GATE.**
    C — hidden_gem_scorer.compute_gap_score multiple_inertia: replace
    FMP quarterly P/E (price ÷ QUARTERLY EPS — seasonal; INTU 8.75 /
    59 / 144 across quarters with no re-rating) with TTM P/E from the
    same table: market_cap ÷ Σ(last 4 quarters net_income), now vs
    ~12 months ago. Seasonality-free, no new vendor. NOT the weaker
    same-fiscal-quarter compare as primary. Fallbacks: negative TTM
    earnings → no P/E (existing lean-away path); <4 quarters → same;
    never annualise one quarter. Market cap must align with the
    quarter window summed.
    D — price_lag ±30 saturation: SOFT CURVE (tanh / diminishing
    extremes), NOT widen-to-±50 (that raises falling-knife credit).
    Keeps a ceiling, still registers direction past ±30. Every name's
    gap re-scores → full DIFF.
    REPORT BACK AFTER GATE: DIFF summary + names that flip solely from
    C or solely from D.
    STILL PARKED: embeddings NULL / decay Phase 2; narrative replay;
    growth-penalty redesign; INTU assessor override unless Edmund asks.

25. **OUTAGE 2026-09-09 23:24 → 09-10 14:09 UTC: self-deadlock on
    `fundamentals` took the site down ~14.7h. FIX WRITTEN 2026-09-10
    (local, not pushed): scheduler step 3d closes the Yahoo session
    BEFORE ttm_sweep / refresh_growth_block (matches daily step 2);
    fmp_quarterly.ensure_columns looks in information_schema first and
    returns without DDL when the four growth_* columns exist, else
    ALTERs under `SET LOCAL lock_timeout='5s'` and logs instead of
    hanging; fundamentals.py reads the log-line values BEFORE commit
    (the post-commit `row.pe_trailing` touch re-opened a transaction
    nobody committed = the share lock the ALTER queued behind).
    Unblocked by Grok/Edmund: pg_terminate_backend(29877) at 14:09 UTC;
    /board 200 again. Wed after-close + Thu daily resumed overlapping;
    no manual clear.**
    **RECURRED 2026-09-14 23:43 UTC → 2026-09-18 12:28 UTC (~3.5 days
    down) because the fix (1da4983, written 09-10, "ready for push")
    was never pushed — no push was called and the desk did not chase
    it. Same pids pattern (idle-in-txn 37932 / ALTER 38043) in the
    Mon 09-14 after-close step 3d. Every scheduled job from 09-15
    06:00 onward was SKIPPED (wedged run counted as running): no
    prices, no snapshots, no editions for 09-15/16/17; the sentinel
    could not fire because it runs inside the wedged process — a
    silent-death mode the sentinel does not cover. Unblocked 09-18
    12:28 UTC by the desk on Edmund's "go" (pg_terminate_backend
    37932 → True; queue drained in <3s; /board 200). Both stuck runs
    resumed on OLD code; they re-score under today's date with
    09-14 prices until the pushed restart lets dead-run rescue run the
    09-18 daily. Track-record lots for 09-15..17 were never opened/
    filled — a real gap, not repairable by rescue. LESSON (rule for
    CLAUDE.md incident section): a written-not-pushed fix for an
    outage-class bug is an open incident with a deadline, restated in
    every readout until shipped; and the sentinel needs an
    out-of-process heartbeat (scheduler_runs finished_at age) checked
    by the API or an external ping.**
    FMP QUOTA — DESIGN NOTE ONLY (not built): on 09-08 and 09-09 the
    evening transcript step got HTTP 429 "Limit Reach" for every symbol
    (204 / 210 lines) — the new 06:00 growth sweep (2 calls × 831) plus
    existing FMP use exhausts the plan's daily quota by evening, so the
    FMP transcript fallback returned nothing (1 EARN_CALL row on 09-09).
    Proposed: refresh the growth block daily ONLY for symbols whose
    latest 10-Q/10-K/8-K-earnings on record is newer than their stored
    growth_filing_date (a handful per day), full-universe sweep weekly;
    put the transcript step's FMP calls ahead of bulk sweeps in the
    day's budget; record the plan's daily limit in DATA_SCORECARD and
    have the sentinel count 429s per run. Needs Edmund's plan tier.

26. **POST-OUTAGE RESILIENCE — Grok rulings locked 2026-09-19. Two
    parts. NO inventing 15–17 Sep boards/editions/lots — ever.**
    VERIFIED 2026-09-19 05:30 UTC: origin has the lock fix (c9fe7cd);
    /board 200, date 09-18; eod_prices 15–17 Sep ALREADY FILLED (823
    rows each — the weekly refresh caught them; no price backfill);
    18 Sep edition regenerated 01:54 UTC by the weekly on real closes
    (stale-edition delete moot); DB timeouts 0/0/0; single login role
    `postgres`; zombie scheduler_runs ids 82 (daily 08-08) and 228
    (daily 09-15) still open; leaderboard_history has no 15/16/17 Sep.
    TODAY — DONE 2026-09-19 06:12 UTC on Edmund's "go" (SQL shown
    first): role config now idle_in_transaction_session_timeout=10min,
    lock_timeout=30s (verified on a NEW connection; statement_timeout
    left 0); zombie rows 82 + 228 closed (finished_at 06:12); platform
    _notes id 7 inserted (15–17 Sep outage, active 09-15 → 09-22);
    /board 200 after. Settings bind new sessions only — the scheduler
    ORM pool and API pool pick them up at the next restart (R1 push).
    Items as executed:
    a. ALTER ROLE postgres SET idle_in_transaction_session_timeout =
       '10min' — both outages would have ended themselves.
    b. ALTER ROLE postgres SET lock_timeout = '30s' — DDL/readers fail
       loud instead of freezing the site.
    c. NOT statement_timeout on the role (single role; would kill the
       long Yahoo/FMP/LLM jobs) — API-only via connect_args in R1.
    d. Close zombies: UPDATE scheduler_runs SET finished_at =
       COALESCE(finished_at, NOW()) WHERE id IN (82, 228) AND
       finished_at IS NULL. Close, never delete.
    e. platform_notes row: 15–17 Sep outage — no snapshots/editions/
       lots those days; not a quiet market; prices recovered, scores/
       editions not and must not be backfilled. Active 09-15 → 09-22.
    f. Settings bind NEW sessions only: the scheduler's shared ORM pool
       (db/session.py) and the API pool keep old settings until the
       process restarts (next push = R1) or a manual Railway restart
       outside a slot — Edmund's call.
    SITTING R1 (one push when Edmund says push at Railway):
    - migrate-at-startup: ONE migrate() (under lock_timeout) holding
      every runtime ALTER TABLE / ADD COLUMN IF NOT EXISTS; run steps
      assume the schema. Inventory of sites listed in the R1 design.
    - deploy-gate lint: fail the push if ALTER TABLE / ADD COLUMN
      appears under run-step paths.
    - hung-run ceiling: daily / after_close / weekly each in a
      subprocess with a hard time limit; on timeout mark scheduler_runs
      failed and free the slot.
    - startup catch-up: newest FINISHED daily older than 30h → run one
      (covers the "slot never recorded" case the rescue misses).
    - session hygiene: every scheduler get_session() in try/finally or
      a context manager that closes; no post-commit ORM attribute
      reads. (expire_on_commit=False is NOT the primary fix.)
    - GET /health/platform: 503 if no scheduler_runs finish in 26h, or
      blocked readers on core tables, or board snapshot older than the
      last trading day. External monitor (UptimeRobot-class) set up by
      Edmund after it exists; desk supplies exact URLs.
    - fetch_prices days=2 → 7 at every scheduler call site.
    - optional --job daily CLI for one-command catch-up.
    - sentinel: exclude non-filers (ETFs, e.g. GLD) from the
      growth_quarter check.
    - include local docs commit 95a91a5; DATA_SCORECARD/V3 notes.
    OUT OF SCOPE R1: INTU A+B (#23), FMP quota, gap math (#24),
    embeddings/decay, separate DB roles (defer), any 15–17 Sep
    fabrication.
    R1 DESIGN BEFORE CODE: list every ALTER site moved into migrate();
    proposed time ceilings; exact /health/platform checks; price-window
    call sites.
    **R1 BUILT 2026-09-20 — LOCAL, NOT PUSHED. Awaiting Edmund at
    Railway + "push". Ceilings AGREED by Edmund 2026-09-20 ("don't
    raise them"): daily 240 / after-close 300 / weekly 360 min — above
    every legitimate run observed (daily p95 175; after-close p95 166
    in Aug, 340–547 in the FMP-429 week; weekly 145 on 09-18) and inside
    the next slot's start; Grok's 180/150/180 would have killed four
    legitimate runs in 45 days. One line to change.**
    What shipped (commit pending):
    - db/migrate.py — 50 steps: the 32 ALTER lines / 17 functions from
      the inventory PLUS 10 `CREATE INDEX IF NOT EXISTS` sites (the
      09-10 lock queue formed on idx_lh_date inside the archive step;
      non-concurrent CREATE INDEX takes SHARE even when the index
      exists), the track_lots constraint drop, historical_metrics
      UNIQUE, the two one-time UPDATE backfills, and the new
      scheduler_runs.status/error. Catalog-checked first → a migrated
      DB gets NO DDL. Prod DRY RUN: 6 would apply — the 2 new ledger
      columns and 4 indexes on filing_themes / stock_theme_alignment
      that were NEVER created on prod. Runs at scheduler start-up
      and via `python scheduler_light.py --migrate`. CREATE TABLE IF
      NOT EXISTS (32 sites) stays in steps — no lock on an existing
      table.
    - scripts/deploy_gate.py — DDL lint first, offline: any
      `ALTER TABLE` / `ADD COLUMN` / `CREATE [UNIQUE] INDEX` on a
      non-comment line under pipeline/, api/, scheduler_light.py
      blocks the push (db/migrate.py allow-listed). Clean now.
    - scheduler_light.py — every job runs as a CHILD PROCESS
      (`--job X --child --slot …`) under JOB_CEILINGS_MIN; parent owns
      the ledger; timeout → kill, status='timeout', slot freed. Harness
      (fake worker, fake ledger, no prod writes): ok / failed / timeout
      all PASS. Start-up: migrate → missed-slot catch-up → liveness
      rule (newest finished daily > 30 h → run one). `--job daily` CLI
      = recorded, ceilinged one-off. All 11 get_session() sites in
      try/finally; no post-commit ORM reads found in the modules they
      call. fetch_prices days 2 → 7 at the three sites.
    - pipeline/ — 17 functions no longer issue DDL (each carries a
      one-line pointer to db/migrate.py). ingestion.py FMP price writer
      RETIRED (eod_prices single owner: Yahoo, adjusted). GLD-class
      exclusion in the sentinel's growth_quarter check.
    - api/ — own engine (statement_timeout 15 s, pool_recycle 1800),
      GET /health/platform (200/503, checks named), api/trading_days.py
      (NYSE holidays 2026–27, due-from-01:00-UTC rule). Local verify:
      /health/platform 200 with correct payload, /board 200,
      SHOW statement_timeout = 15s on the API engine.
    OUT OF SCOPE — untouched: #23 A+B, FMP quota, #24 C+D,
      embeddings/decay, separate DB roles, 15–17 Sep data.
    POST-PUSH CHECKLIST: scheduler + api SUCCESS; start-up log shows
      "migrate: … 6 applied"; /board 200; /health/platform 200; 30-s
      lock watch clean; role timeouts 10min/30s on new sessions;
      external monitor set up by Edmund on the two URLs.
    THEN: Sitting 1 (#23) → FMP quota (#25 note) → Sitting 2 (#24).

## Standing gates (not fixes, reminders)

- Chunk 4 + ALNY/LITE/SNDK additions stay gated behind the board-size
  tripwire (>75 tiered -> proposal first).
- Watch-path isolation still unproven for web-only pushes (CLAUDE.md
  rule; the recent scheduler deploys were pipeline pushes, so no test
  yet).

10. **track_lots has no created_at/audit timestamps** — a row
    disappearance on 2026-08-15 was untraceable (end state verified
    correct, cause unknown). Add created_at DEFAULT now() + updated_at;
    never again an untraceable mutation in the record that judges us.

11. **assessed_tier provenance (BLOCKS the product's assessor badge).**
    Since the 2026-08-15 materiality corridor, assessed_tier can be
    written by three different mechanisms: a judge's conviction
    override, a corridor hold pending ruling, or a materiality-ruled
    hold. The column doesn't say which, so the product's "judgment
    raised it" badge would mislabel mechanism as conviction. Add a
    provenance column stamped at write time (judge / corridor_pending /
    materiality_hold) in apply_qual_tiers + apply_materiality_holds;
    expose via /board.

12. **Report writer must see the book everywhere (law-17 counterpart).**
    The UI now reconciles "no position" sentences against the scorecard
    (DESIGN_BRIEF law 17, user-adopted); the durable fix is upstream:
    the daily_report writer already gets position truth on MOVES
    (2026-08-10 fix) but coverage/top-story/other sections can still
    claim no position. Extend the position field to every section's
    facts so the UI regex becomes a belt, not the brakes.

13. **Corridor holds vs the board's raw-floor guard (found via the
    roster fix, 2026-08-16).** /board applies "an assessor verdict
    counts only while the raw score clears the Watch floor" (Aug 10
    rule); the materiality corridor (Aug 15) stamps holds whose raw
    score can sit BELOW that floor — the guard silently discards them
    (INTU: held Buy in the DB, absent from /board). Two rules written
    five days apart disagree about who wins at the bottom of the
    board. Decide precedence deliberately (freeze ritual — it changes
    board membership); until then the guard wins and holds below the
    floor are display-dead.
    Second worked example 2026-08-19 (CSL, found by Edmund comparing
    surfaces): raw 0.339 sits between exit (0.32) and entry (0.34) —
    the methodology's hysteresis grace seat keeps it on the board
    (stored tier Watch) and the assessor affirms Watch, so Streamlit
    shows it; /board's resolver recomputes tier_for(raw)=None and the
    guard drops the name entirely. The product board does not honor
    grace seats the methodology grants. Likely the same mechanism as
    the 35-vs-38 wrinkle (which stays visible, undiagnosed, per the
    standing brief). Still Edmund's precedence call — nothing changed.
    DONE 2026-08-20 (local, not pushed): Edmund ruled — seat wins above
    the exit line, guard kills below it (V3_13_PRECEDENCE_SPEC.md;
    freeze entry in V2_CONSIDERATIONS.md). board_membership.py resolver
    now rides the stored snapshot tier with a hard kill below
    BOARD_EXIT; both worked examples resolved: CSL back on /board
    (Watch 3.4, grace seat) and INTU's class of corridor holds honoured
    (INTU itself is below 0.32 today — correctly off). Mandatory
    offline diff: additions only, both expected classes, zero
    removals; flip-count stop condition (7/day, Aug 13-16) reported
    and signed off by Edmund ("Proceed"). Local /board 44 -> 46,
    non-flipped entries byte-identical. Commit 0bf2daf; hash also in the
    spec. Prod verify + 35-vs-38 outcome pending the next
    Edmund-attended push.

14. **Report masthead has its own board-membership definition (found
    2026-08-18 during the NaN incident).** daily_report._masthead
    counted board=36 the same morning /board showed 41. Third parallel
    definition of "on the board" (force rosters were the second —
    fixed 2026-08-16 via board_membership). Fix is the same pattern:
    the report generator derives membership/counts from the shared
    resolver, never its own query. Do alongside the daily_report
    bookkeeping-vs-real-move fix assigned in FRONTEND_SPEC (2026-08-18
    decision).
    DONE 2026-08-19 (local, not pushed): resolver EXTRACTED to
    pipeline/board_membership.py with an as_of date (per Edmund's A2
    correction — pipeline never imports api; api re-exports from the
    pipeline module); _masthead/_board_moves use board_membership(conn,
    as_of=edition_date); own COALESCE queries deleted. Local /board
    before/after the extract: byte-identical. Verified read-only vs
    prod DB: board=40, leaders top-3 ACM/GDDY/LDOS — identical to
    prod /board the same day. [Wording corrected 2026-08-19: an earlier
    note here mis-described the fix as importing from api/routers.]

15. **Filings-intelligence positivity skew (user observation 2026-08-20,
    CONFIRMED in data).** Last 30 days: trajectory 72% "accelerating"
    (962/1335) vs 7.5% decelerating; strength wildly top-heavy (mode =
    the 0.9-1.0 bucket, 36% of all filings; almost nothing below 0.6);
    tone 66% "confident"; 8-K impact 11:1 positive (795 vs 71). The
    extractor grades what management CLAIMS, and management always
    claims acceleration — same disease as "every macro accelerating =
    zero signal" (#3). The wire's display floor (strength >= 0.60)
    then hides the few weak ones, making the surfaced feed look even
    rosier. Protections that exist: believability/claims grading and
    checkpoint verdicts (real but slow — they accrue over quarters).
    WORKED DESIGN 2026-08-20 (Edmund: high effort, "not arbitrary in
    either direction"): see V3_15_STORY_GRADING_DESIGN.md — anchored
    evidence-cited strength bands, trajectory graded vs the company's
    OWN prior artifact, tone→groundedness (the "promotional"
    category), 8-K impact anchors. Percentile display and post-hoc
    deflation REJECTED as curves. NOTE: narrative_strength feeds the
    live scorer (call_vs_filing_gap) → full freeze ritual; and
    narrative_believability is EMPTY (0 rows) — the truthfulness
    protection is not operating; populating it is the companion
    build. Shadow sample ~$3 runnable now; 18-month re-extraction
    ~$150-200 quoted before any run. Awaiting Edmund's ruling.

16. **Edition date is midnight-unsafe + off-schedule regeneration
    (found 2026-08-21 via Edmund's SARO question).** Both scheduler
    call sites pass for_date=date.today() evaluated WHEN THE STEP
    RUNS: any invocation crossing/starting after 00:00 UTC stamps
    tomorrow's date onto yesterday's snapshots. Observed: an 00:39
    UTC invocation (likely dead-run rescue after a restart; logs
    rotated, trigger unproven) wrote an Aug-21-dated edition from
    Aug-19/20 snapshots — no moves section, SARO's entry missing
    from headlines while the board correctly flagged it New. Fix:
    derive the session date from the LATEST SNAPSHOT date (the data
    the diff actually uses), never wall-clock at step time; and log
    trigger + for_date + snapshot-dates on every generation (V3 #10
    audit-columns companion) so the next orphan is attributable.
    Self-heals nightly via DELETE+INSERT, so severity is
    hours-of-stale-headlines, not permanent corruption.
    BUILT 2026-08-21 (local, same conversation, per the incident-fix
    rule): latest_snapshot_date() in daily_report.py is the anchor for
    BOTH scheduler call sites (after-close step 8, weekly step F —
    whose friday calc mapped any Friday-daytime catch-up to the
    UPCOMING session, the exact 00:39 shape); generation audit line
    prints for_date + the two diffed snapshot dates + wall clock on
    every edition. Verified read-only: anchor returns 2026-08-21,
    audit pair [08-21, 08-20], SARO None->Buy in that diff. Rides the
    next push; tonight's 22:00 run still executes the OLD code (its
    wall-clock date is safe at 22:2x) and overwrites the orphan
    either way.

17. **DONE 2026-08-23 (the CRUS lesson — PEG conflict class).** The
    2026-07-22 ruling (vendor PEG primary, consensus fallback for
    MISSING values) left a hole: present-but-junk vendor values (CRUS
    9.35 -> implied 1.4%/yr vs delivered +26.6%) passed through with
    only a "(vendor)" tag, and the assessor INVERTED the reading
    ("not yet crediting growth"). Three-part fix, built in-conversation
    per the incident rule: (a) fundamentals.py vendor-write guard —
    a conflict-class vendor value never overwrites a consensus PEG;
    (b) peg_normalizer trigger extended — conflict-class vendor rows
    (implied <3%/yr while delivered >15%) recompute to consensus;
    (c) qual_assessor context now prints implied-vs-delivered growth
    with a CONFLICT tag and a PEG reading rule (high PEG never means
    unpriced growth). Applied to prod: 79 rows recomputed (56 updated,
    21 honestly nulled — consensus growth <=0 makes PEG undefined,
    incl. CRUS; 2 fetch-failed kept w/ flag); conflict class now ZERO.
    CRUS + CMC re-assessed through the machinery on corrected context:
    CRUS SB reinforced (no PEG lean), CMC Buy held. PEG confirmed
    absent from all scoring math — no rescore was needed.

18. **Deploy gate is more permissive than the written rule (found
    2026-08-25, harmless outcome).** CLAUDE.md rule 1 says never push
    DURING a slot (~50-min window); the gate actually blocks only (a)
    a live scheduler_runs row and (b) the 10 minutes BEFORE a slot
    start. A 22:25 push cleared because the run had finished at 22:20
    — correct in substance (nothing to kill), but inside the written
    window. Decide one way: harden the gate to block the whole
    nominal window, or amend CLAUDE.md rule 1 to match the gate's
    live-run semantics ("no push while a run is live or within 10 min
    of a start"). Edmund's call; the desk also re-learned to check
    the clock BEFORE pushing rather than lean on the gate.

19. **Some wire items still show a one-line stub instead of the full
    paragraph — add one retry before giving up (noted 2026-08-26,
    the Home Depot 10-Q example).**
    THE SITUATION IN PLAIN WORDS: when the machine grades a new
    filing, it also writes the 2-4 sentence "expanded narrative" for
    the wire. Before we display that paragraph we check its honesty:
    every number in it must also appear in the evidence the machine
    cited. If the check fails, we throw the paragraph away and keep
    the grade — showing NO paragraph beats showing an unverified
    number (Edmund's Sitting-2 rule). When that happens, the reader
    sees the old short one-liner instead (that's what happened to
    HD's 10-Q: grade 6.2 fine, paragraph discarded, stub shown).
    THE GAP: today the paragraph gets ONE attempt. If it fails the
    honesty check, we discard immediately — no second try. In the
    backfill this discarded 13-27% of paragraphs, so a visible
    minority of wire items will always be stubs.
    THE FIX (small): on a paragraph-only failure, retry ONCE with the
    instruction "rewrite using only the figures in your evidence
    list", then drop if it still fails. The honesty bar does not
    move — we just give the writer a second chance to meet it.
    WHERE: pipeline/narrative_extractor.py (extract_themes_v2's
    synopsis handling). Natural home: the V3 #15 close-out session.
    Cost: a few extra tokens on the minority of filings that fail.
