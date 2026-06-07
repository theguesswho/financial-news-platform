"""
Authentication routes: register, login, get current user.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from api.schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from api.auth import (
    create_user,
    authenticate_user,
    create_access_token,
    get_user_from_token,
    extract_token_from_header,
)
from db.session import get_session


router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────────

def get_current_user(
    authorization: str = Header(None),
    session: Session = Depends(get_session)
):
    """Dependency to get current authenticated user from JWT token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = extract_token_from_header(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_from_token(session, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user"
)
async def register(
    request: UserRegister,
    session: Session = Depends(get_session)
):
    """
    Register a new user account.

    Returns JWT access token for immediate use.
    """
    # Create user
    user = create_user(session, request.email, request.password, request.name)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Generate token
    access_token = create_access_token(user.id, user.email)

    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login user"
)
async def login(
    request: UserLogin,
    session: Session = Depends(get_session)
):
    """
    Login with email and password.

    Returns JWT access token for authenticated requests.
    """
    # Authenticate user
    user = authenticate_user(session, request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate token
    access_token = create_access_token(user.id, user.email)

    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user"
)
async def get_me(
    current_user = Depends(get_current_user)
):
    """
    Get currently authenticated user's profile.

    Requires valid JWT token in Authorization header.
    """
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    summary="Logout user"
)
async def logout(
    current_user = Depends(get_current_user)
):
    """
    Logout user (client-side token invalidation).

    Server-side: tokens are stateless and valid until expiration.
    Clients should delete the token from storage.
    """
    return {
        "message": "Logged out successfully",
        "user_id": current_user.id,
    }
