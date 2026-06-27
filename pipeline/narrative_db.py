"""
Create and manage narrative database tables.
Three tables:
  filing_themes       — structured theme extraction per filing
  meta_themes         — canonical themes built by clustering
  stock_theme_alignment — per-stock alignment to each meta-theme
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(override=True)


def get_engine():
    if os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
        from sqlalchemy import create_engine
        return create_engine(url, pool_pre_ping=True)
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}/{name}", pool_pre_ping=True)


def create_tables():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS filing_themes (
                id              SERIAL PRIMARY KEY,
                filing_id       INT UNIQUE REFERENCES filings(id) ON DELETE CASCADE,
                symbol          VARCHAR(10),
                filing_type     VARCHAR(10),
                filing_date     TIMESTAMP,
                raw_themes      JSONB,
                trajectory      VARCHAR(20),
                narrative_strength FLOAT,
                management_tone VARCHAR(20),
                catalysts       JSONB,
                risks           JSONB,
                extracted_at    TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meta_themes (
                id                  SERIAL PRIMARY KEY,
                name                VARCHAR(200) UNIQUE,
                description         TEXT,
                constituent_themes  JSONB,
                company_count       INT DEFAULT 0,
                sector_count        INT DEFAULT 0,
                momentum            VARCHAR(20),
                updated_at          TIMESTAMP DEFAULT NOW()
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_theme_alignment (
                id              SERIAL PRIMARY KEY,
                symbol          VARCHAR(10),
                meta_theme_id   INT REFERENCES meta_themes(id) ON DELETE CASCADE,
                alignment_score FLOAT,
                trajectory      VARCHAR(20),
                quarter_scores  JSONB,
                updated_at      TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, meta_theme_id)
            );
        """))

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_filing_themes_symbol ON filing_themes(symbol);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_filing_themes_date ON filing_themes(filing_date);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stock_theme_symbol ON stock_theme_alignment(symbol);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stock_theme_score ON stock_theme_alignment(alignment_score DESC);"))

        conn.commit()
    print("✅ Narrative tables ready")


if __name__ == "__main__":
    create_tables()
