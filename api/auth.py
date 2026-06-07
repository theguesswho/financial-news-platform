"""
Authentication service with JWT and password hashing.

Provides:
- Password hashing with bcrypt
- JWT token generation and validation
- User verification and claims extraction
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os

from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from db.models import User


# ──────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────

# Get from environment or use defaults
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours

# Password hashing context (use argon2 which is more secure and doesn't have limitations)
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


# ──────────────────────────────────────────────────────────────────────────
# Password Hashing
# ──────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain-text password against its hash."""
    return pwd_context.verify(plain_password, password_hash)


# ──────────────────────────────────────────────────────────────────────────
# JWT Token Management
# ──────────────────────────────────────────────────────────────────────────

def create_access_token(
    user_id: int,
    email: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: User ID to encode in token
        email: User email to encode in token
        expires_delta: Optional custom expiration time. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.utcnow() + expires_delta
    payload = {
        "sub": str(user_id),  # Subject claim (typically user ID)
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    encoded_jwt = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        if user_id is None or email is None:
            return None
        return payload
    except JWTError:
        return None


def extract_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    """
    Extract JWT token from Authorization header.

    Args:
        auth_header: Authorization header value (e.g., "Bearer <token>")

    Returns:
        Token string if valid format, None otherwise
    """
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


# ──────────────────────────────────────────────────────────────────────────
# User Authentication
# ──────────────────────────────────────────────────────────────────────────

def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """Get user by email address."""
    return session.query(User).filter(User.email == email).first()


def create_user(
    session: Session,
    email: str,
    password: str,
    name: str
) -> Optional[User]:
    """
    Create a new user account.

    Returns:
        Created User object if successful, None if email already exists
    """
    # Check if email already exists
    if get_user_by_email(session, email):
        return None

    # Create new user
    password_hash = hash_password(password)
    user = User(
        email=email,
        password_hash=password_hash,
        name=name,
        is_active=True,
    )

    try:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    except Exception:
        session.rollback()
        return None


def authenticate_user(
    session: Session,
    email: str,
    password: str
) -> Optional[User]:
    """
    Authenticate user with email and password.

    Returns:
        User object if credentials are valid, None otherwise
    """
    user = get_user_by_email(session, email)
    if not user:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    # Update last login
    user.last_login = datetime.utcnow()
    session.commit()

    return user


def get_user_from_token(session: Session, token: str) -> Optional[User]:
    """
    Get user from a valid JWT token.

    Returns:
        User object if token is valid and user exists, None otherwise
    """
    payload = verify_token(token)
    if not payload:
        return None

    user_id = int(payload.get("sub", 0))
    if user_id == 0:
        return None

    user = session.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    return user
