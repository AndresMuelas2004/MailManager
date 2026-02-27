"""
Mailbox router for minimal mailbox management.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.routers.routers_helpers import require_session
from api.schemas.mailbox import MailboxCreate, MailboxOut
from api.services import mailboxes_service


router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


@router.post("", response_model=MailboxOut)
def create_mailbox(
    payload: MailboxCreate,
    user_id: str = Depends(require_session),
) -> MailboxOut:
    """
    Create a mailbox record for grouping accounts and email operations.
    """
    return mailboxes_service.create_mailbox(payload, user_id)


@router.get("", response_model=list[MailboxOut])
def list_mailboxes(user_id: str = Depends(require_session)) -> list[MailboxOut]:
    """
    List all mailboxes owned by the authenticated user.
    """
    return mailboxes_service.list_mailboxes(user_id)


@router.get("/{mailbox_id}", response_model=MailboxOut)
def get_mailbox(
    mailbox_id: str,
    user_id: str = Depends(require_session),
) -> MailboxOut:
    """
    Retrieve a single mailbox by identifier.
    """
    return mailboxes_service.get_mailbox(mailbox_id, user_id)


@router.delete("/{mailbox_id}")
def delete_mailbox(
    mailbox_id: str,
    user_id: str = Depends(require_session),
) -> dict[str, str]:
    """
    Delete a mailbox and all accounts owned by the mailbox.
    """
    return mailboxes_service.delete_mailbox(mailbox_id, user_id)
