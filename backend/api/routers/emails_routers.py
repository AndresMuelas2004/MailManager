"""
Email router for metadata sync and sending.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from api.routers.routers_helpers import require_session
from api.schemas.email import (
    EmailContentOut,
    EmailMetadataOut,
    EmailSendRequest,
    MoveToTrashRequest,
    MoveToTrashResult,
    ReadStatusRequest,
    ReadStatusResponse,
    SpamRequest,
    SpamResponse,
    SyncResultOut,
    TrashActionRequest,
    TrashActionResult,
)
from api.services import emails_service


router = APIRouter(prefix="/mailboxes/{mailbox_id}/emails", tags=["emails"])


@router.get("", response_model=list[EmailMetadataOut])
def list_emails(
    mailbox_id: str,
    box: Literal["ALL_MAIL", "SENT", "SPAM", "TRASH"] = Query(...),
    account_id: str | None = Query(default=None),
    user_id: str = Depends(require_session),
) -> list[EmailMetadataOut]:
    """
    List email metadata for a mailbox, filtered by box.
    Optionally filter to a single account.
    """
    return emails_service.list_emails(mailbox_id, box, user_id, account_id)


@router.post("/sync-metadata", response_model=SyncResultOut)
def sync_email_metadata(
    mailbox_id: str,
    account_id: str | None = Query(default=None),
    user_id: str = Depends(require_session),
) -> SyncResultOut:
    """
    Fetch and persist email metadata for a mailbox.
    Optionally sync only a single account.
    """
    return emails_service.sync_email_metadata(mailbox_id, user_id, account_id)


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


@router.post("/trash", response_model=TrashActionResult)
def manage_trash(
    mailbox_id: str,
    payload: TrashActionRequest,
    user_id: str = Depends(require_session),
) -> TrashActionResult:
    """
    Delete permanently or restore emails from trash.
    """
    return emails_service.manage_trash(mailbox_id, payload, user_id)


@router.post("/move-to-trash", response_model=MoveToTrashResult)
def move_to_trash(
    mailbox_id: str,
    payload: MoveToTrashRequest,
    user_id: str = Depends(require_session),
) -> MoveToTrashResult:
    """
    Move emails to trash.
    """
    return emails_service.move_to_trash(mailbox_id, payload, user_id)


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


@router.get(
    "/{provider_message_id}/content",
    response_model=EmailContentOut,
)
def get_email_full_content(
    mailbox_id: str,
    provider_message_id: str,
    account_id: str = Query(..., min_length=1),
    user_id: str = Depends(require_session),
) -> EmailContentOut:
    return emails_service.get_email_full_content(
        mailbox_id, provider_message_id, account_id, user_id,
    )
