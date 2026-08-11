from datetime import datetime

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Integer,
    Numeric, String, Text, UniqueConstraint, Boolean, ForeignKey, JSON,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Filing(Base):
    __tablename__ = "filings"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    cik = Column(String(20))
    filing_type = Column(String(10))          # 10-K, 10-Q, 8-K
    title = Column(String(500))
    url = Column(String(1000), unique=True, nullable=False)
    filing_date = Column(DateTime)
    content = Column(Text)                    # truncated scraped text
    event_type = Column(String(30))          # for 8-Ks: EARNINGS, M&A, EXEC_CHANGE, GUIDANCE, etc.
    llm_analysis = Column(Text)              # JSON: summary, risks, opportunities, etc.
    master_analysis = Column(Text)           # prose synthesis with market context
    sentiment_score = Column(Integer)        # -10 (bearish) to +10 (bullish)
    # processed_at retired 2026-08-11 (audit): written inconsistently by
    # legacy paths only, read by nothing, and it misled two audits into
    # "unprocessed content" false alarms. Coverage truth lives in
    # llm_analysis (8-Ks) and filing_themes (10-K/Q, transcripts).
    created_at = Column(DateTime, default=datetime.utcnow)


class Fundamentals(Base):
    """
    Key financial ratios and quarterly trend data per stock.
    Fetched from yfinance. Updated periodically.
    """
    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    # ── Valuation ──────────────────────────────────────────
    pe_trailing         = Column(Numeric(12, 2))
    pe_forward          = Column(Numeric(12, 2))
    peg_ratio           = Column(Numeric(12, 2))   # consensus (peg_normalizer owns)
    peg_vendor          = Column(Numeric(12, 2))   # Yahoo's raw pegRatio (5-yr expected)
    peg_source          = Column(String(10))       # 'vendor' (primary) | 'consensus' (fallback)
    price_to_book       = Column(Numeric(12, 2))
    price_to_fcf        = Column(Numeric(12, 2))
    ev_to_ebitda        = Column(Numeric(12, 2))
    ev_to_fcf           = Column(Numeric(12, 2))

    # ── Quality ────────────────────────────────────────────
    roe                 = Column(Numeric(10, 4))   # Return on Equity
    roic                = Column(Numeric(10, 4))   # Return on Invested Capital (approx)
    gross_margin        = Column(Numeric(10, 4))
    operating_margin    = Column(Numeric(10, 4))
    net_margin          = Column(Numeric(10, 4))
    fcf_margin          = Column(Numeric(10, 4))   # FCF / Revenue

    # ── Balance sheet ──────────────────────────────────────
    debt_to_equity      = Column(Numeric(10, 4))
    current_ratio       = Column(Numeric(10, 4))
    interest_coverage   = Column(Numeric(10, 2))

    # ── Growth (YoY, from most recent quarter) ─────────────
    revenue_growth_yoy  = Column(Numeric(10, 4))
    earnings_growth_yoy = Column(Numeric(10, 4))
    fcf_growth_yoy      = Column(Numeric(10, 4))

    # ── Trend data (last 8 quarters, JSON) ─────────────────
    # {"revenue": [...], "gross_margin": [...], "operating_margin": [...],
    #  "net_income": [...], "fcf": [...], "dates": [...]}
    quarterly_trends    = Column(Text)

    # ── Market context ─────────────────────────────────────
    market_cap          = Column(Numeric(20, 0))
    enterprise_value    = Column(Numeric(20, 0))
    fifty_two_week_low  = Column(Numeric(12, 2))
    fifty_two_week_high = Column(Numeric(12, 2))
    price_vs_52w_high   = Column(Numeric(10, 4))   # 0-1, where 1 = at 52w high

    # ── Sector & Industry ──────────────────────────────────
    sector              = Column(String(100))
    industry            = Column(String(200))
    company_name        = Column(String(200))

    # ── Market sentiment ───────────────────────────────────
    short_percent_float = Column(Numeric(10, 4))   # % of float shorted
    analyst_rating      = Column(String(50))       # e.g., "Strong Buy", "Buy", "Hold"
    analyst_target_price = Column(Numeric(12, 2)) # consensus price target
    analysts_count      = Column(Integer)          # number of analysts in consensus


class HistoricalMetrics(Base):
    """
    Quarterly snapshot of key financial metrics from FMP.
    One row per (symbol, quarter-end date). Used for backtesting.
    """
    __tablename__ = "historical_metrics"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False)            # quarter-end date

    # Valuation (as of that quarter-end)
    pe_ratio        = Column(Numeric(12, 4))
    pfcf_ratio      = Column(Numeric(12, 4))
    ev_to_ebitda    = Column(Numeric(12, 4))
    price_to_book   = Column(Numeric(12, 4))
    ev_to_fcf       = Column(Numeric(12, 4))

    # Quality
    roic            = Column(Numeric(10, 6))
    roe             = Column(Numeric(10, 6))
    gross_margin    = Column(Numeric(10, 6))
    operating_margin = Column(Numeric(10, 6))
    net_margin      = Column(Numeric(10, 6))
    interest_coverage = Column(Numeric(10, 2))
    debt_to_equity  = Column(Numeric(10, 4))
    current_ratio   = Column(Numeric(10, 4))

    # Raw financials (for growth calculation)
    revenue         = Column(Numeric(20, 0))
    net_income      = Column(Numeric(20, 0))
    gross_profit    = Column(Numeric(20, 0))
    operating_income = Column(Numeric(20, 0))
    market_cap      = Column(Numeric(20, 0))

    __table_args__ = (UniqueConstraint("symbol", "date", name="_hm_symbol_date_uc"),)


class User(Base):
    """User account for watchlist, portfolio, and alerts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    email_verified = Column(Boolean, default=False)


class WatchlistEntry(Base):
    """Watchlist entry with user, entry price, notes, and alert config."""
    __tablename__ = "watchlist_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    entry_price = Column(Numeric(12, 2))        # optional, for tracking P&L
    entry_score = Column(Numeric(10, 4))        # V2 score when added (optional)
    notes = Column(Text)                         # user's thesis/notes
    alerts_enabled = Column(Boolean, default=True)
    alerts_config = Column(JSON)                 # {score_below, score_above, margin_change_pp, insider_spike, new_filing}
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="_watchlist_user_symbol_uc"),
    )


class PortfolioHolding(Base):
    """User's portfolio holding of a stock."""
    __tablename__ = "portfolio_holdings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    shares = Column(Numeric(16, 2), nullable=False)
    entry_price = Column(Numeric(12, 2), nullable=False)
    entry_date = Column(Date)
    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text)

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="_portfolio_user_symbol_uc"),
    )


class DailyScore(Base):
    """Time-series of daily V2 scores for each stock."""
    __tablename__ = "daily_scores"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False)
    v2_score = Column(Numeric(10, 4), nullable=False)
    quality_score = Column(Numeric(10, 4))
    value_score = Column(Numeric(10, 4))
    trajectory_score = Column(Numeric(10, 4))
    narrative_score = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="_daily_score_symbol_date_uc"),
    )


class UserActivityLog(Base):
    """Audit log of user actions (added watchlist, removed portfolio, etc.)."""
    __tablename__ = "user_activity_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # added_watchlist, removed_watchlist, added_portfolio, etc.
    symbol = Column(String(10), index=True)      # nullable if not stock-specific
    details = Column(JSON)                        # arbitrary action details
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyBrief(Base):
    __tablename__ = "daily_briefs"
    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    content = Column(Text)          # JSON: top_signal, watch_list, on_radar
    generated_at = Column(DateTime, default=datetime.utcnow)


class ScreenerResult(Base):
    """Lightweight screener entry — one per symbol, updated on each screener run."""
    __tablename__ = "screener_results"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, unique=True, index=True)
    company_name = Column(String(200))
    filing_type = Column(String(10))
    filing_date = Column(DateTime)
    v2_mismatch_score = Column(Numeric(10, 4))  # 0-1, primary ranking signal
    sentiment_score = Column(Integer)           # -10 to +10, from filing analysis
    one_liner = Column(Text)          # 1 sentence plain-text summary
    latest_close = Column(Numeric(12, 4))
    price_change_pct = Column(Numeric(8, 4))  # vs prior day
    generated_at = Column(DateTime, default=datetime.utcnow)


class InsiderTrade(Base):
    """A single transaction from a Form 4 filing."""
    __tablename__ = "insider_trades"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    person_name = Column(String(200))
    person_title = Column(String(200))
    transaction_date = Column(Date, nullable=False)
    transaction_type = Column(String(10))   # BUY, SELL, AWARD, OTHER
    shares = Column(Numeric(16, 2))
    price_per_share = Column(Numeric(12, 4))
    total_value = Column(Numeric(20, 2))
    shares_owned_after = Column(Numeric(16, 2))
    form4_url = Column(String(1000))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "person_name", "transaction_date", "transaction_type", "shares",
                         name="_insider_trade_uc"),
    )


class EodPrice(Base):
    __tablename__ = "eod_prices"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Numeric(12, 4))
    high = Column(Numeric(12, 4))
    low = Column(Numeric(12, 4))
    close = Column(Numeric(12, 4))
    volume = Column(BigInteger)

    __table_args__ = (UniqueConstraint("symbol", "date", name="_symbol_date_uc"),)
