"""Authentication endpoints: register, login, token refresh."""

import datetime
import logging
import uuid
from typing import Optional

import bcrypt as _bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator

from hermes_state import UserDataDB
from api.deps import get_user_db, SECRET_KEY, ALGORITHM

router = APIRouter()
logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return _bcrypt.checkpw(password.encode(), password_hash.encode())

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_token(user_id: str, token_type: str, expires: datetime.timedelta) -> str:
    payload = {
        "sub": user_id,
        "type": token_type,
        "exp": datetime.datetime.utcnow() + expires,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _token_pair(user_id: str) -> dict:
    return {
        "access_token": _create_token(
            user_id, "access",
            datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        ),
        "refresh_token": _create_token(
            user_id, "refresh",
            datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        ),
        "token_type": "bearer",
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: UserDataDB = Depends(get_user_db)):
    if db.email_exists(req.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user_id = str(uuid.uuid4())

    # Auto-set first user as admin
    is_first_user = db.user_count() == 0
    is_admin = 1 if is_first_user else 0

    db.create_user(
        user_id=user_id,
        email=req.email,
        password_hash=_hash_password(req.password),
        username=req.username,
        is_admin=is_admin,
    )
    return _token_pair(user_id)


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: UserDataDB = Depends(get_user_db),
):
    """Login with email (username field) and password.

    Also creates/ensures user container for Docker isolation.
    """
    user = db.get_user_by_email(form_data.username.lower().strip())
    if not user or not _verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # Create user container for isolation (background, non-blocking)
    try:
        from api.user_containers import get_or_create_user_container, _USER_CONTAINERS
        # Start container creation in background thread to not block login response
        import threading

        def create_container_with_logging():
            try:
                container = get_or_create_user_container(user["id"])
                msg = f"[OK] User container created for {user['id']}: {container.container_id[:12] if container.container_id else 'unknown'}"
                print(msg)  # Force print to console for visibility
                logger.info(msg)
            except Exception as e:
                msg = f"[ERROR] Failed to create user container for {user['id']}: {e}"
                print(msg)  # Force print to console for visibility
                logger.error(msg, exc_info=True)

        threading.Thread(
            target=create_container_with_logging,
            daemon=True,
        ).start()
    except ImportError as e:
        msg = f"[ERROR] Cannot import user_containers module: {e}"
        print(msg)
        logger.error(msg)
    except Exception as e:
        # Log but don't fail login if container creation fails
        msg = f"[WARN] Failed to setup container creation: {e}"
        print(msg)
        logger.warning(msg, exc_info=True)

    return _token_pair(user["id"])


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: UserDataDB = Depends(get_user_db)):
    try:
        payload = jwt.decode(req.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id or payload.get("type") != "refresh":
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user = db.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return _token_pair(user_id)
