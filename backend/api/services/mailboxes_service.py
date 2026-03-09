"""
Service layer for mailbox operations.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from api.errors.exceptions import ApiError
from api.schemas.mailbox import MailboxCreate, MailboxOut
from database import DatabaseError, mailbox_store
from api.services.services_helpers import ensure_mailbox_access, translate_database_error

logger = logging.getLogger(__name__)


def create_mailbox(payload: MailboxCreate, user_id: str) -> MailboxOut:
    record = {
        "mailbox_id": str(uuid4()),
        "display_name": payload.display_name,
        "owner_user_id": user_id,
    }
    try:
        created = mailbox_store.create(record)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected mailbox creation error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to create mailbox.") from exc
    return MailboxOut(**created)


def list_mailboxes(user_id: str) -> list[MailboxOut]:
    try:
        mailboxes = mailbox_store.list_by_owner(user_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected mailbox listing error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to list mailboxes.") from exc
    return [MailboxOut(**mailbox) for mailbox in mailboxes]


def get_mailbox(mailbox_id: str, user_id: str) -> MailboxOut:
    record = ensure_mailbox_access(mailbox_id, user_id)
    return MailboxOut(**record)


def delete_mailbox(mailbox_id: str, user_id: str) -> dict[str, str]:
    ensure_mailbox_access(mailbox_id, user_id)
    # ON DELETE CASCADE removes associated accounts and tokens automatically.
    try:
        mailbox_store.delete(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected mailbox deletion error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to delete mailbox.") from exc
    return {"status": "deleted"}
