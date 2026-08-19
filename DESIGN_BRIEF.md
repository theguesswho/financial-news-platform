# Design brief — the product (web/)

Agreed 2026-08-10 in the methodology session. Binding on every page
phase of FRONTEND_SPEC.md. Change it only with explicit user sign-off,
recorded here.

**Revision 2026-08-15** — the mock suite (round 2) was reviewed and its
direction approved by the user ("This is looking really good"). This
revision records what that approval decided: the front door reverses to
the Board, the nav nouns change, and a set of surface laws that were
prototyped in the mocks become binding. Superseded sections are kept,
marked, and dated — they are history, not instructions.

## Identity

**A discovery instrument with a judgment layer.** By synthesising
narratives from SEC filings, earnings calls, and market data, the
platform unearths stocks the market is not fully appreciating, supplies
the underlying evidence, and stakes its own public scoreboard on the
calls. The user's framing: an investment tool, not a news site —
FASTgraphs ethos (one consistent analytical lens, applied identically
to every stock), different lens.

This is a product other people will use. Design for a first-time
visitor who has never heard our internal vocabulary — while keeping
every surface honest enough that a skeptic auditing our track record
finds nothing dressed up.

What the instrument's authority rests on, in order:
1. the consistency of the lens (same view for every stock, no cherry
   presentation),
2. the public track record (wins AND losses, vs the SPY twin),
3. the evidence trail (every judgment one click from its data).

## Layout law (applies to every page)

**Judgment first, evidence beneath, history always reachable.**
A page leads with what the instrument concludes, supports it with the
data that produced the conclusion, and never hides what it used to
believe (band history, past editions, closed positions).

## Navigation — DECIDED 2026-08-15 (four nouns; Board is home)

The front door is **The Board**. This reverses the 2026-08-10 decision
that made the narratives landing the front door (that section is kept
below, marked superseded). Reason recorded: the product's first screen
should be what the instrument concludes today — the calls, ranked —
not an essay about the lens. The lens is still first-class; it lives
one noun away and is reachable from every row.

1. **The Board** — `/`. The current opportunity set: ranked, tiered,
   grouped by call. Home.
2. **Forces** — the narrative lens: the directory of forces, each
   opening to its thesis, its on-board roster, and the covered names
   attached to it that do not have a call yet (the discovery surface).
3. **What changed** — the daily edition as instrument log: readings
   that moved, entries, exits, why. ("Edition" was considered and
   REJECTED as jargon.)
4. **Track record** — the public scoreboard: $100 lots vs SPY twins,
   wins and losses together. ("Book" was considered and REJECTED as
   jargon — it is trader-speak, and this is a first-visitor surface.
   "Book" may still appear as a small inline label on the masthead's
   own-vs-SPY line, where the Track record page is one click away.)

**Companies is not a nav noun.** The company page (`/companies/{symbol}`)
is reached by the masthead search over the whole covered universe, by
every company name on every surface, and by prev/next inside the page
itself. A nav item pointing at "pick a company" with no company chosen
is a dead end; the search box is the real door.

**Portfolio is not in the nav yet.** Owner-only, and undecided (auth) —
FRONTEND_SPEC Phase 7. It joins the nav when it exists, not before.

Events / Insiders / News Wire are NOT destinations — they dissolve into
the company page and What changed. (Unchanged from 2026-08-10.)

**AMENDED 2026-08-19 — FIVE nouns (Edmund himself, FIXPACK_2026-08-19
Session B).** News Wire becomes the fifth nav noun; the line above is
superseded for News Wire only (Events and Insiders still dissolve).
His words: "For News Wire, we'll have two places - alongside Board /
Forces / What Changes / News Wire / Trace Record" and "I then want a
News Wire pane on the right side of The Board, just like we have
currently for Forces. I think the News Wire pane should sit above
Forces. It would be a one line snipped." Order: **The Board / Forces /
What changed / News Wire / Track record.**

5. **News Wire** — `/wire`. The earnings/filings feed ONLY (the
   Streamlit reference set: earnings calls, 10-K/Q reports,
   high-impact 8-Ks). Board moves are What changed's content, never
   duplicated here; insiders stay off. Dated masthead + date archive;
   observed filing dates only; synopses are the machinery's stored
   ones or absent — never written at read time; nulls omitted;
   assessor stays dark (law 12 unchanged by this page).

**The Board's rail carries a News Wire pane ABOVE Forces** (same rail
component family): at most 5 one-line items, newest first, format
**SYMBOL  Company — headline snippet · date**. The headline is the
FILING's (never the daily-report writer's — the Today block of edition
headlines stays where it is), verbatim or cropped at a word boundary
with an ellipsis, never rewritten. Company names longer than ~18 chars
take a word-boundary short form; nulls omitted — a line shows what it
has. No scores, no tier badges in the rail (it is news, not a rating).
Every line links into /wire anchored at its item.

## Page architecture — DECIDED 2026-08-15 (AMENDED 2026-08-19: News
## Wire added as a sixth surface — see the nav amendment above)

The mock suite IS the design of record. Five surfaces:

- **The Board (home)** — one-line masthead (universe covered · on the
  board · tier dot counts · the count wrinkle in plain words · own-vs-
  SPY since the first lot, linked to Track record); TODAY: the three
  edition headlines with an "all N moves →" link; the ranked table
  grouped by call with filter tabs (All / Strong Buy / Moved); a right
  rail with the Forces directory (weight, company count) and a
  "Losing support" list.
- **Forces** — directory (weight · on board · covered · thesis clip)
  and `/forces/{id}`: thesis, on-board roster, then the attached-but-
  off-board tail ranked by exposure.
- **What changed** — the full edition from `/reports/{date}`: kicker
  with the change breakdown, date archive, grouped Downgrades →
  Exits → Entries → Upgrades → Also, full bodies, symbols linked.
- **Track record** — verdict header, the honesty paragraph, aggregated
  per-name rows expanding to the daily lots and their SPY twins.
- **Company page** — hero (name · call · score · rank · band strip ·
  STREET line · prev/next), evidence triptych, score components, the
  path (score + price with filing ticks), thesis, calls stack, and a
  right rail (Stories / Said / Inside).

## Surface laws — DECIDED 2026-08-15 (binding, all pages)

These were prototyped in the mock suite and are now rules. They exist
because each one is a way a surface could quietly lie.

1. **Hierarchy on any row or header: the call → the assessor only when
   it moved the call → the story.** The call is what we conclude; the
   assessor line is why it differs from the data; the story is the
   one-line reason. In that order, always.
2. **HOLD IS SILENCE.** When the judgment layer agreed with the data,
   the assessor column prints NOTHING. Never the word "hold", never a
   check mark, never "confirmed". A verdict that says nothing new must
   look like nothing. (Printing "hold" on 30 rows makes agreement look
   like activity, and buries the 3 rows where judgment actually moved.)
3. **STREET is labeled and never ours.** Analyst counts, ratings, and
   targets appear under an explicit "Street" label, visually quieter
   than our own numbers. We never merge a consensus figure into our
   call, and we never present one unlabeled.
4. **Mention-set rule.** A peer set with `peer_count ≥ 100` is a
   MENTION set — companies that cite the story, not proven
   beneficiaries — and must be labeled as such wherever its multiple
   is shown. The hero gap on a company page picks the SMALLEST-n
   priced set (the most specific peer group), not the biggest number.
5. **No unsourced numbers, ever.** If a figure has no field behind it,
   it does not appear. (Concrete precedent: the sketch's "63 candidates
   in review" was cut — there is no sourcing field for it. Inventing a
   plausible number is the one failure this product cannot survive.)
6. **Nulls are omitted, not dashed.** A missing value drops its row,
   chip, or sentence. No em-dash filler grids. "No data" and "zero"
   must never look alike.
7. **Band strip runs on the TIER DOMAIN [2.9, 5.8]**, not on the
   observed min/max of a name's history. A fixed domain means the same
   dot position means the same thing on every company, which is the
   whole FASTgraphs-ethos claim. The full history lives in the path
   chart below it, which does use its own range.
8. **Movement stays on the row — and Moved means the CALL moved.**
   (Narrowed by the 2026-08-15 addendum, item 6.) NEW / tier moves /
   grace seat print in the row's Moved column, in the up-down role
   colors — not in a separate "what changed" widget. Rank ticks are
   NOT movement: a name can rise a rank on a downgrade day, and a
   green ▲1 would paint the downgrade as good news (the SANM case).
   The per-row band strip and the Q·V·G mini-bars from the Phase 2
   board row are DROPPED from the home table: the table is a
   directory of calls, and the evidence belongs on the company page
   where it has room to be read.
9. **Track record is aggregated first, losses at equal weight.** Per
   name first (invested, open/closed, beating, vs SPY), daily lots on
   expand. The honesty paragraph — that these are $100 paper lots, not
   live capital — sits above the numbers, not in a footnote.
10. **8-K tick rule.** Filing days that carry a transcript or a
    10-K/10-Q get a full tab in the calls stack; 8-K-only days compress
    to slim ticks — compressed, NEVER hidden. (The AECOM lesson: a
    $337M charge that no surface showed is how a wrong judgment
    survives.)
11. **Momentum orange is BACK IN RESERVE.** The 2026-08-10 landing put
    it into use for the word "accelerating"; that landing is retired
    and the token is unused again. It stays reserved until the
    methodology track recalibrates momentum into something that
    discriminates (today every macro reads "accelerating").
12. **The assessor ships DARK — entirely — until provenance exists.**
    (Extended by the 2026-08-15 addendum, item 5.) Since 2026-08-15
    `assessed_tier` is also written by the materiality corridor
    (corridor-pending and materiality-hold states), so a "▲ judgment
    raised it" badge would label a mechanical corridor state as
    human-style conviction. NOTHING assessor-flavored renders until
    the methodology track stamps provenance (judge / corridor_pending /
    materiality_hold) AND the API exposes it: not the raised/restrained
    badges, not "narrative promoted", not upgrade/downgrade direction
    words, not an Assessor column at all. Hold remains silence. This
    is a hard gate, not a preference — see FRONTEND_SPEC roadmap
    step 2.
13. **One since-date, derived, never copied.** (Sharpened by the
    2026-08-15 addendum, item 2.) The masthead and the Track record
    page both date from the FIRST LOT — computed as
    `min(scorecard.lots[].lot_date)`, currently 27 Jul 2026 — never
    from `masthead.since` (which says July 23, the signal start).
    The whole Book line on the masthead draws from the scorecard:
    its returns, its open-lot count, its first lot. Closed count is
    `scorecard.closed_lots`, never `masthead.closed`. The signal
    start may appear only as a footnote where it is explained.
14. **Wrinkles stay visible.** Where two of our own counts disagree
    (today: the edition masthead says 35 on the board, the snapshot
    has 41 rows carrying a call), the surface SAYS SO in plain words
    rather than picking the flattering number. Diagnosing the why is
    the methodology track's job; hiding it is not an option.

## Addendum — localhost review, ADOPTED 2026-08-15 (user decision;
## item 4 adopted as written over Claude's objection)

Source: CLAUDE_UI_ADDENDUM.md (external review of the running mocks).
All ten items adopted and BUILT the same day. Beyond the law
amendments above (8, 12, 13), these are now binding:

15. **Quality evidence is the durability road, never a revenue road.**
    (Amended by user 2026-08-15, same day: not a single FY-vs-TTM
    pair — each metric gets a ROAD.) Quality is durability — ROIC,
    operating margin, FCF margin — not size. Every company gets the
    same chart: per metric, up to FIVE fiscal years of bars (labeled
    FY{YY} from `period_end`, so a Sep year-end is one FY, never a
    second calendar year) with TTM from fundamentals as the SIXTH
    bar, drawn in full ink so "now" reads apart from the history.
    One shared year axis across the three metrics; each metric row
    scales to its own range. Null values omit the bar (the slot
    stays); a metric with no values at all is omitted. Revenue is
    never charted in this pane. (Supersedes the "revenue road +
    margin road" evidence-pane composition below, kept marked
    superseded.) FY FCF margin is fcf/revenue from the same annual
    row.
16. **One clock.** Board surfaces (table, counts, company as-of) run
    on `/board`'s date; TODAY and What-changed run on the edition's
    date; when they differ each surface is stamped with ITS date
    (the newspaper lags the board and says so).
17. **Never contradict the book.** If the scorecard holds open lots
    in a name, no surface prints "we don't hold a position" for it —
    the sentence is replaced with the open-lot fact, for every
    symbol, every edition, no special-casing. (User decision
    2026-08-15: applied in the UI as written; the report writer
    seeing the book remains a methodology-track item.)
18. **Company chrome:** prev/next stepping is its own labeled
    control, never in the phrase carrying this name's call and score;
    gauges come from fields (`components`, `fundamentals`,
    `priced_in`, prices, `analyst_*`), never restated from assessment
    prose; call tone/trajectory/strength print only when the value
    DIFFERS across the company's calls; claims appear ONCE (in the
    calls stack, against their call date — no Said rail); the value
    pane asks "is it cheap against this set?" (never "the same
    story"); one gap word per pane — `priced_in` on the narrative-gap
    pane, the 10-pt Gap on its component bar, and `ng_score` is not
    printed as a third figure.
19. **The pulse charts observed weeks only.** Backfill (seeding)
    weeks from the ledger's opening sweep are acknowledged in the
    footnote, never drawn — their bars would dwarf and re-scale the
    real weeks. No momentum word until the shadow column earns it.

## Landing page — SUPERSEDED 2026-08-15 (was: the narrative lens)

Kept for history. This described the narratives-as-front-door landing
built in Phase 2b (`/narratives/landing` + the old `app/(site)/page.tsx`).
The front door reversed to the Board on 2026-08-15; the work lives on
as the Forces directory and the force pages, and the four questions
below still describe what a force page should answer.

> 1. **The forces we believe in** — the leading narratives, each with:
>    how many companies gave rise to it / carry exposure to it (counts
>    are evidence of breadth, show them), its exposed board weight, and
>    one plain-words thesis line.
> 2. **Emerging narratives** — what the instrument is starting to see
>    (emerging/candidate tier): name, age, companies attached so far.
> 3. **Shifts and weakness** — narratives losing support, honestly
>    shown: drawn from the exposure LEDGER (weaken/remove ops, misses,
>    declining lifecycle status) — NOT from the momentum word alone.
>    Honest-surfaces rule applies: weakness gets equal visual weight.
> 4. **The bridge to the Board** — each narrative links to its stocks.

The ledger-derived weakness rule (3) survives the reversal: the home
rail's "Losing support" list and any force-level weakness claim use the
LEDGER, never the momentum word.

## The signature view (design centerpiece)

One visual, identical for every stock, that collapses the methodology
the way FASTgraphs' chart collapses theirs. It must show at a glance:
- **Quality** — is this a durable business (trend-fit, the 10y road)
- **Value** — is it fairly priced against true peers (shrunk percentile)
- **Narrative gap** — how much story the price ignores (exposure × (1−P))
- where the composite sits vs the tier bands, and its recent path

Every company page leads with it. (2026-08-15: the BOARD is no longer
this view collapsed to a row — see surface law 8. The Board row carries
the call, the score, and movement; the signature evidence lives on the
company page.)

## Signature view — DECIDED (user, 2026-08-10, Phase 2 lab)

Live variants A/B/C, then refinements B1/B2/C1/C2, were built against real
data at web/app/signature (route kept as the design lab). The pick:

- **The Board row = C1, the position row** — rank · company · tier chip ·
  band strip (zone washes, today's dot) · quality/value/gap numbers with
  mini-bars · score — **with C2's movement language integrated**: a
  compact what-changed cell (NEW badge, ▲/▼ rank moves in up/down colors,
  "▲ raised from Buy" tier moves, grace-seat note) driven entirely by
  fields /board already returns.
  **AMENDED 2026-08-15:** the movement language and the tier chip are
  kept; the per-row band strip and the Q·V·G mini-bars are dropped
  (surface law 8). The home row is name-first: rank · name/symbol ·
  call · score · assessor (silent unless it moved) · moved · story.
- **The Companies dossier hero = B1, the triptych with the band ruler**
  (state + 30-reading trail), carrying the company toggle: dropdown over
  the board in rank order + prev/next arrows. **BUILT 2026-08-15** in
  the company mock, with the band ruler on the fixed tier domain
  (surface law 7) and prev/next over the board in rank order; the
  dropdown was replaced by the masthead's universe search, which
  reaches all ~828 covered names rather than only the board.
- **Evidence panes** (user note, direction agreed): Quality = revenue
  road + margin road (separate micro-rows, never dual-axis) + ROIC /
  FCF-margin chips; Value = P/E fwd AND EV/EBITDA dumbbells vs the
  NAMED narrative peer set ("vs 135 companies in the same story: …");
  Narrative gap = top 2–3 narratives with alignment + trajectory above
  the exposure/priced-in bar. **BUILT 2026-08-15** in the company mock
  and approved in direction, with the mention-set label and smallest-n
  hero gap added (surface law 4). FCF-margin chips are NOT built —
  the field is not on the annual rows the API returns; add only if the
  data exists (surface law 5).

## Design tokens — LOCKED (Phase 2, from the chosen variants)

Defined in web/app/globals.css as CSS custom properties (light + dark via
prefers-color-scheme). Three color roles, never cross-used (standing rule):

- **Tier (conviction)** — one blue, ordinal by depth; validated for CVD
  + lightness monotonicity in both modes (dataviz validator):
  light: Strong Buy #104281 · Buy #2a78d6 · Watch #86b6ef
  dark:  Strong Buy #9ec5f4 · Buy #3987e5 · Watch #1c5cab
  Band-zone washes: these fills at 0.13–0.18 opacity. Tier chips: white
  (light mode) / surface text on the tier color, uppercase 11.5px bold.
- **Up/down (direction of change)** — light #006300 / #d03b3b,
  dark #0ca30c / #e66767. Used for rank/tier movement arrows, deltas,
  and the dashed exit line at 3.2. Never for tiers.
- **Momentum (narrative trajectory)** — RESERVED orange, light #eb6834 /
  dark #d95926. Currently UNUSED (surface law 11); never for tiers or
  deltas.
- **Narrative-gap accent** — violet, light #4a3aa7 / dark #9085e9: the
  "unpriced story" highlight only. Also carries "narrative promoted".
- **Ink & chrome** — page #f9f9f7/#0d0d0d, surface (cards) #fcfcfb/#1a1a19,
  ink #0b0b0b/#ffffff, ink-2 #52514e/#c3c2b7, ink-3 #898781 (both),
  hairline #e1e0d9/#2c2c2a, baseline #c3c2b7/#383835.
- **Type** — Geist Sans throughout; numerals tabular (`.num`) wherever
  they align in columns; scores 1dp on the 10-point scale. Editorial
  vocabulary from the report page: `.kicker` = 11.5px uppercase,
  0.14em tracking, ink-3, weight 600. Headline 26–28px bold tight;
  body 13–14px; captions 11–12px ink-3.
- **Anatomy** — cards: surface, 1px hairline border, 12px radius
  (rounded-xl), 24px padding. Tables: hairline row separators, kicker
  column headers, generous 20px column gaps. Charts: marks in ink,
  1.5–2px lines, washes for zones, direct labels over legends.
- **Page frame (added 2026-08-15)** — max width 1280px, 24px gutters;
  main/rail split `minmax(0,1fr) 300px` collapsing to one column below
  the xl breakpoint. Section rules: a 1px ink rule under a kicker opens
  a section; hairline rules separate rows inside it.

## Open design decisions

- **Product name / masthead identity** — still open, still blocking
  anything public. The mocks use "THE BOARD" as the working wordmark;
  it is a placeholder, not a decision.
- **Empty / loading / error states** — not designed yet; the mocks
  skipped them. They get designed and built in roadmap step 2 (they
  are the difference between a demo and a product).
- **The force-page pulse** — force pages currently show a portrait
  (thesis + roster). The living-narratives claim needs the health
  series (conviction week by week) from `narrative_health_history`;
  its chart form is undesigned and lands with the endpoint.
