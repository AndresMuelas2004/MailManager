"""
PostgreSQL mailbox repository.
"""

from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from database import connection
from database.contracts import MailboxStore
from database.queries import mailboxes
from database.errors import DatabaseError, QueryError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if result.get("mailbox_id") is not None:
        result["mailbox_id"] = str(result["mailbox_id"])
    result["owner_user_id"] = str(result["owner_user_id"])
    if result.get("created_at") is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result


class PgMailboxStore(MailboxStore):
    """
    PostgreSQL-backed mailbox persistence.
    """

    def create(self, mailbox: dict[str, Any]) -> dict[str, Any]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(mailboxes.INSERT_MAILBOX, mailbox)
                    row = cur.fetchone()
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to create mailbox.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected mailbox create error ({type(exc).__name__}): {exc}"
            ) from exc
        return _row_to_dict(row)

    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        mailboxes.LIST_MAILBOXES_BY_OWNER,
                        {"owner_user_id": owner_user_id},
                    )
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list mailboxes by owner.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected mailbox list error ({type(exc).__name__}): {exc}"
            ) from exc
        return [_row_to_dict(row) for row in rows]

    def get(self, mailbox_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(mailboxes.GET_MAILBOX, {"mailbox_id": mailbox_id})
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get mailbox.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected mailbox get error ({type(exc).__name__}): {exc}"
            ) from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def delete(self, mailbox_id: str) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(mailboxes.DELETE_MAILBOX, {"mailbox_id": mailbox_id})
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete mailbox.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected mailbox delete error ({type(exc).__name__}): {exc}"
            ) from exc


mailbox_store = PgMailboxStore()
