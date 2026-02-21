"""
PostgreSQL mailbox repository.
"""

from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from api.database import connection
from api.database.contracts import MailboxStore
from api.database.queries import mailboxes
from api.errors.exceptions import DatabaseError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if result.get("mailbox_id") is not None:
        result["mailbox_id"] = str(result["mailbox_id"])
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
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to create mailbox.") from exc
        return _row_to_dict(row)

    def list(self) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(mailboxes.LIST_MAILBOXES)
                    rows = cur.fetchall()
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to list mailboxes.") from exc
        return [_row_to_dict(row) for row in rows]

    def get(self, mailbox_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(mailboxes.GET_MAILBOX, {"mailbox_id": mailbox_id})
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to get mailbox.") from exc
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
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to delete mailbox.") from exc


mailbox_store = PgMailboxStore()

