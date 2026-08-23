"""
Qualitative Assessment Layer — runs after Phase 3 scoring.

Takes the top N stocks by gem score and applies a Claude Sonnet judgment
pass to each one. The quant score is a filter; this is the verdict.

It can upgrade or downgrade a stock's tier when the numbers miss something:
  - Earnings quality issues (declining earnings, thesis unproven)
  - Already discovered (stock has run, value score lags)
  - Imminent catalyst visible in transcripts but not yet in fundamentals
  - Sector/macro override the theme alignment can't see
  - Management credibility red flags

Adjustments are rare by design — if everything moves, the quant score
becomes meaningless. Only move when there's a specific, articulable reason.

Results stored in qual_assessments with both raw and adjusted tier.

Run:
  python -m pipeline.qual_assessor           # top 25 stocks
  python -m pipeline.qual_assessor --top 40  # wider net
  python -m pipeline.qual_assessor --symbol WDAY  # single stock
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from anthropic import Anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
from pipeline.tiers import tier_for as get_tier, WATCH

load_dotenv(override=True)

MODEL       = "claude-sonnet-4-6"
MAX_WORKERS = 4   # Sonnet is more expensive — keep parallel calls low
TOP_N       = 20   # kept for backwards compat but no longer caps assessment
MIN_SCORE   = WATCH  # assess everything at Watch tier or above (single-source: pipeline/tiers.py)


ASSESSMENT_SYSTEM = """You are a senior fundamental equity analyst performing a qualitative review of a stock flagged by a quantitative scoring system.

Your job is NOT to validate the score — it's to catch what the numbers miss. Look for:
- Earnings quality issues (declining earnings, investment phase vs structural deterioration)
- Whether the stated narrative is proven or just aspirational
- Stocks already discovered by the market (value score lags price run)
- Imminent catalysts visible in transcripts but not yet in fundamentals
- Management credibility red flags — but know the baseline: 67% of 10-Qs read
  "cautious" (mandated legal conservatism) while 88% of earnings calls read
  "confident". Cautious-filing-vs-confident-call is the NORM for the majority
  of the universe AND, per this platform's thesis, the POSITIVE configuration
  (market anchoring on dry filing language while management signals strength —
  the Corning/Dell setup). NEVER cite it as a credibility flag. Tone is only
  a signal in three cases: (a) INVERSION — management cautious/hedging ON THE
  CALL while filings read confident (rare, genuine red flag); (b) SEQUENCE —
  call tone deteriorating across consecutive quarters (confident -> cautious);
  (c) EUPHORIA — confident calls against visibly weakening margins/guidance
- Sector headwinds the theme alignment can't see

TIERS: Strong Buy (gem > {tier_sb}) | Buy ({tier_buy}–{tier_sb}) | Watch ({tier_watch}–{tier_buy}) | None (< {tier_watch})

THE EVALUATION FRAME — the Dell test. This platform hunts one specific trade:
a decent boring business, priced as a decent boring business, where genuine
narrative exposure comes FREE (Dell pre-AI-rerating: a fairly-priced PC maker
with the AI-server option at zero). Every upgrade rationale must answer:
"would the buyer be PAYING for the narrative, or getting it free on top of a
fairly-priced business?" If the narrative is in the price, it is not a hidden
gem no matter how strong the story.

COMPONENT DEFINITIONS (v2 formula: gem = sqrt(Value x Quality) x NG^0.75):
- Exposure E (0–1): SIGNED narrative exposure, cited from the company's own
  filings. Only BENEFICIARY exposure counts fully — a company defensively
  adapting to a narrative that threatens it gets a fraction; incidental
  linkage (portfolio income, cost drift) is near-zero. Interrogate the top
  exposures: is "beneficiary/direct" credible from the evidence?
- Value (0–1): STANDALONE ex-growth cheapness — percentile vs margin-peer
  group on fwd PE / EV/EBITDA / P/FCF. NO growth adjustment, by design: the
  narrative option must be free, not paid for via expected growth. PEG is
  provided as a sanity stat only.
- Quality (0–1): ROIC, margins, growth trajectory strength.
- Priced-in P (0–1): how much the market ALREADY pays for the story (price
  action, distance to 52w high, analyst crowding). HIGH P (> ~0.55) is
  near-disqualifying regardless of story strength — treat any upgrade of a
  high-P stock as extraordinary. At-the-high stocks: the repricing already
  happened; "room to run" is a momentum thesis and not ours.
- NG (0–1): E x (1 − P) — THE core signal: genuine exposure the market has
  not priced. A strong narrative fully priced scores near-zero, correctly.
  CRITICAL — unpriced exposure has two opposite causes: (a) NEGLECT — the
  story grew and price hasn't followed (the Dell setup); (b) DE-RATING —
  price falling because the market senses narrative deceleration first (a
  value trap wearing an opportunity's number). If call trajectory is
  decelerating, growth adjectives cooling, or guidance hedging while NG is
  high, treat it as a RED FLAG and say so — do not endorse it as margin of
  safety.


BAND-TRANSITION RULE: if this stock crossed a rating band within the last
~10 days (see TIER BAND HISTORY) — especially into or out of Strong Buy —
your rationale MUST place the current band against the prior one: name the
prior band, state plainly why it ended (including when the cause was OUR
measurement being corrected — e.g. "the earlier Strong Buy rested on a
quality score the old formula inflated"), and state what would move it
back ("Strong Buy is 0.6 away; the path back is X"). A band change may
never silently become the new normal after one assessment.

CONTINUITY REQUIREMENT: your analysis is a LIVING VIEW, not a fresh take.
Read your previous assessment in the provided data and frame this one explicitly as
BUILDING on it, REINFORCING it, SHIFTING it, or DIVERGING from it — and say
which, and why the new data justifies that. Never contradict your previous
view without acknowledging you held it.

WRITING RULES (the reader is an intelligent investor, NOT a platform
insider): never use internal shorthand like P=, E=, NG, V_s, gem. Say it
straight — "the market has already priced about half this story", "narrative
exposure is strong", "standalone value is high". Quote scores on a 10-POINT
scale (a 0.55 input is "5.5 out of 10").

METRIC DISCIPLINE (three views, always reconciled): the data gives you a
10-year annual road, the last fiscal year, and trailing-twelve-month
figures. Never quote a single flattering number as if it were the company —
locate the TTM against the road. Say plainly whether a metric's history is
STEADY, GENUINELY IMPROVING (multi-year path, like a compounder), or
CYCLICAL (oscillating with booms and busts — check whether today's level
is merely recovering toward a prior peak). For cyclical businesses the
platform's doctrine applies: they are interesting when punished and
written off, not when things are going well — a strong year near a cycle
high is a WARNING for the thesis, not support. One weak year in an
otherwise steady decade is a blip, not a trend; say so rather than
overreacting.

Respond in valid JSON only:
{{
  "direction": "upgrade" | "downgrade" | "hold",
  "adjusted_tier": "Strong Buy" | "Buy" | "Watch" | "None",
  "continuity": "building" | "reinforcing" | "shifting" | "diverging" | "first",
  "rationale": "Two to four sentences — plain language, opens with the continuity framing (and the trigger verdict if one was given)",
  "key_bull": "Single most compelling reason to own it",
  "key_bear": "Single most important risk to the thesis"
}}

Rules:
- Only upgrade/downgrade when there is a SPECIFIC, ARTICULABLE reason
- Most stocks should be "hold" — do not adjust just to seem thorough
- Multi-tier jumps are PERMITTED when the evidence genuinely merits it, but
  they are exceptional: a leap of more than one tier requires the rationale to
  explicitly state why one step is insufficient
- Never upgrade to Strong Buy unless narrative is genuinely differentiated AND cheap AND quality
- Return ONLY valid JSON, no markdown"""

ASSESSMENT_USER = """QUANTITATIVE SCORES:
  Symbol: {symbol}
  Gem score: {gem_score} → Raw tier: {raw_tier}
  Exposure E: {narrative_score} | Value: {value_score} | Quality: {quality_score} | Priced-in P: {priced_in} | NG: {ng_score}
  PEG (sanity stat): {peg} | Fwd PE: {fwd_pe} | Revenue growth: {rev_growth} | Earnings growth: {earn_growth} | ROIC (TTM): {roic}
  PEG reading rule: a HIGH PEG means the price is HIGH relative to expected growth (or consensus growth is near zero) — it NEVER means growth is unpriced. A LOW PEG is the cheap-for-growth signal. If the PEG line above is tagged CONFLICT, the figure is unreliable: do not build any argument on it in either direction.

TOP THEMES (from filings + earnings calls):
{themes}

MOST RECENT EARNINGS CALL ({last_call_date}):
  Narrative strength: {call_narrative_strength} | Trajectory: {call_trajectory} | Tone: {call_tone}
  Key themes: {call_themes}
  Catalysts: {call_catalysts}
  Risks: {call_risks}

MOST RECENT 10-K/10-Q:
  Narrative strength: {filing_narrative_strength} | Trajectory: {filing_trajectory} | Tone: {filing_tone}

10-YEAR ROAD (annual, oldest → newest — canonical figures; reconcile TTM stats above against this history):
{fundamental_trend}
{trigger_context}

YOUR PREVIOUS ASSESSMENT ({prev_date}): {prev_verdict}
TIER BAND HISTORY (recent rating-band changes with their causes — continuity
is chain-deep, not just vs the last assessment):
{band_history}
{prev_rationale}"""


_NOTES_CACHE: dict = {}


def _platform_notes(engine) -> str:
    """Active platform-event notes injected into EVERY assessment while
    live (user 2026-08-09: methodology/data changes must never be narrated
    as company news). Cached per process."""
    if "v" in _NOTES_CACHE:
        return _NOTES_CACHE["v"]
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS platform_notes (
                    id SERIAL PRIMARY KEY, note TEXT NOT NULL,
                    active_from DATE NOT NULL, active_to DATE NOT NULL)"""))
            rows = conn.execute(text("""
                SELECT note FROM platform_notes
                WHERE CURRENT_DATE BETWEEN active_from AND active_to""")).fetchall()
        _NOTES_CACHE["v"] = ("".join(
            f"\nPLATFORM NOTE (this is about OUR measurement, NOT the company): {r[0]}\n"
            for r in rows)) if rows else ""
    except Exception:
        _NOTES_CACHE["v"] = ""
    return _NOTES_CACHE["v"]


def _peg_context_line(fund) -> str:
    """PEG with provenance, implied-vs-delivered growth, and a CONFLICT
    tag (2026-08-23, the CRUS lesson: vendor 9.35 was narrated as
    'market not crediting growth' — an inversion built on a junk value).
    fund = (peg, pe_forward, rev_growth, earn_growth, roic, sector,
    peg_analysts)."""
    if not fund or fund[0] is None:
        return "n/a"
    peg = float(fund[0])
    out = f"{peg:.2f}"
    n = fund[6]
    if n:
        n = int(n)
        out += (f" (consensus of {n} analyst{'s' if n != 1 else ''}"
                + (" — THIN coverage, treat with caution" if n <= 4 else "")
                + ")")
    else:
        out += " (vendor)"
    fwd = float(fund[1]) if fund[1] else None
    earn = float(fund[3]) if fund[3] is not None else None
    if fwd and fwd > 0 and peg > 0:
        implied = fwd / peg   # PEG = PE/(g*100) -> g% = PE/PEG
        out += f" — implies consensus growth ≈{implied:.1f}%/yr"
        if earn is not None:
            out += f" vs delivered {earn * 100:+.1f}%"
            if implied < 3 and earn > 0.15:
                out += (" — CONFLICT: the implied growth contradicts the"
                        " delivered numbers; this PEG is unreliable, do"
                        " NOT lean on it in either direction")
    return out


def get_stock_context(engine, symbol: str) -> dict:
    """Pull all context needed for qual assessment from DB."""
    with engine.connect() as conn:
        # Previous assessment — the continuity anchor (user 2026-08-01)
        prev = conn.execute(text("""
            SELECT adjusted_tier, direction, rationale, assessed_at::date
            FROM qual_assessments WHERE symbol = :sym
        """), {"sym": symbol}).fetchone()
        # Most recent earnings call
        call = conn.execute(text("""
            SELECT ft.narrative_strength, ft.trajectory, ft.management_tone,
                   ft.raw_themes, ft.catalysts, ft.risks, f.filing_date
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :sym AND f.filing_type = 'EARN_CALL'
            ORDER BY f.filing_date DESC
            LIMIT 1
        """), {"sym": symbol}).fetchone()

        # Most recent 10-K or 10-Q
        filing = conn.execute(text("""
            SELECT ft.narrative_strength, ft.trajectory, ft.management_tone, f.filing_date
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :sym AND f.filing_type IN ('10-K','10-Q')
            ORDER BY f.filing_date DESC
            LIMIT 1
        """), {"sym": symbol}).fetchone()

        # Fundamentals
        fund = conn.execute(text("""
            SELECT peg_ratio, pe_forward, revenue_growth_yoy,
                   earnings_growth_yoy, roic, sector, peg_analysts
            FROM fundamentals WHERE symbol = :sym
        """), {"sym": symbol}).fetchone()

        # 10-year annual road from the CANONICAL tables (P2 2026-08-09) —
        # long enough to see a full cycle, single FMP definitions
        trend_rows = conn.execute(text("""
            SELECT fiscal_year, revenue, gross_margin, op_margin, net_margin,
                   fcf, roic
            FROM fundamentals_annual
            WHERE symbol = :sym
            ORDER BY fiscal_year DESC
            LIMIT 10
        """), {"sym": symbol}).fetchall()[::-1]

        # Recent material events WITH their content (the AECOM lesson,
        # user 2026-08-11): the assessor was told an 8-K existed but never
        # shown its summary — it adjudicated a $337M charge as noise
        # blind. A judgment surface must receive the evidence it judges.
        event_rows = conn.execute(text("""
            SELECT filing_type, filing_date::date, llm_analysis
            FROM filings
            WHERE symbol = :sym AND filing_type IN ('8-K', '8-K/A')
              AND llm_analysis IS NOT NULL
              AND filing_date > NOW() - INTERVAL '14 days'
            ORDER BY filing_date DESC LIMIT 3
        """), {"sym": symbol}).fetchall()
    events = []
    for ftype, fdate, analysis in event_rows:
        try:
            a = json.loads(analysis)
            events.append(
                f"- {ftype} filed {fdate} [{a.get('event_type', '?')}, "
                f"impact {a.get('impact', '?')} {a.get('score', '')}]: "
                f"{a.get('summary', a.get('headline', ''))}")
        except Exception:
            events.append(f"- {ftype} filed {fdate}: {str(analysis)[:300]}")
    recent_events = "\n".join(events)

    with engine.connect() as conn:
        hist_rows = conn.execute(text("""
            SELECT assessed_at::date, adjusted_tier, LEFT(rationale, 140)
            FROM qual_history WHERE symbol = :sym
            ORDER BY assessed_at DESC LIMIT 8"""), {"sym": symbol}).fetchall()
    band_changes = []
    prev_tier = None
    for d, tier, why in reversed(hist_rows):   # chronological
        if tier != prev_tier and prev_tier is not None:
            band_changes.append(f"- {d}: {prev_tier} -> {tier}: {why}")
        prev_tier = tier
    band_history = "\n".join(band_changes[-3:]) if band_changes \
        else "(no band changes on record)"

    return {
        "call":       call,
        "filing":     filing,
        "fund":       fund,
        "trend_rows": trend_rows,
        "prev":       prev,
        "band_history": band_history,
        "recent_events": recent_events,
        "platform_notes": _platform_notes(engine),
    }


def build_prompt(gem: dict, ctx: dict) -> str:
    """Assemble the assessment prompt for one stock."""
    call       = ctx["call"]
    filing     = ctx["filing"]
    fund       = ctx["fund"]
    trend_rows = ctx.get("trend_rows", [])

    def fmt(v, pct=False, dp=2):
        if v is None: return "n/a"
        v = float(v)
        if pct: return f"{v*100:.1f}%"
        return f"{v:.{dp}f}"

    def fmt_m(v):
        """Format revenue/FCF in $M."""
        if v is None: return "n/a"
        return f"${float(v)/1e6:,.0f}M"

    themes_str = "\n".join(
        f"  - {t['theme']} (score: {t['score']:.3f})"
        for t in gem.get("top_themes", [])
    ) or "  (none)"

    call_themes    = "n/a"
    call_catalysts = "n/a"
    call_risks     = "n/a"
    call_date      = "n/a"
    call_ns        = "n/a"
    call_traj      = "n/a"
    call_tone      = "n/a"

    if call:
        call_date = str(call[6])[:10]
        call_ns   = fmt(call[0])
        call_traj = call[1] or "n/a"
        call_tone = call[2] or "n/a"
        try:
            themes_list = json.loads(call[3]) if call[3] else []
            call_themes = "; ".join(themes_list[:4]) if themes_list else "n/a"
        except Exception:
            call_themes = str(call[3])[:300]
        try:
            cats = json.loads(call[4]) if call[4] else []
            call_catalysts = "; ".join(cats[:3]) if cats else "n/a"
        except Exception:
            call_catalysts = str(call[4])[:200]
        try:
            risks = json.loads(call[5]) if call[5] else []
            call_risks = "; ".join(risks[:3]) if risks else "n/a"
        except Exception:
            call_risks = str(call[5])[:200]

    filing_ns   = fmt(filing[0]) if filing else "n/a"
    filing_traj = filing[1] if filing else "n/a"
    filing_tone = filing[2] if filing else "n/a"

    # Format 10-year road table
    if trend_rows:
        trend_lines = ["  Year       Revenue     Gross%   OpMgn%   NetMgn%   FCF        ROIC%"]
        for r in trend_rows:
            period_end, revenue, gm, om, nm, fcf, roic = r
            year = str(period_end)[:4]
            trend_lines.append(
                f"  {year}    {fmt_m(revenue):>10}  "
                f"{fmt(gm, pct=True):>7}  {fmt(om, pct=True):>7}  "
                f"{fmt(nm, pct=True):>7}  {fmt_m(fcf):>10}  {fmt(roic, pct=True):>6}"
            )
        fundamental_trend = "\n".join(trend_lines)
    else:
        fundamental_trend = "  (no multi-year history available)"

    from pipeline.tiers import STRONG_BUY, BUY, WATCH
    # Static system block (identical every call -> prompt-cached);
    # dynamic per-stock data rides in the user message.
    system_text = ASSESSMENT_SYSTEM.format(
        tier_sb=f"{STRONG_BUY:.2f}", tier_buy=f"{BUY:.2f}", tier_watch=f"{WATCH:.2f}")
    return system_text, ASSESSMENT_USER.format(
        symbol               = gem["symbol"],
        gem_score            = fmt(gem["hidden_gem_score"]),
        raw_tier             = gem.get("_raw_tier", "—"),
        narrative_score      = fmt(gem["narrative_score"]),
        value_score          = fmt(gem["value_score"]),
        quality_score        = fmt(gem["quality_score"]),
        priced_in            = fmt(gem.get("priced_in", 0.5)),
        ng_score             = fmt(gem.get("ng_score", 0)),
        # PEG carries its evidence weight (user 2026-08-12): a 3-analyst
        # consensus PEG deserves less trust than a 25-analyst one.
        peg                  = _peg_context_line(fund),
        fwd_pe               = fmt(fund[1] if fund else None),
        rev_growth           = fmt(fund[2] if fund else None, pct=True),
        earn_growth          = fmt(fund[3] if fund else None, pct=True),
        roic                 = fmt(fund[4] if fund else None, pct=True),
        themes               = themes_str,
        last_call_date       = call_date,
        call_narrative_strength = call_ns,
        call_trajectory      = call_traj,
        call_tone            = call_tone,
        call_themes          = call_themes,
        call_catalysts       = call_catalysts,
        call_risks           = call_risks,
        filing_narrative_strength = filing_ns,
        filing_trajectory    = filing_traj,
        filing_tone          = filing_tone,
        fundamental_trend    = fundamental_trend,
        prev_date            = str(ctx["prev"][3]) if ctx.get("prev") else "none",
        prev_verdict         = (f"{ctx['prev'][0]} ({ctx['prev'][1]})"
                                if ctx.get("prev") else "FIRST ASSESSMENT — no prior view"),
        prev_rationale       = (ctx["prev"][2] or "")[:600] if ctx.get("prev") else "",
        band_history         = ctx.get("band_history", "(no band changes on record)"),
        trigger_context      = (
            (f"\nRECENT MATERIAL EVENTS (what was actually filed — weigh the "
             f"CONTENT, not just the fact of the filing):\n{ctx['recent_events']}\n"
             if ctx.get("recent_events") else "")
            + (f"{ctx.get('platform_notes', '')}"
               f"\nWHY YOU ARE BEING ASKED NOW: {gem['_trigger']}\n"
               "Your rationale MUST open by stating whether this event/move changes "
               "the thesis or is noise — that opinion is the point of this assessment."
               if gem.get("_trigger") else ctx.get("platform_notes", ""))),
    )


def assess_stock(client, engine, gem: dict) -> dict:
    """Run qual assessment for one stock. Returns result dict."""
    ctx    = get_stock_context(engine, gem["symbol"])
    system_text, user_text = build_prompt(gem, ctx)

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model     = MODEL,
                max_tokens= 1200,   # 600 truncated mid-JSON once continuity framing lengthened rationales (GDDY 2026-08-01)
                system    = [{"type": "text", "text": system_text,
                              "cache_control": {"type": "ephemeral"}}],
                messages  = [{"role": "user", "content": user_text}],
                timeout   = 45,
            )
            from pipeline.llm_usage import record_usage
            record_usage(engine, "qual_assessor", MODEL, resp.usage)
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]
            result = json.loads(raw)
            result["symbol"] = gem["symbol"]
            return result
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    # Total failure: return None — store_assessment is SKIPPED so a real
    # prior assessment is never overwritten by a placeholder (learned
    # 2026-08-01 when a truncation failure stomped GDDY's live verdict).
    return None


def store_assessment(engine, gem: dict, result: dict):
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE qual_assessments ADD COLUMN IF NOT EXISTS narrative_score NUMERIC(10,4)"))
        conn.execute(text(
            "ALTER TABLE qual_assessments ADD COLUMN IF NOT EXISTS continuity VARCHAR(12)"))
        # Preserve the chain (user 2026-08-01): the upsert overwrites, so the
        # outgoing assessment is archived first — the full sequence of views
        # per stock lives in qual_history.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS qual_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                gem_score NUMERIC(10,4), raw_tier VARCHAR(20),
                adjusted_tier VARCHAR(20), direction VARCHAR(12),
                continuity VARCHAR(12), rationale TEXT,
                assessed_at TIMESTAMP
            )"""))
        conn.execute(text("""
            INSERT INTO qual_history (symbol, gem_score, raw_tier, adjusted_tier,
                                      direction, continuity, rationale, assessed_at)
            SELECT symbol, gem_score, raw_tier, adjusted_tier, direction,
                   continuity, rationale, assessed_at
            FROM qual_assessments WHERE symbol = :s
        """), {"s": gem["symbol"]})
        conn.execute(text("""
            INSERT INTO qual_assessments
                (symbol, gem_score, narrative_score, raw_tier, adjusted_tier, direction,
                 continuity, rationale, key_bull, key_bear, assessed_at)
            VALUES
                (:symbol, :gem_score, :narrative_score, :raw_tier, :adjusted_tier, :direction,
                 :continuity, :rationale, :key_bull, :key_bear, NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                continuity    = EXCLUDED.continuity,
                gem_score     = EXCLUDED.gem_score,
                narrative_score = EXCLUDED.narrative_score,
                raw_tier      = EXCLUDED.raw_tier,
                adjusted_tier = EXCLUDED.adjusted_tier,
                direction     = EXCLUDED.direction,
                rationale     = EXCLUDED.rationale,
                key_bull      = EXCLUDED.key_bull,
                key_bear      = EXCLUDED.key_bear,
                assessed_at   = NOW()
        """), {
            "symbol":        gem["symbol"],
            "gem_score":     gem["hidden_gem_score"],
            "narrative_score": gem.get("narrative_score"),
            "continuity":    result.get("continuity", "first"),
            "raw_tier":      gem.get("_raw_tier"),
            "adjusted_tier": result.get("adjusted_tier"),
            "direction":     result.get("direction", "hold"),
            "rationale":     result.get("rationale", ""),
            "key_bull":      result.get("key_bull", ""),
            "key_bear":      result.get("key_bear", ""),
        })
        conn.commit()


def run_qual_assessment(top_n: int = TOP_N, symbol: str = None,
                        symbols: list = None, gems: list = None,
                        triggers: dict = None):
    """
    Run qual assessment.
    - symbol:  assess a single named stock (CLI use)
    - symbols: assess a specific list of stocks (daily targeted use)
    - gems:    pre-computed score_all_stocks() result — avoids redundant re-score
    - top_n:   kept for backwards compat; no longer caps assessment count
    When neither symbol nor symbols is given, assesses all Watch+ stocks.
    """
    engine = get_engine()
    client = Anthropic()

    print("=" * 70)
    print("QUALITATIVE ASSESSMENT LAYER")
    print("=" * 70)

    if gems is None:
        gems = score_all_stocks(engine)

    if symbol:
        # Single-symbol mode (CLI / manual)
        gems = [g for g in gems if g["symbol"] == symbol.upper()]
        if not gems:
            print(f"  {symbol} not found in scored universe")
            return
    elif symbols:
        # Targeted list mode (daily tier-mover assessment)
        target = {s.upper() for s in symbols}
        gems = [g for g in gems if g["symbol"] in target]
        if not gems:
            print(f"  None of {symbols} found in scored universe")
            return
    else:
        # Full pass — all Watch+ stocks
        gems = [g for g in gems if g["hidden_gem_score"] >= MIN_SCORE]

    # Tag each gem with its raw tier + trigger reason before assessment
    for g in gems:
        g["_raw_tier"] = get_tier(g["hidden_gem_score"]) or "None"
        if triggers and g["symbol"] in triggers:
            g["_trigger"] = triggers[g["symbol"]]

    print(f"  Assessing {len(gems)} stocks with {MODEL}\n")

    lock      = Lock()
    completed = 0
    changes   = []

    def process(gem):
        result = assess_stock(client, engine, gem)
        if result is None:
            return gem, {"direction": "failed", "adjusted_tier": gem.get("_raw_tier"),
                         "rationale": "(assessment errored — previous verdict retained)"}
        store_assessment(engine, gem, result)
        return gem, result

    # Cache warm-up (2026-08-09): with a cold cache, the first MAX_WORKERS
    # parallel calls all race and all MISS before any writes the shared
    # system block (measured 55% hit rate vs ~85% achievable). Run ONE
    # assessment synchronously to write the cache, then fan out.
    def _tally(gem, result):
        nonlocal completed
        with lock:
            completed += 1
            direction = result.get("direction", "hold")
            adj_tier = result.get("adjusted_tier", gem["_raw_tier"])
            arrow = "⬆" if direction == "upgrade" else "⬇" if direction == "downgrade" else "–"
            if direction != "hold":
                changes.append((gem["symbol"], gem["_raw_tier"], adj_tier,
                                direction, result.get("rationale", "")))
            print(f"  [{completed:2d}/{len(gems)}] {gem['symbol']:<6} {arrow} "
                  f"{gem['_raw_tier']} → {adj_tier}  "
                  f"{result.get('rationale','')[:70]}")

    if len(gems) > 1:
        first, *rest = gems
        _tally(*process(first))
    else:
        rest = gems
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process, g): g for g in rest}
        for future in as_completed(futures):
            gem, result = future.result()
            _tally(gem, result)

    print(f"\n{'='*70}")
    print(f"SUMMARY — {len(changes)} adjustment(s) from {len(gems)} assessed\n")

    if changes:
        for sym, raw, adj, d, rationale in sorted(changes, key=lambda x: x[3]):
            arrow = "⬆ UPGRADE" if d == "upgrade" else "⬇ DOWNGRADE"
            print(f"  {sym:<6} {arrow:<12} {raw} → {adj}")
            print(f"         {rationale}")
            print()
    else:
        print("  No adjustments — quant scores held")

    # Print final adjusted top 10
    print(f"\n{'='*70}")
    print("FINAL ADJUSTED TOP 10\n")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT qa.symbol, qa.gem_score, qa.adjusted_tier, qa.direction,
                   qa.key_bull, qa.key_bear, qa.rationale
            FROM qual_assessments qa
            ORDER BY
                CASE qa.adjusted_tier
                    WHEN 'Strong Buy' THEN 1
                    WHEN 'Buy'        THEN 2
                    WHEN 'Watch'      THEN 3
                    ELSE 4 END,
                qa.gem_score DESC
            LIMIT 10
        """)).fetchall()

    for i, r in enumerate(rows, 1):
        tier_icon = {"Strong Buy": "🔥", "Buy": "✅", "Watch": "👀"}.get(r[2], "–")
        adj_note  = f" [{r[3].upper()}]" if r[3] != "hold" else ""
        print(f"  #{i:<2} {r[0]:<6} {r[1]:.3f}  {tier_icon} {r[2]}{adj_note}")
        print(f"       Bull: {r[4]}")
        print(f"       Bear: {r[5]}")
        if r[3] != "hold":
            print(f"       Note: {r[6]}")
        print()

    # Stamp qual-adjusted tiers back into leaderboard_history so tomorrow's
    # move-detection compares against final assessed tiers, not raw gem tiers.
    from pipeline.leaderboard_archiver import apply_qual_tiers, create_table
    create_table(engine)
    updated = apply_qual_tiers(engine)
    print(f"  Leaderboard history updated with qual tiers: {updated} rows")


if __name__ == "__main__":
    top_n  = TOP_N
    sym    = None
    for arg in sys.argv[1:]:
        if arg.startswith("--top="):
            top_n = int(arg.split("=")[1])
        elif arg.startswith("--symbol="):
            sym = arg.split("=")[1]
        elif arg.startswith("--top"):
            try: top_n = int(sys.argv[sys.argv.index(arg)+1])
            except Exception: pass
    run_qual_assessment(top_n=top_n, symbol=sym)
