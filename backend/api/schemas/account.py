"""
Pydantic schemas for account API contracts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    """
    Request model for creating an account under a user.
    """

    provider: str = Field(..., min_length=1)
    display_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        validation_alias="label",
    )
    config: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseModel):
    """
    Request model for updating mutable account fields.
    """

    display_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        validation_alias="label",
    )
    config: dict[str, Any] | None = None


class AccountOut(BaseModel):
    """
    Response model for account data.
    """

    account_id: str
    user_id: str
    provider: str
    display_label: str
    config: dict[str, Any]


class AccountConnectResponse(BaseModel):
    """
    Response model for account connection checks.
    """

    connected: bool
    provider: str
    account_id: str
    account_label: str
    message: str
