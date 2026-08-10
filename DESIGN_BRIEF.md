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

1. **The Board** — front door. The current opportunity set: ranked,
   tiered, countdowns visible. Opening the site = reading the instrument.
2. **Companies** — the workbench. Point the instrument at any covered
   name; get the same signature view every time. Events, insider
   activity, and filings appear HERE, inside the dossier, where they
   have context.
3. **Narratives** — the differentiator: why the instrument sees what
   others don't. Three-layer map (forces / what moved / library).
4. **What Changed** — the daily edition, demoted from front page to
   instrument log: readings that moved, entries, exits, why.
5. **Portfolio** — capital against the instrument's output. (Owner-only
   feature initially; a per-user feature if the product gets users.)

Events / Insiders / News Wire are NOT top-level destinations — they
dissolve into Companies and What Changed.

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

## Open design decisions

- Signature view form (Phase 2 presents live variants; user picks).
- Design tokens (locked after that pick).
- Product name / masthead identity — currently internal-flavored;
  needs deciding before anything public.
