"""
Pydantic models for API request/response validation.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


# ──────────────────────────────────────────────────────────────────────────
# User & Auth Schemas
# ──────────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=255)


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    """User public profile response."""
    id: int
    email: str
    name: str
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────
# Watchlist Schemas
# ──────────────────────────────────────────────────────────────────────────

class AlertConfig(BaseModel):
    """Alert configuration for a watchlist entry."""
    score_below: Optional[float] = None  # Alert if score drops below this
    score_above: Optional[float] = None  # Alert if score rises above this
    margin_change_pp: Optional[float] = None  # Alert if margin changes by this many pp
    insider_spike: Optional[bool] = None  # Alert on insider buying spike
    new_filing: Optional[bool] = None  # Alert on new SEC filing


class WatchlistEntryCreate(BaseModel):
    """Create watchlist entry request."""
    symbol: str = Field(pattern="^[A-Z]{1,5}$")
    entry_price: Optional[float] = None
    notes: Optional[str] = None
    alerts_enabled: bool = True
    alerts_config: Optional[AlertConfig] = None


class WatchlistEntryUpdate(BaseModel):
    """Update watchlist entry request."""
    entry_price: Optional[float] = None
    notes: Optional[str] = None
    alerts_enabled: Optional[bool] = None
    alerts_config: Optional[AlertConfig] = None


class WatchlistEntryResponse(BaseModel):
    """Watchlist entry response."""
    id: int
    symbol: str
    added_at: datetime
    entry_price: Optional[float]
    entry_score: Optional[float]
    notes: Optional[str]
    alerts_enabled: bool
    alerts_config: Optional[Dict[str, Any]]
    updated_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────
# Portfolio Schemas
# ──────────────────────────────────────────────────────────────────────────

class PortfolioHoldingCreate(BaseModel):
    """Create portfolio holding request."""
    symbol: str = Field(pattern="^[A-Z]{1,5}$")
    shares: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    entry_date: Optional[str] = None  # ISO date format
    notes: Optional[str] = None


class PortfolioHoldingUpdate(BaseModel):
    """Update portfolio holding request."""
    shares: Optional[float] = Field(default=None, gt=0)
    entry_price: Optional[float] = Field(default=None, gt=0)
    entry_date: Optional[str] = None
    notes: Optional[str] = None


class PortfolioHoldingResponse(BaseModel):
    """Portfolio holding response."""
    id: int
    symbol: str
    shares: float
    entry_price: float
    entry_date: Optional[str]
    added_at: datetime
    updated_at: datetime
    notes: Optional[str]
    current_value: Optional[float] = None  # Calculated field: current price * shares
    cost_basis: Optional[float] = None  # Calculated field: entry_price * shares
    gain_loss: Optional[float] = None  # Calculated field: current_value - cost_basis
    gain_loss_pct: Optional[float] = None  # Calculated field: (gain_loss / cost_basis) * 100

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────────────────
# Stock Data Schemas
# ──────────────────────────────────────────────────────────────────────────

class StockFundamentalsResponse(BaseModel):
    """Stock fundamentals response."""
    symbol: str
    sector: Optional[str]
    industry: Optional[str]
    market_cap: Optional[int]
    pe_trailing: Optional[float]
    peg_ratio: Optional[float]
    price_to_fcf: Optional[float]
    ev_to_ebitda: Optional[float]
    roe: Optional[float]
    roic: Optional[float]
    gross_margin: Optional[float]
    operating_margin: Optional[float]
    net_margin: Optional[float]
    fcf_margin: Optional[float]
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    revenue_growth_yoy: Optional[float]
    earnings_growth_yoy: Optional[float]
    fcf_growth_yoy: Optional[float]
    analyst_rating: Optional[str]
    analyst_target_price: Optional[float]
    analysts_count: Optional[int]
    short_percent_float: Optional[float]
    fetched_at: Optional[datetime]

    class Config:
        from_attributes = True


class V2ScoreComponent(BaseModel):
    """Component scores within V2 score."""
    roic: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    fcf_margin: Optional[float] = None
    debt_safety: Optional[float] = None
    pe_ratio: Optional[float] = None
    price_vs_52w: Optional[float] = None
    revenue_growth: Optional[float] = None


class V2ScoreResponse(BaseModel):
    """V2 score response with full breakdown."""
    symbol: str
    v2_score: float
    quality_score: float
    value_score: float
    trajectory_score: float
    business_type: str
    components: Optional[Dict[str, Any]] = None
    current_price: Optional[float] = None
    date: Optional[str] = None


class StockDetailResponse(BaseModel):
    """Complete stock detail with all data."""
    fundamentals: StockFundamentalsResponse
    v2_score: V2ScoreResponse
    current_price: Optional[float]
    price_change_pct: Optional[float]
    fifty_two_week_high: Optional[float]
    fifty_two_week_low: Optional[float]


class ScreenerResult(BaseModel):
    """Screener result for a single stock."""
    symbol: str
    v2_score: float
    quality_score: float
    value_score: float
    trajectory_score: float
    current_price: Optional[float]
    sector: Optional[str]
    industry: Optional[str]
    pe_ratio: Optional[float]
    revenue_growth: Optional[float]


# ──────────────────────────────────────────────────────────────────────────
# Error Responses
# ──────────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
