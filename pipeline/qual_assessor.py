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
from ui.app import get_tier

load_dotenv(override=True)

MODEL       = "claude-sonnet-4-6"
MAX_WORKERS = 4   # Sonnet is more expensive — keep parallel calls low
TOP_N       = 20   # kept for backwards compat but no longer caps assessment
MIN_SCORE   = 0.34 # assess everything at Watch tier or above (matches Home page threshold)


ASSESSMENT_PROMPT = """You are a senior fundamental equity analyst performing a qualitative review of a stock flagged by a quantitative scoring system.

Your job is NOT to validate the score — it's to catch what the numbers miss. Look for:
- Earnings quality issues (declining earnings, investment phase vs structural deterioration)
- Whether the stated narrative is proven or just aspirational
- Stocks already discovered by the market (value score lags price run)
- Imminent catalysts visible in transcripts but not yet in fundamentals
- Management credibility red flags (cautious tone vs confident filing language)
- Sector headwinds the theme alignment can't see

TIERS: Strong Buy (gem > 0.60) | Buy (0.52–0.60) | Watch (0.47–0.52) | None (< 0.47)

COMPONENT DEFINITIONS — read carefully; do not guess semantics:
- Narrative (0–1): LLM-judged exposure to accelerating structural narratives,
  cited from the company's own filings. High = genuine, material exposure.
- Value (0–1): PERCENTILE RANK vs margin-peer group (PEG-weighted). 1.00 means
  "cheapest in its peer group on the blend", NOT infinitely cheap — and it can
  be inflated by distorted growth inputs (spin-offs, one-off comps).
- Quality (0–1): ROIC, margins, growth trajectory strength.
- Gap (0–1): degree to which the market has NOT yet priced the narrative.
  HIGH gap = story present, price lagging = THE OPPORTUNITY this platform
  hunts. LOW gap = market has already repriced it. Never read a high gap as
  "the market has discovered this" — it means the opposite.

QUANTITATIVE SCORES:
  Symbol: {symbol}
  Gem score: {gem_score} → Raw tier: {raw_tier}
  Narrative: {narrative_score} | Value: {value_score} | Quality: {quality_score} | Gap: {gap_score}
  PEG: {peg} | Fwd PE: {fwd_pe} | Revenue growth: {rev_growth} | Earnings growth: {earn_growth} | ROIC: {roic}

TOP THEMES (from filings + earnings calls):
{themes}

MOST RECENT EARNINGS CALL ({last_call_date}):
  Narrative strength: {call_narrative_strength} | Trajectory: {call_trajectory} | Tone: {call_tone}
  Key themes: {call_themes}
  Catalysts: {call_catalysts}
  Risks: {call_risks}

MOST RECENT 10-K/10-Q:
  Narrative strength: {filing_narrative_strength} | Trajectory: {filing_trajectory} | Tone: {filing_tone}

5-YEAR FUNDAMENTAL TREND (annual, oldest → newest):
{fundamental_trend}

Respond in valid JSON only:
{{
  "direction": "upgrade" | "downgrade" | "hold",
  "adjusted_tier": "Strong Buy" | "Buy" | "Watch" | "None",
  "rationale": "One or two sentences — specific reason for any change, or why it holds",
  "key_bull": "Single most compelling reason to own it",
  "key_bear": "Single most important risk to the thesis"
}}

Rules:
- Only upgrade/downgrade when there is a SPECIFIC, ARTICULABLE reason
- Most stocks should be "hold" — do not adjust just to seem thorough
- Adjusted tier must be adjacent (one step up or down), never leap two tiers
- Never upgrade to Strong Buy unless narrative is genuinely differentiated AND cheap AND quality
- Return ONLY valid JSON, no markdown"""


def get_stock_context(engine, symbol: str) -> dict:
    """Pull all context needed for qual assessment from DB."""
    with engine.connect() as conn:
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
                   earnings_growth_yoy, roic, sector
            FROM fundamentals WHERE symbol = :sym
        """), {"sym": symbol}).fetchone()

        # 5-year annual trend from fundamentals_history
        trend_rows = conn.execute(text("""
            SELECT period_end, revenue, gross_margin, op_margin, net_margin, fcf, roic
            FROM fundamentals_history
            WHERE symbol = :sym AND period_type = 'A'
            ORDER BY period_end ASC
            LIMIT 6
        """), {"sym": symbol}).fetchall()

    return {
        "call":       call,
        "filing":     filing,
        "fund":       fund,
        "trend_rows": trend_rows,
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

    # Format 5-year trend table
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

    return ASSESSMENT_PROMPT.format(
        symbol               = gem["symbol"],
        gem_score            = fmt(gem["hidden_gem_score"]),
        raw_tier             = gem.get("_raw_tier", "—"),
        narrative_score      = fmt(gem["narrative_score"]),
        value_score          = fmt(gem["value_score"]),
        quality_score        = fmt(gem["quality_score"]),
        gap_score            = fmt(gem.get("gap_score", 0)),
        peg                  = fmt(fund[0] if fund else None),
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
    )


def assess_stock(client, engine, gem: dict) -> dict:
    """Run qual assessment for one stock. Returns result dict."""
    ctx    = get_stock_context(engine, gem["symbol"])
    prompt = build_prompt(gem, ctx)

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model     = MODEL,
                max_tokens= 600,
                messages  = [{"role": "user", "content": prompt}],
                timeout   = 45,
            )
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
    return {
        "symbol":        gem["symbol"],
        "direction":     "hold",
        "adjusted_tier": gem.get("_raw_tier", "—"),
        "rationale":     "Assessment failed — holding quant tier",
        "key_bull":      "",
        "key_bear":      "",
    }


def store_assessment(engine, gem: dict, result: dict):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO qual_assessments
                (symbol, gem_score, raw_tier, adjusted_tier, direction,
                 rationale, key_bull, key_bear, assessed_at)
            VALUES
                (:symbol, :gem_score, :raw_tier, :adjusted_tier, :direction,
                 :rationale, :key_bull, :key_bear, NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                gem_score     = EXCLUDED.gem_score,
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
            "raw_tier":      gem.get("_raw_tier"),
            "adjusted_tier": result.get("adjusted_tier"),
            "direction":     result.get("direction", "hold"),
            "rationale":     result.get("rationale", ""),
            "key_bull":      result.get("key_bull", ""),
            "key_bear":      result.get("key_bear", ""),
        })
        conn.commit()


def run_qual_assessment(top_n: int = TOP_N, symbol: str = None,
                        symbols: list = None, gems: list = None):
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

    # Tag each gem with its raw tier before assessment
    for g in gems:
        g["_raw_tier"] = get_tier(g["hidden_gem_score"]) or "None"

    print(f"  Assessing {len(gems)} stocks with {MODEL}\n")

    lock      = Lock()
    completed = 0
    changes   = []

    def process(gem):
        result = assess_stock(client, engine, gem)
        store_assessment(engine, gem, result)
        return gem, result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process, g): g for g in gems}
        for future in as_completed(futures):
            gem, result = future.result()
            with lock:
                completed += 1
                direction  = result.get("direction", "hold")
                adj_tier   = result.get("adjusted_tier", gem["_raw_tier"])
                arrow      = "⬆" if direction == "upgrade" else "⬇" if direction == "downgrade" else "–"
                if direction != "hold":
                    changes.append((gem["symbol"], gem["_raw_tier"], adj_tier,
                                    direction, result.get("rationale", "")))
                print(f"  [{completed:2d}/{len(gems)}] {gem['symbol']:<6} {arrow} "
                      f"{gem['_raw_tier']} → {adj_tier}  "
                      f"{result.get('rationale','')[:70]}")

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
