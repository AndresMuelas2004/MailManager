"""
Pydantic schemas for email API contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmailSendRequest(BaseModel):
    """
    Request model for sending an email from a specific account.
    """

    account_id: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    recipients: list[str] = Field(..., min_length=1)


class AccountSyncDetail(BaseModel):
    """Per-account sync result."""

    account_id: str
    provider: str
    emails_synced: int
    sync_cursor: str | None = None


class SyncResultOut(BaseModel):
    """Response for the sync-metadata endpoint."""

    total_synced: int
    accounts: list[AccountSyncDetail]
