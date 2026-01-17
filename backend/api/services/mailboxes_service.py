"""
Service layer for mailbox operations.
"""

from __future__ import annotations

from uuid import uuid4

from api.errors.exceptions import MailboxNotFound
from api.schemas.mailbox import MailboxCreate, MailboxOut
from api.storage.json_store import account_store, mailbox_store, now_iso
from api.storage.token_store import delete_account_tokens_for_records


def create_mailbox(payload: MailboxCreate) -> MailboxOut:
    record = {
        "mailbox_id": str(uuid4()),
        "display_name": payload.display_name,
        "created_at": now_iso(),
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

    accounts = account_store.list_by_mailbox(mailbox_id)
    # Best-effort token cleanup for all accounts under this mailbox.
    delete_account_tokens_for_records(accounts)
    for account in accounts:
        account_id = str(account.get("account_id", ""))
        if account_id:
            account_store.delete(mailbox_id, account_id)

    mailbox_store.delete(mailbox_id)
    return {"status": "deleted"}
