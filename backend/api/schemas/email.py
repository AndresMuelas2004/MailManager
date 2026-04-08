"""
Pydantic schemas for email API contracts.
"""

from __future__ import annotations

from datetime import datetime
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


class SpamItem(BaseModel):
    """Single item in a spam move/restore request."""

    account_id: str = Field(..., min_length=1)
    provider_message_id: str = Field(..., min_length=1)


class SpamRequest(BaseModel):
    """Request to batch move/restore emails to/from spam."""

    items: list[SpamItem] = Field(..., min_length=1)


class AccountSpamDetail(BaseModel):
    """Per-account result of a spam move/restore operation."""

    account_id: str
    moved: int


class SpamResponse(BaseModel):
    """Response for spam move/restore endpoints."""

    moved_count: int
    accounts: list[AccountSpamDetail]


class EmailContentOut(BaseModel):
    """Full email body content."""

    html_body: str | None = None
    text_body: str | None = None


class EmailMetadataOut(BaseModel):
    """Single email metadata item returned by the listing endpoint."""

    provider_message_id: str
    account_id: str
    thread_id: str | None = None
    from_email: str
    from_name: str | None = None
    subject: str | None = None
    received_at: datetime
    is_read: bool
    box: str
