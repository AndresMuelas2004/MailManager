"""
Email router for metadata sync and sending.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.routers.routers_helpers import require_session
from api.schemas.email import (
    EmailSendRequest,
    ReadStatusRequest,
    ReadStatusResponse,
    SpamRequest,
    SpamResponse,
    SyncResultOut,
)
from api.services import emails_service


router = APIRouter(prefix="/mailboxes/{mailbox_id}/emails", tags=["emails"])


@router.post("/sync-metadata", response_model=SyncResultOut)
def sync_email_metadata(
    mailbox_id: str,
    user_id: str = Depends(require_session),
) -> SyncResultOut:
    """
    Fetch and persist email metadata for all accounts under a mailbox.
    """
    return emails_service.sync_email_metadata(mailbox_id, user_id)


@router.post("/send")
def send_email(
    mailbox_id: str,
    payload: EmailSendRequest,
    user_id: str = Depends(require_session),
) -> dict[str, str]:
    """
    Send an email using a specific account under the mailbox.
    """
    return emails_service.send_email(mailbox_id, payload, user_id)


@router.patch("/read-status", response_model=ReadStatusResponse)
def update_read_status(
    mailbox_id: str,
    payload: ReadStatusRequest,
    user_id: str = Depends(require_session),
) -> ReadStatusResponse:
    """
    Mark emails as read or unread across accounts in a mailbox.
    """
    return emails_service.update_read_status(mailbox_id, payload, user_id)


@router.post("/spam", response_model=SpamResponse)
def move_to_spam(
    mailbox_id: str,
    payload: SpamRequest,
    user_id: str = Depends(require_session),
) -> SpamResponse:
    """
    Move emails to spam across accounts in a mailbox.
    """
    return emails_service.move_to_spam(mailbox_id, payload, user_id)


@router.post("/restore-from-spam", response_model=SpamResponse)
def restore_from_spam(
    mailbox_id: str,
    payload: SpamRequest,
    user_id: str = Depends(require_session),
) -> SpamResponse:
    """
    Restore emails from spam across accounts in a mailbox.
    """
    return emails_service.restore_from_spam(mailbox_id, payload, user_id)
