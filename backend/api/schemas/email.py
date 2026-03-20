"""
Pydantic schemas for email API contracts.
"""

from __future__ import annotations

from typing import Literal

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


class TrashItem(BaseModel):
    provider_message_id: str = Field(..., min_length=1)
    account_id: str = Field(..., min_length=1)


class TrashActionRequest(BaseModel):
    action: Literal["delete", "restore"]
    items: list[TrashItem] = Field(..., min_length=1)


class TrashActionResult(BaseModel):
    affected: int


class MoveToTrashRequest(BaseModel):
    items: list[TrashItem] = Field(..., min_length=1)


class MoveToTrashResult(BaseModel):
    affected: int


class ReadStatusItem(BaseModel):
    """Single item in a read-status update request."""

    account_id: str = Field(..., min_length=1)
    provider_message_id: str = Field(..., min_length=1)


class ReadStatusRequest(BaseModel):
    """Request to batch-update read/unread status."""

    is_read: bool
    items: list[ReadStatusItem] = Field(..., min_length=1)


class AccountReadStatusDetail(BaseModel):
    """Per-account result of a read-status update."""

    account_id: str
    updated: int


class ReadStatusResponse(BaseModel):
    """Response for the read-status endpoint."""

    updated_count: int
    accounts: list[AccountReadStatusDetail]
