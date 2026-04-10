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
