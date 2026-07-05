"""
Narrative Brain — schema and lifecycle engine for the meta-narrative system.

Architecture:
  narratives          — tiered entities (macro / sector / emerging / candidate)
                        with a thesis and explicit falsification conditions
  narrative_evidence  — append-only ledger; every pipeline feeds it; never wiped
  narrative_events    — creation, promotion, demotion, decline log
  narrative_exposures — per-stock exposure, assigned by LLM judgment WITH cited
                        evidence (replaces cosine-similarity alignment)

Lifecycle (evaluated every run, not on a calendar):
  candidate → emerging → sector → macro    promotion earned by breadth +
                                           financial confirmation
  any tier → declining → retired           falsification conditions met or
                                           cohort fundamentals diverge
"""
from sqlalchemy import text

TIERS = ["candidate", "emerging", "sector", "macro"]
STATUSES = ["active", "declining", "retired", "proposed"]


def create_schema(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS narratives (
                id            SERIAL PRIMARY KEY,
                name          VARCHAR(200) UNIQUE NOT NULL,
                tier          VARCHAR(20) NOT NULL DEFAULT 'candidate',
                status        VARCHAR(20) NOT NULL DEFAULT 'active',
                thesis        TEXT,               -- what the narrative claims
                description   TEXT,               -- one-liner for display
                sector_scope  VARCHAR(200),       -- NULL for macro
                falsification JSONB,              -- list of concrete kill conditions
                parent_id     INTEGER REFERENCES narratives(id),  -- sector -> macro link
                created_at    TIMESTAMP DEFAULT NOW(),
                promoted_at   TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS narrative_evidence (
                id           SERIAL PRIMARY KEY,
                narrative_id INTEGER NOT NULL REFERENCES narratives(id),
                evidence_date DATE NOT NULL,
                symbol       VARCHAR(10),
                source       VARCHAR(30) NOT NULL,   -- filing | 8k | earnings_call | fundamentals | price | insider
                stance       VARCHAR(15) NOT NULL,   -- confirming | contradicting
                excerpt      TEXT,                    -- the actual evidence, quoted or metric
                weight       NUMERIC(4,2) DEFAULT 1.0,
                created_at   TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS ix_nev_narrative_date
                ON narrative_evidence (narrative_id, evidence_date);

            CREATE TABLE IF NOT EXISTS narrative_events (
                id           SERIAL PRIMARY KEY,
                narrative_id INTEGER NOT NULL REFERENCES narratives(id),
                event_type   VARCHAR(30) NOT NULL,  -- created | promoted | demoted | declining | retired | user_override
                from_tier    VARCHAR(20),
                to_tier      VARCHAR(20),
                reason       TEXT,                   -- the evidence that triggered it
                created_at   TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS narrative_exposures (
                id           SERIAL PRIMARY KEY,
                symbol       VARCHAR(10) NOT NULL,
                narrative_id INTEGER NOT NULL REFERENCES narratives(id),
                exposure     NUMERIC(4,3) NOT NULL,  -- 0-1, LLM-judged
                evidence     TEXT,                    -- cited: segments, backlog, revenue %
                updated_at   TIMESTAMP DEFAULT NOW(),
                UNIQUE (symbol, narrative_id)
            );
        """))
    print("✓ Narrative brain schema ready")


def log_event(engine, narrative_id: int, event_type: str,
              from_tier: str = None, to_tier: str = None, reason: str = ""):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO narrative_events (narrative_id, event_type, from_tier, to_tier, reason)
            VALUES (:nid, :et, :ft, :tt, :r)
        """), {"nid": narrative_id, "et": event_type, "ft": from_tier,
               "tt": to_tier, "r": reason})


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    create_schema(get_engine())
