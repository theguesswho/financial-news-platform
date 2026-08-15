"""
Leaderboard History Archiver

Archives daily gem scores and leaderboard ranks so the Home page can show
new entrants and rank-change badges vs the previous session.

Table: leaderboard_history
  id, date, symbol, gem_score, tier, rank, assessed_tier

Run automatically from the daily scheduler (Step 5b).
"""
from datetime import date, timedelta
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)


def create_table(engine):
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS leaderboard_history (
                id              SERIAL PRIMARY KEY,
                date            DATE          NOT NULL,
                symbol          VARCHAR(10)   NOT NULL,
                gem_score       NUMERIC(10,6) NOT NULL,
                tier            VARCHAR(20),
                rank            INTEGER,
                assessed_tier   VARCHAR(20),
                narrative_score NUMERIC(10,4),
                value_score     NUMERIC(10,4),
                quality_score   NUMERIC(10,4),
                gap_score       NUMERIC(10,4),
                UNIQUE (date, symbol)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_lh_date "
            "ON leaderboard_history (date DESC)"
        ))
        # Migrations for existing tables
        for col, defn in [
            ("assessed_tier",   "VARCHAR(20)"),
            ("narrative_score", "NUMERIC(10,4)"),
            ("value_score",     "NUMERIC(10,4)"),
            ("quality_score",   "NUMERIC(10,4)"),
            ("gap_score",       "NUMERIC(10,4)"),
            ("priced_in",       "NUMERIC(10,4)"),
            ("ng_score",        "NUMERIC(10,4)"),
        ]:
            conn.execute(text(
                f"ALTER TABLE leaderboard_history ADD COLUMN IF NOT EXISTS {col} {defn}"
            ))
        conn.commit()


def archive_leaderboard(engine, gems=None) -> dict:
    """
    Snapshot today's gem scores and leaderboard ranks.
    Always upserts — safe to call after every rescore.
    Pass pre-computed gems to avoid a redundant score_all_stocks() call.
    """
    if gems is None:
        from pipeline.hidden_gem_scorer import score_all_stocks
        gems = score_all_stocks(engine)

    today = date.today()

    from pipeline.tiers import tier_for, WATCH, BOARD_EXIT

    # Exit hysteresis (user-approved 2026-08-01): stocks on YESTERDAY's board
    # whose score dipped into the [BOARD_EXIT, WATCH] band keep their Watch
    # seat — a wobble at the line is not an exit. Below BOARD_EXIT, they leave.
    from sqlalchemy import text as _t
    with engine.connect() as _c:
        _prev_board = {r[0] for r in _c.execute(_t("""
            SELECT symbol FROM leaderboard_history
            WHERE date = (SELECT MAX(date) FROM leaderboard_history
                          WHERE date < CURRENT_DATE)
              AND tier IS NOT NULL""")).fetchall()}

    def tier_with_hysteresis(g):
        t = tier_for(g["hidden_gem_score"])
        if t is None and g["symbol"] in _prev_board                 and BOARD_EXIT < g["hidden_gem_score"] <= WATCH:
            return "Watch"
        return t

    TIER_ORDER = {"Strong Buy": 0, "Buy": 1, "Watch": 2}

    on_board = sorted(
        [g for g in gems if tier_with_hysteresis(g) is not None],
        key=lambda g: (TIER_ORDER.get(tier_with_hysteresis(g), 3), -g["hidden_gem_score"])
    )

    rows = []
    for rank, g in enumerate(on_board, 1):
        rows.append({
            "date":            today,
            "symbol":          g["symbol"],
            "gem_score":       g["hidden_gem_score"],
            "tier":            tier_with_hysteresis(g),
            "rank":            rank,
            "narrative_score": g.get("narrative_score"),
            "value_score":     g.get("value_score"),
            "quality_score":   g.get("quality_score"),
            "gap_score":       g.get("gap_score"),
            "priced_in":       g.get("priced_in"),
            "ng_score":        g.get("ng_score"),
        })

    on_board_syms = {r["symbol"] for r in rows}
    for g in gems:
        if g["symbol"] not in on_board_syms:
            rows.append({
                "date":            today,
                "symbol":          g["symbol"],
                "gem_score":       g["hidden_gem_score"],
                "tier":            None,
                "rank":            None,
                "narrative_score": g.get("narrative_score"),
                "value_score":     g.get("value_score"),
                "quality_score":   g.get("quality_score"),
                "gap_score":       g.get("gap_score"),
                "priced_in":       g.get("priced_in"),
                "ng_score":        g.get("ng_score"),
            })

    upsert = text("""
        INSERT INTO leaderboard_history
            (date, symbol, gem_score, tier, rank,
             narrative_score, value_score, quality_score, gap_score,
             priced_in, ng_score)
        VALUES
            (:date, :symbol, :gem_score, :tier, :rank,
             :narrative_score, :value_score, :quality_score, :gap_score,
             :priced_in, :ng_score)
        ON CONFLICT (date, symbol) DO UPDATE SET
            gem_score       = EXCLUDED.gem_score,
            tier            = EXCLUDED.tier,
            rank            = EXCLUDED.rank,
            narrative_score = EXCLUDED.narrative_score,
            value_score     = EXCLUDED.value_score,
            quality_score   = EXCLUDED.quality_score,
            gap_score       = EXCLUDED.gap_score,
            priced_in       = EXCLUDED.priced_in,
            ng_score        = EXCLUDED.ng_score
    """)
    # Chunked with per-chunk commits — a single 500-row payload can be killed
    # mid-send by the Railway proxy when written from outside the datacenter.
    CHUNK = 100
    for i in range(0, len(rows), CHUNK):
        with engine.begin() as conn:
            conn.execute(upsert, rows[i:i + CHUNK])

    return {"archived": len(rows), "on_board": len(on_board)}


def apply_qual_tiers(engine) -> int:
    """
    After qual_assessor runs, stamp adjusted_tier from qual_assessments back
    into today's leaderboard_history rows so that tomorrow's move-detection
    compares against the final qual-adjusted tier, not the raw gem-score tier.
    Returns the number of rows updated.
    """
    with engine.connect() as conn:
        # Only stamp stocks currently on the board; a qual opinion from when a
        # stock last qualified must not resurrect it after its score drops off.
        result = conn.execute(text("""
            UPDATE leaderboard_history lh
            SET assessed_tier = qa.adjusted_tier
            FROM qual_assessments qa
            WHERE lh.symbol = qa.symbol
              AND lh.tier IS NOT NULL
              AND lh.date   = (SELECT MAX(date) FROM leaderboard_history)
        """))
        # qual_promoted rows legitimately carry assessed_tier with tier NULL
        # (narrative-override promotions) — never wipe those here.
        conn.execute(text("""
            UPDATE leaderboard_history
            SET assessed_tier = NULL
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
              AND tier IS NULL AND assessed_tier IS NOT NULL
              AND NOT COALESCE(qual_promoted, FALSE)
        """))
        # FINAL RANK (user 2026-08-03): the position after qual adjustment —
        # what the investor actually experiences. Quant rank stays in `rank`;
        # the two together make the qual layer's influence measurable.
        conn.execute(text(
            "ALTER TABLE leaderboard_history ADD COLUMN IF NOT EXISTS final_rank INTEGER"))
        conn.execute(text("""
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    ORDER BY CASE COALESCE(assessed_tier, tier)
                        WHEN 'Strong Buy' THEN 0 WHEN 'Buy' THEN 1
                        WHEN 'Watch' THEN 2 ELSE 3 END,
                    COALESCE(gem_adjusted, gem_score) DESC) AS fr
                FROM leaderboard_history
                WHERE date = (SELECT MAX(date) FROM leaderboard_history)
                  AND (COALESCE(assessed_tier, tier) IN ('Strong Buy','Buy','Watch'))
            )
            UPDATE leaderboard_history lh SET final_rank = ranked.fr
            FROM ranked WHERE lh.id = ranked.id"""))
        conn.execute(text("""
            UPDATE leaderboard_history SET final_rank = NULL
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
              AND COALESCE(assessed_tier, tier) NOT IN ('Strong Buy','Buy','Watch')"""))
        conn.commit()
    return result.rowcount


def get_prev_leaderboard(engine) -> dict:
    """
    Return previous session's leaderboard as {symbol: rank}.
    Returns {} if no history exists yet.
    """
    with engine.connect() as conn:
        prev_date = conn.execute(text("""
            SELECT date FROM leaderboard_history
            WHERE date < CURRENT_DATE
            GROUP BY date ORDER BY date DESC LIMIT 1
        """)).scalar()
        if prev_date is None:
            return {}
        rows = conn.execute(text("""
            SELECT symbol, rank FROM leaderboard_history
            WHERE date = :d AND rank IS NOT NULL
        """), {"d": prev_date}).fetchall()
    return {r[0]: r[1] for r in rows}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from pipeline.hidden_gem_scorer import get_engine
    engine = get_engine()
    create_table(engine)
    result = archive_leaderboard(engine)
    print(f"✅ {result}")


def apply_materiality_holds(engine) -> list:
    """Tier-materiality corridor (user-approved 2026-08-15, all drivers).
    When yesterday's FINAL tier was Strong Buy or Buy and today's RAW band
    is lower but the raw score sits within 10% of the lost band's floor,
    the tier is HELD pending the assessor's materiality ruling that same
    run (the machinery adjudicates — never auto-demote inside the
    corridor, never hold below it). Returns hold descriptors for the
    qual sweep to turn into materiality triggers.
    Scope: SB and Buy floors; holds require today's raw tier on-board.
    """
    FLOORS = {"Strong Buy": 0.46, "Buy": 0.36}
    ORDER = {None: 0, "Watch": 1, "Buy": 2, "Strong Buy": 3}
    holds = []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH cur AS (SELECT * FROM leaderboard_history
                         WHERE date = (SELECT MAX(date) FROM leaderboard_history)),
                 prev AS (SELECT * FROM leaderboard_history
                          WHERE date = (SELECT MAX(date) FROM leaderboard_history
                                        WHERE date < (SELECT MAX(date) FROM leaderboard_history)))
            SELECT c.symbol, COALESCE(p.assessed_tier, p.tier) AS prev_final,
                   c.tier AS raw_band, c.gem_score,
                   p.gem_score, c.quality_score, p.quality_score,
                   c.narrative_score, p.narrative_score,
                   c.priced_in, p.priced_in
            FROM cur c JOIN prev p USING (symbol)
            WHERE c.tier IS NOT NULL
        """)).fetchall()
        for (sym, prev_final, raw_band, g, g0, q, q0, n, n0, pi, pi0) in rows:
            if prev_final not in FLOORS:
                continue
            if ORDER.get(raw_band, 0) >= ORDER[prev_final]:
                continue                                   # no downward breach
            floor = FLOORS[prev_final]
            g = float(g)
            if g < floor * 0.9:
                continue                                   # beyond corridor: falls
            dq = float(q or 0) - float(q0 or 0)
            dn = float(n or 0) - float(n0 or 0)
            evidence = abs(dq) >= 0.005 or abs(dn) >= 0.005
            holds.append({
                "symbol": sym, "held": prev_final, "raw_band": raw_band,
                "gap_pct": round((floor - g) / floor * 100, 1),
                "evidence": evidence, "dq": round(dq, 3), "dn": round(dn, 3),
                "dp": round(float(pi or 0) - float(pi0 or 0), 3)})
        for h in holds:
            conn.execute(text("""
                UPDATE leaderboard_history SET assessed_tier = :t
                WHERE symbol = :s AND date = (SELECT MAX(date) FROM leaderboard_history)
            """), {"t": h["held"], "s": h["symbol"]})
        conn.commit()
    if holds:
        print(f"  materiality corridor: holding {[h['symbol'] for h in holds]} pending ruling")
    return holds


def materiality_reason(h: dict) -> str:
    """The asymmetric-bar question the assessor must answer for a hold."""
    core = (f"MATERIALITY RULING REQUIRED: the raw score slipped below the "
            f"{h['held']} floor by {h['gap_pct']}% (within the 10% corridor; "
            f"beyond 10% the tier falls with no ruling). Component moves: "
            f"quality {h['dq']:+}, story exposure {h['dn']:+}, priced-in {h['dp']:+}. ")
    if h["evidence"]:
        return core + (
            "This breach involves EVIDENCE movement, so the bar is high: to hold "
            "the tier you must cite the specific evidence and name a concrete "
            "noise mechanism (an active platform note, a vendor restatement, a "
            "single-narrative reweight with breadth intact). 'The thesis is "
            "still good' is NOT a noise mechanism. An evidence-based hold "
            "lapses at the company's next earnings — it must be re-earned from "
            "fresh filings. Rule HOLD (state the mechanism) or DEMOTE.")
    return core + (
        "This is a PRICE-driven breach (quality and story unchanged): rule "
        "whether the market move is material to the opportunity. A drift of "
        "rounding size is not material; a genuine repricing that consumed the "
        "opportunity is. Rule HOLD or DEMOTE and say why in one sentence.")
