"""
Stocks routes: get stock data, V2 scores, and run screeners.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from api.schemas import StockFundamentalsResponse, V2ScoreResponse, StockDetailResponse, ScreenerResult
from db.session import get_session
from db.models import Fundamentals, DailyScore, EodPrice
from pipeline.score import compute_v2_score, compute_v2_score_with_breakdown


router = APIRouter()


@router.get(
    "/screener",
    response_model=List[ScreenerResult],
    summary="Screen stocks by V2 score"
)
async def screener(
    sector: Optional[str] = Query(None, description="Filter by sector (e.g., 'Technology')"),
    min_score: Optional[float] = Query(None, ge=0, le=1, description="Minimum V2 score"),
    max_pe: Optional[float] = Query(None, gt=0, description="Maximum P/E ratio"),
    min_revenue_growth: Optional[float] = Query(None, ge=0, description="Minimum revenue growth YoY"),
    limit: int = Query(50, ge=1, le=500, description="Number of results to return"),
    session: Session = Depends(get_session),
):
    """
    Screen stocks using V2 mismatch score and fundamental filters.

    Returns top stocks sorted by V2 score descending.
    """
    # Query all stocks with fundamentals
    query = session.query(Fundamentals)

    # Apply sector filter
    if sector:
        query = query.filter(Fundamentals.sector == sector)

    # Get all results
    all_funds = query.all()

    if not all_funds:
        return []

    # Calculate V2 scores
    results = []
    for fund in all_funds:
        v2_score = compute_v2_score(fund, session)

        # Apply score filter
        if min_score is not None and v2_score < min_score:
            continue

        # Apply P/E filter
        if max_pe is not None and fund.pe_trailing and float(fund.pe_trailing) > max_pe:
            continue

        # Apply revenue growth filter
        if min_revenue_growth is not None and fund.revenue_growth_yoy:
            if float(fund.revenue_growth_yoy) < min_revenue_growth:
                continue

        # Get latest price
        latest_price = session.query(EodPrice).filter(
            EodPrice.symbol == fund.symbol
        ).order_by(EodPrice.date.desc()).first()

        breakdown = compute_v2_score_with_breakdown(fund, session)

        results.append(ScreenerResult(
            symbol=fund.symbol,
            v2_score=v2_score,
            quality_score=breakdown.get("quality_score", 0),
            value_score=breakdown.get("value_score", 0),
            trajectory_score=breakdown.get("trajectory_score", 0),
            current_price=float(latest_price.close) if latest_price else None,
            sector=fund.sector,
            industry=fund.industry,
            pe_ratio=float(fund.pe_trailing) if fund.pe_trailing else None,
            revenue_growth=float(fund.revenue_growth_yoy) if fund.revenue_growth_yoy else None,
        ))

    # Sort by V2 score
    results = sorted(results, key=lambda x: x.v2_score, reverse=True)

    return results[:limit]


@router.get(
    "/{symbol}/fundamentals",
    response_model=StockFundamentalsResponse,
    summary="Get stock fundamentals"
)
async def get_fundamentals(
    symbol: str,
    session: Session = Depends(get_session),
):
    """Get fundamental data for a stock."""
    fund = session.query(Fundamentals).filter(
        Fundamentals.symbol == symbol.upper()
    ).first()

    if not fund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No fundamentals found for {symbol}",
        )

    return StockFundamentalsResponse.model_validate(fund)


@router.get(
    "/{symbol}/v2-score",
    response_model=V2ScoreResponse,
    summary="Get V2 mismatch score"
)
async def get_v2_score(
    symbol: str,
    session: Session = Depends(get_session),
):
    """
    Get V2 mismatch score with component breakdown.

    Returns quality, value, and trajectory scores with detailed calculations.
    """
    fund = session.query(Fundamentals).filter(
        Fundamentals.symbol == symbol.upper()
    ).first()

    if not fund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No fundamentals found for {symbol}",
        )

    # Calculate V2 score
    v2_score = compute_v2_score(fund, session)
    breakdown = compute_v2_score_with_breakdown(fund, session)

    # Get latest price
    latest_price = session.query(EodPrice).filter(
        EodPrice.symbol == symbol.upper()
    ).order_by(EodPrice.date.desc()).first()

    # Get today's daily score if available
    from datetime import date
    daily_score = session.query(DailyScore).filter(
        DailyScore.symbol == symbol.upper(),
        DailyScore.date == date.today()
    ).first()

    return V2ScoreResponse(
        symbol=symbol.upper(),
        v2_score=round(v2_score, 4),
        quality_score=round(breakdown.get("quality_score", 0), 4),
        value_score=round(breakdown.get("value_score", 0), 4),
        trajectory_score=round(breakdown.get("trajectory_score", 0), 4),
        business_type=breakdown.get("business_type", "unknown"),
        components=breakdown.get("breakdown"),
        current_price=float(latest_price.close) if latest_price else None,
        date=daily_score.date.isoformat() if daily_score else None,
    )


@router.get(
    "/{symbol}",
    response_model=StockDetailResponse,
    summary="Get complete stock details"
)
async def get_stock_detail(
    symbol: str,
    session: Session = Depends(get_session),
):
    """
    Get complete stock data: fundamentals, V2 score, current price, trends.

    This is the main endpoint for stock detail pages.
    """
    fund = session.query(Fundamentals).filter(
        Fundamentals.symbol == symbol.upper()
    ).first()

    if not fund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for {symbol}",
        )

    # Get prices
    latest_price = session.query(EodPrice).filter(
        EodPrice.symbol == symbol.upper()
    ).order_by(EodPrice.date.desc()).first()

    prior_price = session.query(EodPrice).filter(
        EodPrice.symbol == symbol.upper()
    ).order_by(EodPrice.date.desc()).offset(1).first()

    price_change_pct = None
    if latest_price and prior_price:
        change = (float(latest_price.close) - float(prior_price.close)) / float(prior_price.close)
        price_change_pct = round(change * 100, 2)

    # Get V2 score
    v2_score = compute_v2_score(fund, session)
    breakdown = compute_v2_score_with_breakdown(fund, session)

    return StockDetailResponse(
        fundamentals=StockFundamentalsResponse.model_validate(fund),
        v2_score=V2ScoreResponse(
            symbol=symbol.upper(),
            v2_score=round(v2_score, 4),
            quality_score=round(breakdown.get("quality_score", 0), 4),
            value_score=round(breakdown.get("value_score", 0), 4),
            trajectory_score=round(breakdown.get("trajectory_score", 0), 4),
            business_type=breakdown.get("business_type", "unknown"),
            components=breakdown.get("breakdown"),
            current_price=float(latest_price.close) if latest_price else None,
        ),
        current_price=float(latest_price.close) if latest_price else None,
        price_change_pct=price_change_pct,
        fifty_two_week_high=float(fund.fifty_two_week_high) if fund.fifty_two_week_high else None,
        fifty_two_week_low=float(fund.fifty_two_week_low) if fund.fifty_two_week_low else None,
    )


@router.get(
    "/search/{query}",
    summary="Search stocks by symbol or name"
)
async def search_stocks(
    query: str,
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """
    Search for stocks by symbol (e.g., 'AAPL') or company name substring.

    Returns matching stocks with key metrics.
    """
    # Search by symbol (starts with) or industry/sector keywords
    search_term = query.upper()

    results = session.query(Fundamentals).filter(
        (Fundamentals.symbol.ilike(f"%{search_term}%")) |
        (Fundamentals.industry.ilike(f"%{search_term}%")) |
        (Fundamentals.sector.ilike(f"%{search_term}%"))
    ).limit(limit).all()

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stocks found matching '{query}'",
        )

    return [
        {
            "symbol": f.symbol,
            "sector": f.sector,
            "industry": f.industry,
            "market_cap": int(f.market_cap) if f.market_cap else None,
            "pe_trailing": float(f.pe_trailing) if f.pe_trailing else None,
        }
        for f in results
    ]
