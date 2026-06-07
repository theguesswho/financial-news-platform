"""
Migration script to add new user/watchlist/portfolio tables to PostgreSQL.

Run this once to set up the schema for the new product features.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load env
root = Path(__file__).parent.parent
load_dotenv(root / ".env", override=True)

# Get database URL
DB_HOST = os.environ.get("DB_HOST_IP", "localhost")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "financial_news")
DB_PORT = os.environ.get("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create engine and run migrations
engine = create_engine(DATABASE_URL)

migration_sql = """
-- Add columns to fundamentals table
ALTER TABLE fundamentals
ADD COLUMN IF NOT EXISTS sector VARCHAR(100),
ADD COLUMN IF NOT EXISTS industry VARCHAR(200),
ADD COLUMN IF NOT EXISTS short_percent_float NUMERIC(10, 4),
ADD COLUMN IF NOT EXISTS analyst_rating VARCHAR(50),
ADD COLUMN IF NOT EXISTS analyst_target_price NUMERIC(12, 2),
ADD COLUMN IF NOT EXISTS analysts_count INTEGER;

CREATE INDEX IF NOT EXISTS idx_fundamentals_sector ON fundamentals(sector);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,
    email_verified BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create watchlist_entries table (replaces old watchlist table structure)
-- First, back up old data if it exists
CREATE TABLE IF NOT EXISTS watchlist_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    symbol VARCHAR(10) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    entry_price NUMERIC(12, 2),
    entry_score NUMERIC(10, 4),
    notes TEXT,
    alerts_enabled BOOLEAN DEFAULT TRUE,
    alerts_config JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_symbol ON watchlist_entries(symbol);

-- Create portfolio_holdings table
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    symbol VARCHAR(10) NOT NULL,
    shares NUMERIC(16, 2) NOT NULL,
    entry_price NUMERIC(12, 2) NOT NULL,
    entry_date DATE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    UNIQUE(user_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_symbol ON portfolio_holdings(symbol);

-- Create daily_scores table (time-series of V2 scores)
CREATE TABLE IF NOT EXISTS daily_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    v2_score NUMERIC(10, 4) NOT NULL,
    quality_score NUMERIC(10, 4),
    value_score NUMERIC(10, 4),
    trajectory_score NUMERIC(10, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_scores_date ON daily_scores(symbol, date);

-- Create user_activity_log table
CREATE TABLE IF NOT EXISTS user_activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    symbol VARCHAR(10),
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_activity_user ON user_activity_log(user_id);

-- Success message
SELECT 'Migration complete!';
"""

try:
    with engine.connect() as connection:
        # Execute migration
        connection.execute(text(migration_sql))
        connection.commit()
        print("✓ Migration successful: All tables created/updated")
except Exception as e:
    print(f"✗ Migration failed: {e}")
    sys.exit(1)
