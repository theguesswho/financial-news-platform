# Design brief — the product (web/)

Agreed 2026-08-10 in the methodology session. Binding on every page
phase of FRONTEND_SPEC.md. Change it only with explicit user sign-off,
recorded here.

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

## Navigation — five nouns, tool-shaped
(front door REVISED 2026-08-10, user decision — see Landing page section)

1. **Narratives** — FRONT DOOR. The lens is the product's identity:
   FASTgraphs is the graphs; we are the narratives. Landing = the
   narrative state of the world, broken down (see Landing page below),
   flowing into the Board. The three-layer map (forces / what moved /
   library) lives here as the deep view.
2. **The Board** — the current opportunity set: ranked, tiered,
   countdowns visible. One click (or one scroll-bridge) from landing.
3. **Companies** — the workbench. Point the instrument at any covered
   name; get the same signature view every time. Events, insider
   activity, and filings appear HERE, inside the dossier, where they
   have context.
4. **What Changed** — the daily edition as instrument log: readings
   that moved, entries, exits, why.
5. **Portfolio** — capital against the instrument's output. (Owner-only
   feature initially; a per-user feature if the product gets users.)

Events / Insiders / News Wire are NOT top-level destinations — they
dissolve into Companies and What Changed.

## Landing page — the narrative lens (user decision 2026-08-10)

The landing page showcases WHAT THE SYSTEM IS: narrative synthesis.
It must answer, in order, for a first-time visitor:

1. **The forces we believe in** — the leading narratives, each with:
   how many companies gave rise to it / carry exposure to it (counts
   are evidence of breadth, show them), its exposed board weight, and
   one plain-words thesis line.
2. **Emerging narratives** — what the instrument is starting to see
   (emerging/candidate tier): name, age, companies attached so far.
   This is the "discovery is happening live" proof.
3. **Shifts and weakness** — narratives losing support, honestly shown:
   drawn from the exposure LEDGER (weaken/remove ops, misses, declining
   lifecycle status) — NOT from the momentum word alone (momentum
   currently reads "accelerating" across the board and carries no
   discriminating signal until the methodology track recalibrates it).
   Honest-surfaces rule applies: weakness gets equal visual weight.
4. **The bridge to the Board** — each narrative links to its stocks;
   a closing strip surfaces the top of the Board ("what these forces
   surface"), leading into the full Board page.

The full three-layer map (forces / what moved / library) remains the
deep view behind this landing. Momentum orange (reserved token) comes
into use here.

## The signature view (design centerpiece — get this right first)

One visual, identical for every stock, that collapses the methodology
the way FASTgraphs' chart collapses theirs. It must show at a glance:
- **Quality** — is this a durable business (trend-fit, the 10y road)
- **Value** — is it fairly priced against true peers (shrunk percentile)
- **Narrative gap** — how much story the price ignores (exposure × (1−P))
- where the composite sits vs the tier bands, and its recent path

Every Companies dossier leads with it. The Board is this view collapsed
to a row per stock. Phase 2 builds 2–3 live variants of it for user
selection before anything else is styled.

## Visual language

- Seed: the report page's editorial restraint — words before chrome,
  numbers with dignity, no dashboard clutter.
- Plain lexicon everywhere (standing rule): 10-point scores, direction
  words spelled out, zero internal jargon. A stranger must understand
  every label. Where a concept needs teaching (narrative gap), teach it
  inline once, briefly — never assume the reader knows our history.
- Honest surfaces (standing rule): losses, exits, and downgrades get the
  same visual weight as wins. No celebration framing. The track record
  page shows the twin comparison unconditionally.
- Tier colors, momentum colors, and up/down colors are three SEPARATE
  roles — never reuse one for another. Exact tokens (type scale,
  spacing, palette, table/card anatomy) get locked in Phase 2 from the
  chosen signature-view variant, then recorded here.

## Signature view — DECIDED (user, 2026-08-10, Phase 2 lab)

Live variants A/B/C, then refinements B1/B2/C1/C2, were built against real
data at web/app/signature (route kept as the design lab). The pick:

- **The Board row = C1, the position row** — rank · company · tier chip ·
  band strip (zone washes, today's dot) · quality/value/gap numbers with
  mini-bars · score — **with C2's movement language integrated**: a
  compact what-changed cell (NEW badge, ▲/▼ rank moves in up/down colors,
  "▲ raised from Buy" tier moves, grace-seat note) driven entirely by
  fields /board already returns.
- **The Companies dossier hero = B1, the triptych with the band ruler**
  (state + 30-reading trail), carrying the company toggle: dropdown over
  the board in rank order + prev/next arrows. Built in Phase 3 at the top
  of the company page.
- **Evidence panes need a data pass before Phase 3 ships them** (user
  note, direction agreed): Quality = revenue road + margin road (separate
  micro-rows, never dual-axis) + ROIC / FCF-margin chips; Value = P/E fwd
  AND EV/EBITDA dumbbells vs the NAMED narrative peer set ("vs 135
  companies in the same story: …"); Narrative gap = top 2–3 narratives
  with alignment + trajectory above the exposure/priced-in bar. All data
  already crosses the API. Final pane composition = Phase 3 sign-off.

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
  dark #d95926. Not used until the Narratives phase; never for tiers or
  deltas.
- **Narrative-gap accent** — violet, light #4a3aa7 / dark #9085e9: the
  "unpriced story" highlight only.
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

## Open design decisions

- Evidence-pane final composition (direction agreed above; sign-off in
  Phase 3 when built on the company page).
- Product name / masthead identity — currently internal-flavored;
  needs deciding before anything public.
