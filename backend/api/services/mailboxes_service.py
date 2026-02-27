"""
Service layer for mailbox operations.
"""

from __future__ import annotations

from uuid import uuid4

from api.schemas.mailbox import MailboxCreate, MailboxOut
from api.database import mailbox_store
from api.services.services_helpers import ensure_mailbox_access


def create_mailbox(payload: MailboxCreate, user_id: str) -> MailboxOut:
    record = {
        "mailbox_id": str(uuid4()),
        "display_name": payload.display_name,
        "owner_user_id": user_id,
    }
    created = mailbox_store.create(record)
    return MailboxOut(**created)


def list_mailboxes(user_id: str) -> list[MailboxOut]:
    return [MailboxOut(**mailbox) for mailbox in mailbox_store.list_by_owner(user_id)]


def get_mailbox(mailbox_id: str, user_id: str) -> MailboxOut:
    record = ensure_mailbox_access(mailbox_id, user_id)
    return MailboxOut(**record)


def delete_mailbox(mailbox_id: str, user_id: str) -> dict[str, str]:
    ensure_mailbox_access(mailbox_id, user_id)
    # ON DELETE CASCADE removes associated accounts and tokens automatically.
    mailbox_store.delete(mailbox_id)
    return {"status": "deleted"}
