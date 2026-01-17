"""
Email router for inbox fetching and sending.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.email import EmailOut, EmailSendRequest
from api.services import emails_service


router = APIRouter(prefix="/mailboxes/{mailbox_id}/emails", tags=["emails"])


@router.get("/unread", response_model=list[EmailOut])
def list_unread_emails(mailbox_id: str) -> list[EmailOut]:
    """
    Fetch unread emails for all accounts under a mailbox.
    """
    return emails_service.get_unread(mailbox_id)


@router.post("/send")
def send_email(mailbox_id: str, payload: EmailSendRequest) -> dict[str, str]:
    """
    Send an email using a specific account under the mailbox.
    """
    return emails_service.send_email(mailbox_id, payload)
