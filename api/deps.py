"""Shared FastAPI dependencies: DB access, JWT validation, current-user injection."""

import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from hermes_state import UserDataDB

# ── JWT settings ──────────────────────────────────────────────────────────────

# Set HERMES_SECRET_KEY in your environment before production deployment.
SECRET_KEY: str = os.getenv("HERMES_SECRET_KEY", "change-me-in-production-please")
ALGORITHM = "HS256"

# ── DB singleton ──────────────────────────────────────────────────────────────

_db: Optional[UserDataDB] = None


def get_user_db() -> UserDataDB:
    global _db
    if _db is None:
        _db = UserDataDB()
    return _db


# ── Auth ──────────────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: UserDataDB = Depends(get_user_db),
) -> dict:
    """Validate Bearer JWT and return the user dict (without password_hash)."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type", "access")
        if not user_id or token_type != "access":
            raise credentials_exc
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exc

    user = db.get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise credentials_exc
    return user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires the user to be an admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )
    return current_user
