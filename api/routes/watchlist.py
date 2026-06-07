"""
Watchlist routes: CRUD operations for user watchlist entries.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json

from api.schemas import WatchlistEntryCreate, WatchlistEntryUpdate, WatchlistEntryResponse
from api.routes.auth import get_current_user
from db.session import get_session
from db.models import WatchlistEntry


router = APIRouter()


@router.get(
    "",
    response_model=List[WatchlistEntryResponse],
    summary="Get user's watchlist"
)
async def get_watchlist(
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Get all stocks on current user's watchlist.

    Returns list of watchlist entries with prices and scores.
    """
    entries = session.query(WatchlistEntry).filter(
        WatchlistEntry.user_id == current_user.id
    ).all()

    return [WatchlistEntryResponse.model_validate(e) for e in entries]


@router.post(
    "",
    response_model=WatchlistEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add stock to watchlist"
)
async def add_to_watchlist(
    request: WatchlistEntryCreate,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Add a stock to user's watchlist.

    Each user can have at most one entry per symbol.
    """
    # Check if already on watchlist
    existing = session.query(WatchlistEntry).filter(
        WatchlistEntry.user_id == current_user.id,
        WatchlistEntry.symbol == request.symbol.upper(),
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{request.symbol} already on watchlist",
        )

    # Create entry
    entry = WatchlistEntry(
        user_id=current_user.id,
        symbol=request.symbol.upper(),
        entry_price=request.entry_price,
        notes=request.notes,
        alerts_enabled=request.alerts_enabled,
        alerts_config=request.alerts_config.dict() if request.alerts_config else None,
    )

    session.add(entry)
    session.commit()
    session.refresh(entry)

    return WatchlistEntryResponse.model_validate(entry)


@router.get(
    "/{symbol}",
    response_model=WatchlistEntryResponse,
    summary="Get watchlist entry details"
)
async def get_watchlist_entry(
    symbol: str,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get details for a specific watchlist entry."""
    entry = session.query(WatchlistEntry).filter(
        WatchlistEntry.user_id == current_user.id,
        WatchlistEntry.symbol == symbol.upper(),
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} not on watchlist",
        )

    return WatchlistEntryResponse.model_validate(entry)


@router.put(
    "/{symbol}",
    response_model=WatchlistEntryResponse,
    summary="Update watchlist entry"
)
async def update_watchlist_entry(
    symbol: str,
    request: WatchlistEntryUpdate,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Update a watchlist entry (entry price, notes, alerts).

    Only the fields provided in the request are updated.
    """
    entry = session.query(WatchlistEntry).filter(
        WatchlistEntry.user_id == current_user.id,
        WatchlistEntry.symbol == symbol.upper(),
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} not on watchlist",
        )

    # Update fields
    if request.entry_price is not None:
        entry.entry_price = request.entry_price
    if request.notes is not None:
        entry.notes = request.notes
    if request.alerts_enabled is not None:
        entry.alerts_enabled = request.alerts_enabled
    if request.alerts_config is not None:
        entry.alerts_config = request.alerts_config.dict()

    session.commit()
    session.refresh(entry)

    return WatchlistEntryResponse.model_validate(entry)


@router.delete(
    "/{symbol}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove stock from watchlist"
)
async def remove_from_watchlist(
    symbol: str,
    current_user = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Remove a stock from user's watchlist."""
    entry = session.query(WatchlistEntry).filter(
        WatchlistEntry.user_id == current_user.id,
        WatchlistEntry.symbol == symbol.upper(),
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} not on watchlist",
        )

    session.delete(entry)
    session.commit()

    return None
