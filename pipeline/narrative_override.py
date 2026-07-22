"""
Narrative-blind screen + qual override (user-approved 2026-07-21).

The 19-narrative brain can't see company-specific narratives (canonical case:
Broadridge — SEC digital-default catalyst, tokenization/DLR infrastructure —
quality 1.00, gap 0.77, value 0.41, yet gem 0.16 because narrative 0.38 maps
only partial AI exposure). Until the v2 company-narrative layer exists, the
qual assessor gets a bounded override right:

  SCREEN (weekly LLM, daily re-stamp): quality >= 0.75, gap >= 0.60,
    value >= 0.40, narrative < 0.50, raw gem <= 0.47 (off board) —
    "quant-qualified but narrative-blind".
  OVERRIDE: assessor may RAISE narrative by at most +0.40, only with cited
    filing/call evidence of a real, financially-proven, unmapped company
    narrative. Never lowers, never touches other components.
  AUDIT: raw score untouched everywhere; adjusted values stored alongside;
    every decision (including declines) kept as the labeled dataset for v2.
  TRACK RECORD: promoted Strong Buys get $1,000 lots flagged qual_promoted
    (user decision 2026-07-21) so override alpha is measurable separately.

Promotions are stamped into leaderboard_history (assessed_tier +
qual_promoted + gem_adjusted); the board UI and track record read from there.
"""
import json
import time

from sqlalchemy import text

# v2 screen (2026-07-22): quant-qualified but exposure-blind — standalone
# cheap, quality, NOT crowded (priced_in low), yet low signed E keeps it off
# the board. The floor gates who gets JUDGED; promotion still requires the
# adjusted gem to clear the Watch line (single-source: pipeline/tiers.py).
SCREEN = {"quality": 0.75, "priced_in_max": 0.50, "value": 0.35,
          "narrative_below": 0.50}
MAX_BOOST = 0.40
REUSE_DAYS = 7   # LLM re-judges weekly; daily runs re-stamp from stored boost

OVERRIDE_PROMPT = """You are a senior fundamental equity analyst. A quantitative system scores stocks as gem = sqrt(value*quality) * narrative^1.5 * gap_multiplier. Its narrative score comes from mapping each stock against a library of ~19 MACRO and SECTOR narratives — it is structurally blind to COMPANY-SPECIFIC narratives (a proven, differentiated story belonging to this company alone).

This stock passed a screen: high quality ({quality_score}), wide gap ({gap_score} — the market has NOT priced its story), reasonable value ({value_score}), yet a LOW mapped narrative score ({narrative_score}) keeps it off the board (gem {gem_score}).

Your ONE decision: does this company have a genuine company-level narrative that the macro/sector library cannot see — proven in its financials and filings, not merely aspirational — that justifies raising the narrative input?

Rules:
- You may RAISE narrative by at most +{max_boost} (to a maximum of {max_narrative}). You may NOT lower it or touch any other component.
- The bar is HIGH: the narrative must be (a) specific to this company or its niche, (b) already showing up in delivered financials (margins, ROIC, growth mix), and (c) supported by concrete catalysts or structural positioning cited in ITS OWN filings/calls below. "Good company, cheap stock" is NOT a narrative — decline those.
- Most candidates should be DECLINED. An override without hard cited evidence is worse than no override.
- Cite the specific evidence (filing/call content below) in "evidence". Generic sector tailwinds do not count — those are what the library already maps.

QUANT COMPONENTS:
  Symbol: {symbol}
  Raw gem: {gem_score} | Narrative: {narrative_score} | Value: {value_score} | Quality: {quality_score} | Gap: {gap_score}
  PEG: {peg} | Fwd PE: {fwd_pe} | Revenue growth: {rev_growth} | Earnings growth: {earn_growth} | ROIC: {roic}

TOP MAPPED THEMES (what the library CAN see):
{themes}

MOST RECENT EARNINGS CALL ({last_call_date}):
  Narrative strength: {call_narrative_strength} | Trajectory: {call_trajectory} | Tone: {call_tone}
  Key themes: {call_themes}
  Catalysts: {call_catalysts}
  Risks: {call_risks}

MOST RECENT 10-K/10-Q:
  Narrative strength: {filing_narrative_strength} | Trajectory: {filing_trajectory} | Tone: {filing_tone}

5-YEAR FUNDAMENTAL TREND (annual, oldest -> newest):
{fundamental_trend}

Respond in valid JSON only:
{{
  "override": true | false,
  "narrative_adjusted": <float, only if override; between {narrative_score} and {max_narrative}>,
  "evidence": "The specific filing/call evidence for the company-level narrative (or why declined)",
  "rationale": "One or two sentences: the narrative in plain terms and why the library misses it",
  "key_bull": "Single most compelling reason to own it",
  "key_bear": "Single most important risk to the thesis"
}}
Return ONLY valid JSON, no markdown."""


def create_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS narrative_overrides (
                id                 SERIAL PRIMARY KEY,
                symbol             VARCHAR(10) UNIQUE NOT NULL,
                narrative_raw      NUMERIC(10,4),
                narrative_adjusted NUMERIC(10,4),
                gem_raw            NUMERIC(10,4),
                gem_adjusted       NUMERIC(10,4),
                adjusted_tier      VARCHAR(20),
                promoted           BOOLEAN DEFAULT FALSE,
                evidence           TEXT,
                rationale          TEXT,
                key_bull           TEXT,
                key_bear           TEXT,
                assessed_at        TIMESTAMP
            )
        """))
        conn.execute(text(
            "ALTER TABLE leaderboard_history ADD COLUMN IF NOT EXISTS qual_promoted BOOLEAN DEFAULT FALSE"))
        conn.execute(text(
            "ALTER TABLE leaderboard_history ADD COLUMN IF NOT EXISTS gem_adjusted NUMERIC(10,4)"))
        conn.execute(text(
            "ALTER TABLE track_lots ADD COLUMN IF NOT EXISTS qual_promoted BOOLEAN DEFAULT FALSE"))


def recompute_gem(g: dict, n_adj: float) -> float:
    """v2 composition (V2_SPEC) with the adjusted E input.
    Mirrors hidden_gem_scorer.score_all_stocks."""
    v, q = g["value_score"], g["quality_score"]
    unpriced = 1 - g.get("priced_in", 0.5)
    if g.get("neg_velocity"):
        unpriced = min(unpriced, 0.5)
    ng = n_adj * unpriced
    gem = (v * q) ** 0.5 * (ng ** 0.75) if (v > 0 and q > 0 and ng > 0) else 0.0

    rev_gr  = g.get("revenue_growth") or 0.0
    earn_gr = g.get("earnings_growth") or 0.0
    if rev_gr < 0 and earn_gr < 0:
        gem *= 0.5
    elif earn_gr < 0 and rev_gr >= 0 and n_adj < 0.40:
        gem *= 0.75
    return round(min(gem, 1.0), 4)


def _tier(score):
    from pipeline.tiers import tier_for
    return tier_for(score)


def _screen(gems: list) -> list:
    from pipeline.tiers import WATCH
    return [g for g in gems
            if g["quality_score"]  >= SCREEN["quality"]
            and g.get("priced_in", 1.0) <= SCREEN["priced_in_max"]
            and g["value_score"]   >= SCREEN["value"]
            and g["narrative_score"] < SCREEN["narrative_below"]
            and g["hidden_gem_score"] <= WATCH]


def _assess(client, engine, g: dict) -> dict:
    """One LLM override judgement. Returns dict with override/narrative_adjusted/etc."""
    from pipeline.qual_assessor import get_stock_context, MODEL, build_prompt as _bp  # noqa: F401
    ctx = get_stock_context(engine, g["symbol"])
    # Reuse qual_assessor's context formatting by building its prompt, then
    # extracting nothing — instead format our own prompt with the same fields.
    fund = ctx["fund"]

    def fmt(v, pct=False):
        if v is None: return "n/a"
        v = float(v)
        return f"{v*100:.1f}%" if pct else f"{v:.2f}"

    call = ctx["call"]
    call_kw = {
        "last_call_date": str(call[6])[:10] if call else "n/a",
        "call_narrative_strength": fmt(call[0]) if call else "n/a",
        "call_trajectory": (call[1] or "n/a") if call else "n/a",
        "call_tone": (call[2] or "n/a") if call else "n/a",
    }
    def _j(blob, k, sep="; "):
        try:
            items = json.loads(blob) if blob else []
            return sep.join(items[:4]) if items else "n/a"
        except Exception:
            return str(blob)[:250] if blob else "n/a"
    call_kw["call_themes"]    = _j(call[3], 3) if call else "n/a"
    call_kw["call_catalysts"] = _j(call[4], 3) if call else "n/a"
    call_kw["call_risks"]     = _j(call[5], 3) if call else "n/a"

    filing = ctx["filing"]
    trend_rows = ctx.get("trend_rows", [])
    if trend_rows:
        lines = ["  Year    Revenue($M)  OpMgn%   ROIC%"]
        for r in trend_rows:
            period_end, revenue, _gm, om, _nm, _fcf, roic = r
            rev = f"{float(revenue)/1e6:,.0f}" if revenue else "n/a"
            lines.append(f"  {str(period_end)[:4]}    {rev:>10}  "
                         f"{fmt(om, pct=True):>7}  {fmt(roic, pct=True):>6}")
        trend = "\n".join(lines)
    else:
        trend = "  (no multi-year history available)"

    n = g["narrative_score"]
    prompt = OVERRIDE_PROMPT.format(
        symbol=g["symbol"],
        gem_score=fmt(g["hidden_gem_score"]),
        narrative_score=fmt(n), value_score=fmt(g["value_score"]),
        quality_score=fmt(g["quality_score"]), gap_score=fmt(g["gap_score"]),
        peg=fmt(g.get("peg_ratio")), fwd_pe=fmt(g.get("pe_forward")),
        rev_growth=fmt(g.get("revenue_growth"), pct=True),
        earn_growth=fmt(g.get("earnings_growth"), pct=True),
        roic=fmt(g.get("roic"), pct=True),
        themes="\n".join(f"  - {t['theme']} (score: {t['score']:.3f})"
                         for t in g.get("top_themes", [])) or "  (none)",
        filing_narrative_strength=fmt(filing[0]) if filing else "n/a",
        filing_trajectory=(filing[1] or "n/a") if filing else "n/a",
        filing_tone=(filing[2] or "n/a") if filing else "n/a",
        fundamental_trend=trend,
        max_boost=f"{MAX_BOOST:.2f}",
        max_narrative=f"{min(n + MAX_BOOST, 1.0):.2f}",
        **call_kw,
    )

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=700, timeout=45,
                messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]
            return json.loads(raw)
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return {"override": False, "evidence": "assessment failed",
            "rationale": "Assessment failed — no override", "key_bull": "", "key_bear": ""}


def run_narrative_override(engine, gems=None) -> dict:
    """
    Screen the scored universe, LLM-judge new/stale candidates (stored boosts
    fresher than REUSE_DAYS are reused without an LLM call), recompute adjusted
    gems, and stamp promotions into today's leaderboard_history.
    Idempotent; safe to call after every rescore.
    """
    from anthropic import Anthropic
    create_table(engine)

    if gems is None:
        from pipeline.hidden_gem_scorer import score_all_stocks
        gems = score_all_stocks(engine)

    candidates = _screen(gems)
    stats = {"screened": len(candidates), "llm_calls": 0,
             "overridden": 0, "declined": 0, "promoted": 0}
    if not candidates:
        _stamp(engine, [])
        print(f"Narrative override: {stats}")
        return stats

    with engine.connect() as conn:
        stored = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, narrative_adjusted, evidence, rationale,
                   key_bull, key_bear, assessed_at
            FROM narrative_overrides
            WHERE assessed_at > NOW() - (:d || ' days')::interval
        """), {"d": REUSE_DAYS}).fetchall()}

    client = Anthropic()
    promotions = []
    for g in candidates:
        sym, n = g["symbol"], g["narrative_score"]
        prior = stored.get(sym)
        if prior is not None:
            # Fresh judgement exists — reuse boost against today's components.
            boost = (float(prior[1]) - n) if prior[1] is not None else None
            result = {"override": prior[1] is not None,
                      "narrative_adjusted": float(prior[1]) if prior[1] is not None else None,
                      "evidence": prior[2], "rationale": prior[3],
                      "key_bull": prior[4], "key_bear": prior[5]}
            fresh_llm = False
        else:
            result = _assess(client, engine, g)
            stats["llm_calls"] += 1
            fresh_llm = True

        n_adj, gem_adj, tier, promoted = None, None, None, False
        if result.get("override") and result.get("narrative_adjusted") is not None:
            n_adj = max(n, min(float(result["narrative_adjusted"]), n + MAX_BOOST, 1.0))
            gem_adj = recompute_gem(g, n_adj)
            tier = _tier(gem_adj)
            promoted = tier is not None
            stats["overridden"] += 1
        else:
            stats["declined"] += 1
        if promoted:
            stats["promoted"] += 1
            promotions.append({"symbol": sym, "tier": tier, "gem_adjusted": gem_adj})

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO narrative_overrides
                    (symbol, narrative_raw, narrative_adjusted, gem_raw, gem_adjusted,
                     adjusted_tier, promoted, evidence, rationale, key_bull, key_bear, assessed_at)
                VALUES (:s, :nr, :na, :gr, :ga, :t, :p, :e, :r, :bull, :bear,
                        CASE WHEN :fresh THEN NOW() ELSE (
                            SELECT assessed_at FROM narrative_overrides WHERE symbol = :s) END)
                ON CONFLICT (symbol) DO UPDATE SET
                    narrative_raw = EXCLUDED.narrative_raw,
                    narrative_adjusted = EXCLUDED.narrative_adjusted,
                    gem_raw = EXCLUDED.gem_raw, gem_adjusted = EXCLUDED.gem_adjusted,
                    adjusted_tier = EXCLUDED.adjusted_tier, promoted = EXCLUDED.promoted,
                    evidence = EXCLUDED.evidence, rationale = EXCLUDED.rationale,
                    key_bull = EXCLUDED.key_bull, key_bear = EXCLUDED.key_bear,
                    assessed_at = CASE WHEN :fresh THEN NOW()
                                       ELSE narrative_overrides.assessed_at END
            """), {"s": sym, "nr": n, "na": n_adj, "gr": g["hidden_gem_score"],
                   "ga": gem_adj, "t": tier, "p": promoted,
                   "e": result.get("evidence", ""), "r": result.get("rationale", ""),
                   "bull": result.get("key_bull", ""), "bear": result.get("key_bear", ""),
                   "fresh": fresh_llm})

        flag = f"OVERRIDE n {n:.2f}->{n_adj:.2f} gem {g['hidden_gem_score']:.3f}->{gem_adj:.3f} [{tier}]" \
            if n_adj is not None else "declined"
        print(f"  {sym:<6} {flag}")

    _stamp(engine, promotions)
    print(f"Narrative override: {stats}")
    return stats


def _stamp(engine, promotions: list):
    """Stamp today's promotions into leaderboard_history; clear stale ones."""
    from sqlalchemy import bindparam
    with engine.begin() as conn:
        # Clear qual_promoted stamps on the latest snapshot that are no longer
        # backed by an active promotion (lapsed screen or lapsed override).
        conn.execute(text("""
            UPDATE leaderboard_history
            SET qual_promoted = FALSE, gem_adjusted = NULL,
                assessed_tier = CASE WHEN tier IS NULL THEN NULL ELSE assessed_tier END
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
              AND COALESCE(qual_promoted, FALSE)
              AND symbol NOT IN :syms
        """).bindparams(bindparam("syms", expanding=True)),
            {"syms": [p["symbol"] for p in promotions] or ["__none__"]})
        for p in promotions:
            conn.execute(text("""
                UPDATE leaderboard_history
                SET assessed_tier = :t, qual_promoted = TRUE, gem_adjusted = :ga
                WHERE date = (SELECT MAX(date) FROM leaderboard_history)
                  AND symbol = :s
            """), {"t": p["tier"], "ga": p["gem_adjusted"], "s": p["symbol"]})


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    run_narrative_override(get_engine())
