"""
Portfolio routes: CRUD operations for user portfolio holdings.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from api.schemas import (
    PortfolioHoldingCreate,
    PortfolioHoldingUpdate,
    PortfolioHoldingResponse,
)
from api.routes.auth import get_current_user
from db.session import get_session
from db.models import PortfolioHolding, EodPrice


router = APIRouter()


def _enrich_holding(holding: PortfolioHolding, session: Session) -> dict:
    """
    Enrich a portfolio holding with current price data.

    Calculates cost_basis, current_value, gain/loss.
    """
    data = PortfolioHoldingResponse.model_validate(holding).dict()

    # Get latest price
    latest_price_record = session.query(EodPrice).filter(
        EodPrice.symbol == holding.symbol
    ).order_by(EodPrice.date.desc()).first()

    if latest_price_record:
        current_price = float(latest_price_record.close)
        data["current_value"] = round(current_price * float(holding.shares), 2)
        data["current_price"] = current_price
    else:
        data["current_price"] = None
        data["current_value"] = None

    # Calculate cost basis
    cost_basis = float(holding.entry_price) * float(holding.shares)
    data["cost_basis"] = round(cost_basis, 2)

    # Calculate gain/loss
    if data["current_value"] is not None:
        gain_loss = data["current_value"] - cost_basis
        data["gain_loss"] = round(gain_loss, 2)
        data["gain_loss_pct"] = round((gain_loss / cost_basis * 100) if cost_basis > 0 else 0, 2)
    else:
        data["gain_loss"] = None
        data["gain_loss_pct"] = None

    return data


@router.get(
    "",
    response_model=List[PortfolioHoldingResponse],
    summary="Get user's portfolio"
)
async def get_portfolio(
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Get all holdings in current user's portfolio.

    Includes current prices, cost basis, and gain/loss.
    """
    holdings = session.query(PortfolioHolding).filter(
        PortfolioHolding.user_id == current_user.id
    ).all()

    return [_enrich_holding(h, session) for h in holdings]


@router.get(
    "/summary",
    summary="Get portfolio summary"
)
async def get_portfolio_summary(
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Get portfolio summary with total value and gain/loss.
    """
    holdings = session.query(PortfolioHolding).filter(
        PortfolioHolding.user_id == current_user.id
    ).all()

    total_cost_basis = 0
    total_current_value = 0
    total_gain_loss = 0
    holdings_count = len(holdings)

    for holding in holdings:
        cost_basis = float(holding.entry_price) * float(holding.shares)
        total_cost_basis += cost_basis

        latest_price_record = session.query(EodPrice).filter(
            EodPrice.symbol == holding.symbol
        ).order_by(EodPrice.date.desc()).first()

        if latest_price_record:
            current_price = float(latest_price_record.close)
            current_value = current_price * float(holding.shares)
            total_current_value += current_value
            total_gain_loss += (current_value - cost_basis)

    total_gain_loss_pct = 0
    if total_cost_basis > 0:
        total_gain_loss_pct = (total_gain_loss / total_cost_basis) * 100

    return {
        "holdings_count": holdings_count,
        "total_cost_basis": round(total_cost_basis, 2),
        "total_current_value": round(total_current_value, 2) if total_current_value > 0 else None,
        "total_gain_loss": round(total_gain_loss, 2),
        "total_gain_loss_pct": round(total_gain_loss_pct, 2),
    }


@router.post(
    "",
    response_model=PortfolioHoldingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add holding to portfolio"
)
async def add_holding(
    request: PortfolioHoldingCreate,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Add a stock holding to user's portfolio.

    Each user can have at most one entry per symbol.
    """
    # Check if already in portfolio
    existing = session.query(PortfolioHolding).filter(
        PortfolioHolding.user_id == current_user.id,
        PortfolioHolding.symbol == request.symbol.upper(),
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{request.symbol} already in portfolio",
        )

    # Parse entry_date if provided
    entry_date = None
    if request.entry_date:
        try:
            entry_date = datetime.fromisoformat(request.entry_date).date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid entry_date format (use ISO format: YYYY-MM-DD)",
            )

    # Create holding
    holding = PortfolioHolding(
        user_id=current_user.id,
        symbol=request.symbol.upper(),
        shares=request.shares,
        entry_price=request.entry_price,
        entry_date=entry_date,
        notes=request.notes,
    )

    session.add(holding)
    session.commit()
    session.refresh(holding)

    return _enrich_holding(holding, session)


@router.get(
    "/{symbol}",
    response_model=PortfolioHoldingResponse,
    summary="Get holding details"
)
async def get_holding(
    symbol: str,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get details for a specific portfolio holding."""
    holding = session.query(PortfolioHolding).filter(
        PortfolioHolding.user_id == current_user.id,
        PortfolioHolding.symbol == symbol.upper(),
    ).first()

    if not holding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} not in portfolio",
        )

    return _enrich_holding(holding, session)


@router.put(
    "/{symbol}",
    response_model=PortfolioHoldingResponse,
    summary="Update holding"
)
async def update_holding(
    symbol: str,
    request: PortfolioHoldingUpdate,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Update a portfolio holding (shares, entry price, notes).

    Only the fields provided in the request are updated.
    """
    holding = session.query(PortfolioHolding).filter(
        PortfolioHolding.user_id == current_user.id,
        PortfolioHolding.symbol == symbol.upper(),
    ).first()

    if not holding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} not in portfolio",
        )

    # Update fields
    if request.shares is not None:
        holding.shares = request.shares
    if request.entry_price is not None:
        holding.entry_price = request.entry_price
    if request.notes is not None:
        holding.notes = request.notes
    if request.entry_date is not None:
        try:
            holding.entry_date = datetime.fromisoformat(request.entry_date).date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid entry_date format (use ISO format: YYYY-MM-DD)",
            )

    session.commit()
    session.refresh(holding)

    return _enrich_holding(holding, session)


@router.delete(
    "/{symbol}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove holding from portfolio"
)
async def remove_holding(
    symbol: str,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Remove a stock holding from user's portfolio."""
    holding = session.query(PortfolioHolding).filter(
        PortfolioHolding.user_id == current_user.id,
        PortfolioHolding.symbol == symbol.upper(),
    ).first()

    if not holding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} not in portfolio",
        )

    session.delete(holding)
    session.commit()

    return None
