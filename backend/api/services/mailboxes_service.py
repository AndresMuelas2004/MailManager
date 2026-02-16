"""
Service layer for mailbox operations.
"""

from __future__ import annotations

from uuid import uuid4

from api.errors.exceptions import MailboxNotFound
from api.schemas.mailbox import MailboxCreate, MailboxOut
from api.database import mailbox_store


def create_mailbox(payload: MailboxCreate) -> MailboxOut:
    record = {
        "mailbox_id": str(uuid4()),
        "display_name": payload.display_name,
    }
    created = mailbox_store.create(record)
    return MailboxOut(**created)


def list_mailboxes() -> list[MailboxOut]:
    return [MailboxOut(**mailbox) for mailbox in mailbox_store.list()]


def get_mailbox(mailbox_id: str) -> MailboxOut:
    record = mailbox_store.get(mailbox_id)
    if record is None:
        raise MailboxNotFound(f"Mailbox '{mailbox_id}' not found.")
    return MailboxOut(**record)


def delete_mailbox(mailbox_id: str) -> dict[str, str]:
    record = mailbox_store.get(mailbox_id)
    if record is None:
        raise MailboxNotFound(f"Mailbox '{mailbox_id}' not found.")

    # ON DELETE CASCADE removes associated accounts and tokens automatically.
    mailbox_store.delete(mailbox_id)
    return {"status": "deleted"}
