"""User profile endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user

router = APIRouter()


class UserProfile(BaseModel):
    id: str
    email: str
    username: Optional[str]
    um_id: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: float


@router.get("/me", response_model=UserProfile)
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user
