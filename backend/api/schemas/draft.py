"""
Pydantic schemas for draft API contracts.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DraftCreate(BaseModel):
    """
    Request model for creating a draft. All fields are optional —
    empty drafts are allowed (matches Gmail/Outlook native behavior).
    """

    to_recipients: list[str] = Field(default_factory=list)
    cc_recipients: list[str] = Field(default_factory=list)
    bcc_recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    body_html: str = ""


class DraftUpdate(BaseModel):
    """
    Request model for updating an existing draft. Semantically a full
    replacement: the provider call overwrites the draft with exactly
    the fields in this payload. All fields are optional with defaults,
    matching DraftCreate — empty fields are valid.
    """

    to_recipients: list[str] = Field(default_factory=list)
    cc_recipients: list[str] = Field(default_factory=list)
    bcc_recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    body_html: str = ""


class DraftOut(BaseModel):
    """
    Response model for a persisted draft.
    """

    provider_draft_id: str
    account_id: str
    to_recipients: list[str]
    cc_recipients: list[str]
    bcc_recipients: list[str]
    subject: str
    body_html: str
    created_at: datetime
    updated_at: datetime


class DraftsAccountSyncDetail(BaseModel):
    """Per-account detail inside a drafts sync response."""

    account_id: str
    provider: str
    drafts_synced: int


class DraftsSyncResultOut(BaseModel):
    """Response model for POST /mailboxes/{mailbox_id}/drafts/sync."""

    total_synced: int
    accounts: list[DraftsAccountSyncDetail]
