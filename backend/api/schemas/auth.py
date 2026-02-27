"""
Pydantic schemas for authentication API contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GoogleLoginRequest(BaseModel):
    """
    Request model for Google OIDC login.
    """

    id_token: str = Field(..., min_length=1)


class UserOut(BaseModel):
    """
    Response model for user data.
    """

    user_id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None


class AuthResponse(BaseModel):
    """
    Response model for authentication operations.
    """

    user: UserOut
    message: str
