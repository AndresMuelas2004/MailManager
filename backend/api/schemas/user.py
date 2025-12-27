"""
Pydantic schemas for user API contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """
    Request model for creating a user.
    """

    display_name: str | None = Field(default=None, max_length=120)


class UserOut(BaseModel):
    """
    Response model for user data.
    """

    user_id: str
    display_name: str | None = None
    created_at: str
