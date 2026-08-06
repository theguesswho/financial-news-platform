"""
Shadow lane (P3) — the three candidate designs for wiring company
narratives into scoring, computed daily alongside the LIVE score, which
remains untouched. Pure arithmetic, zero LLM cost. The shadow data — not
taste — picks the design (spec §4); one design ships only after user
sign-off over the day-5 interim and final reports.

  Design A: company story as an extra exposure in the noisy-OR
            E_a = 1 - (1 - E_live) * (1 - maturity)
  Design B: a stock's exposure is its BEST story, never the sum
            E_b = max(E_live, maturity)
  Design C: company channel occupies the bounded override-boost slot
            E_c = min(E_live + 0.40 * maturity, 1.0)

maturity is the DATA-LINKED corroboration score (claims contribute zero;
delivered evidence and confirmed predictions are the only inputs), so a
salesman-only story shadows at ~nothing under every design.
"""
from sqlalchemy import text

DESIGNS = ("A", "B", "C")
C_SLOT = 0.40   # mirrors the override MAX_BOOST semantics


def create_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS shadow_scores (
                date        DATE NOT NULL,
                symbol      VARCHAR(10) NOT NULL,
                design      CHAR(1) NOT NULL,
                maturity    NUMERIC(6,3),
                e_live      NUMERIC(6,3),
                e_shadow    NUMERIC(6,3),
                gem_live    NUMERIC(10,4),
                gem_shadow  NUMERIC(10,4),
                tier_live   VARCHAR(20),
                tier_shadow VARCHAR(20),
                PRIMARY KEY (date, symbol, design)
            )"""))


def compute_shadow(engine, gems: list) -> dict:
    """Compute all three designs for every stock holding an active company
    narrative. gems = the freshly scored universe (from score_all_stocks) —
    passed in so nothing is re-scored."""
    from pipeline.narrative_override import recompute_gem
    from pipeline.tiers import tier_for

    create_table(engine)
    with engine.connect() as conn:
        maturities = dict(conn.execute(text("""
            SELECT symbol, maturity FROM narratives
            WHERE scope = 'company' AND status IN ('active', 'candidate')
        """)).fetchall())
    stats = {"symbols": 0, "tier_diffs": {d: 0 for d in DESIGNS}}
    if not maturities:
        return stats

    by_sym = {g["symbol"]: g for g in gems}
    rows = []
    for sym, m in maturities.items():
        g = by_sym.get(sym)
        if g is None:
            continue
        m = float(m)
        e = g["narrative_score"]
        shadows = {
            "A": 1 - (1 - e) * (1 - m),
            "B": max(e, m),
            "C": min(e + C_SLOT * m, 1.0),
        }
        stats["symbols"] += 1
        for d, e_s in shadows.items():
            gem_s = recompute_gem(g, e_s)
            t_live = tier_for(g["hidden_gem_score"])
            t_shadow = tier_for(gem_s)
            if t_live != t_shadow:
                stats["tier_diffs"][d] += 1
            rows.append({"sym": sym, "d": d, "m": round(m, 3),
                         "el": round(e, 3), "es": round(e_s, 3),
                         "gl": g["hidden_gem_score"], "gs": gem_s,
                         "tl": t_live, "ts": t_shadow})
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO shadow_scores (date, symbol, design, maturity,
                    e_live, e_shadow, gem_live, gem_shadow, tier_live, tier_shadow)
                VALUES (CURRENT_DATE, :sym, :d, :m, :el, :es, :gl, :gs, :tl, :ts)
                ON CONFLICT (date, symbol, design) DO UPDATE SET
                    maturity = EXCLUDED.maturity, e_shadow = EXCLUDED.e_shadow,
                    gem_shadow = EXCLUDED.gem_shadow,
                    tier_shadow = EXCLUDED.tier_shadow,
                    e_live = EXCLUDED.e_live, gem_live = EXCLUDED.gem_live,
                    tier_live = EXCLUDED.tier_live
            """), r)
    print(f"shadow lane: {stats['symbols']} stocks, tier diffs "
          + ", ".join(f"{d}:{stats['tier_diffs'][d]}" for d in DESIGNS))
    return stats


def shadow_summary(engine) -> str:
    """One plain-language paragraph for the daily brief's Shadow Lane
    section: what each candidate design would change on today's board."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT design, symbol, tier_live, tier_shadow, gem_live, gem_shadow
            FROM shadow_scores
            WHERE date = (SELECT MAX(date) FROM shadow_scores)
              AND tier_live IS DISTINCT FROM tier_shadow
            ORDER BY design, gem_shadow DESC""")).fetchall()
    if rows is None:
        return ""
    by_design: dict[str, list] = {}
    for d, sym, tl, ts, gl, gs in rows:
        by_design.setdefault(d, []).append(
            f"{sym} {tl or 'off board'}→{ts or 'off board'} "
            f"({float(gl)*10:.1f}→{float(gs)*10:.1f})")
    if not by_design:
        return ("Shadow test of the three company-story designs: no board "
                "differences today — all three agree with the live score.")
    parts = []
    for d in DESIGNS:
        moves = by_design.get(d)
        if moves:
            shown = "; ".join(moves[:4]) + (f" (+{len(moves)-4} more)" if len(moves) > 4 else "")
            parts.append(f"Design {d} would move: {shown}")
        else:
            parts.append(f"Design {d}: no differences")
    return "Shadow test of the three company-story designs (live scores untouched): " + ". ".join(parts) + "."


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
    eng = get_engine()
    compute_shadow(eng, score_all_stocks(eng))
    print(shadow_summary(eng))
