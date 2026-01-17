"""
Mailbox router for minimal mailbox management.

Authentication is out of scope for now, so mailbox_id is explicit in paths.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.mailbox import MailboxCreate, MailboxOut
from api.services import mailboxes_service


router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


@router.post("", response_model=MailboxOut)
def create_mailbox(payload: MailboxCreate) -> MailboxOut:
    """
    Create a mailbox record for grouping accounts and email operations.
    """
    return mailboxes_service.create_mailbox(payload)


@router.get("", response_model=list[MailboxOut])
def list_mailboxes() -> list[MailboxOut]:
    """
    List all mailboxes stored in the system.
    """
    return mailboxes_service.list_mailboxes()


@router.get("/{mailbox_id}", response_model=MailboxOut)
def get_mailbox(mailbox_id: str) -> MailboxOut:
    """
    Retrieve a single mailbox by identifier.
    """
    return mailboxes_service.get_mailbox(mailbox_id)


@router.delete("/{mailbox_id}")
def delete_mailbox(mailbox_id: str) -> dict[str, str]:
    """
    Delete a mailbox and all accounts owned by the mailbox.
    """
    return mailboxes_service.delete_mailbox(mailbox_id)
