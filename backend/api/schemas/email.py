"""
Pydantic schemas for email API contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from core.email.email_client import EmailMessage


class EmailOut(BaseModel):
    """
    Response model derived from core.EmailMessage.
    """

    message_id: str
    subject: str
    sender: str
    recipients: List[str]
    body: str
    sent_at: datetime
    is_unread: bool
    provider: str
    thread_id: str | None = None
    raw_rfc822_b64url: str | None = None

    @classmethod
    def from_core(cls, message: EmailMessage) -> "EmailOut":
        return cls(
            message_id=message.message_id,
            subject=message.subject,
            sender=message.sender,
            recipients=message.recipients,
            body=message.body,
            sent_at=message.sent_at,
            is_unread=message.is_unread,
            provider=message.provider,
            thread_id=message.thread_id,
            raw_rfc822_b64url=message.raw_rfc822_b64url,
        )


class EmailSendRequest(BaseModel):
    """
    Request model for sending an email from a specific account.
    """

    account_id: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    recipients: List[str] = Field(default_factory=list)
