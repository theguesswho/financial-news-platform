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

    def tier_for(s):
        if s is None: return None
        if s > 0.58: return "Strong Buy"
        if s > 0.46: return "Buy"
        if s > 0.34: return "Watch"
        return None

    TIER_ORDER = {"Strong Buy": 0, "Buy": 1, "Watch": 2}

    on_board = sorted(
        [g for g in gems if tier_for(g["hidden_gem_score"]) is not None],
        key=lambda g: (TIER_ORDER.get(tier_for(g["hidden_gem_score"]), 3), -g["hidden_gem_score"])
    )

    rows = []
    for rank, g in enumerate(on_board, 1):
        rows.append({
            "date":            today,
            "symbol":          g["symbol"],
            "gem_score":       g["hidden_gem_score"],
            "tier":            tier_for(g["hidden_gem_score"]),
            "rank":            rank,
            "narrative_score": g.get("narrative_score"),
            "value_score":     g.get("value_score"),
            "quality_score":   g.get("quality_score"),
            "gap_score":       g.get("gap_score"),
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
            })

    upsert = text("""
        INSERT INTO leaderboard_history
            (date, symbol, gem_score, tier, rank,
             narrative_score, value_score, quality_score, gap_score)
        VALUES
            (:date, :symbol, :gem_score, :tier, :rank,
             :narrative_score, :value_score, :quality_score, :gap_score)
        ON CONFLICT (date, symbol) DO UPDATE SET
            gem_score       = EXCLUDED.gem_score,
            tier            = EXCLUDED.tier,
            rank            = EXCLUDED.rank,
            narrative_score = EXCLUDED.narrative_score,
            value_score     = EXCLUDED.value_score,
            quality_score   = EXCLUDED.quality_score,
            gap_score       = EXCLUDED.gap_score
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
        conn.execute(text("""
            UPDATE leaderboard_history
            SET assessed_tier = NULL
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
              AND tier IS NULL AND assessed_tier IS NOT NULL
        """))
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
