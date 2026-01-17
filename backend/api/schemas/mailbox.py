"""
Pydantic schemas for mailbox API contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MailboxCreate(BaseModel):
    """
    Request model for creating a mailbox.
    """

    display_name: str = Field(..., max_length=120)


class MailboxOut(BaseModel):
    """
    Response model for mailbox data.
    """

    mailbox_id: str
    display_name: str | None = None
    created_at: str
