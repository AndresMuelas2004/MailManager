"""
PostgreSQL email metadata repository.
"""

from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from database import connection
from database.contracts import EmailMetadataStore
from database.queries import email_metadata as queries
from database.errors import DatabaseError, QueryError


class PgEmailMetadataStore(EmailMetadataStore):
    """
    PostgreSQL-backed email metadata persistence.
    """

    def _execute_batch_values(self, query: str, rows: list[tuple], error_msg: str) -> int:
        """Shared helper for execute_values batch operations."""
        if not rows:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(cur, query, rows, page_size=500)
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError(error_msg) from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected {error_msg.lower()} ({type(exc).__name__}): {exc}"
            ) from exc

    def upsert_batch(self, account_id: str, rows: list[tuple]) -> int:
        if not rows:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        queries.UPSERT_EMAIL_METADATA_BATCH,
                        rows,
                        page_size=500,
                    )
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to upsert email metadata batch.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata upsert error ({type(exc).__name__}): {exc}"
            ) from exc

    def delete_batch_by_message_ids(self, account_id: str, message_ids: list[str]) -> int:
        if not message_ids:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        queries.DELETE_BATCH_BY_MESSAGE_IDS,
                        {"account_id": account_id, "message_ids": message_ids},
                    )
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete email metadata batch by message IDs.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata delete batch error ({type(exc).__name__}): {exc}"
            ) from exc

    def update_labels_batch(self, account_id: str, rows: list[tuple]) -> int:
        if not rows:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        queries.UPDATE_LABELS_BATCH,
                        rows,
                        page_size=500,
                    )
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to update email metadata labels batch.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata label update error ({type(exc).__name__}): {exc}"
            ) from exc

    def update_read_status_batch(self, account_id: str, rows: list[tuple]) -> int:
        if not rows:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        queries.UPDATE_READ_STATUS_BATCH,
                        rows,
                        page_size=500,
                    )
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to update email read status batch.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email read status update error ({type(exc).__name__}): {exc}"
            ) from exc

    def list_provider_message_ids(self, account_id: str) -> list[str]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(queries.LIST_PROVIDER_MESSAGE_IDS_BY_ACCOUNT, {"account_id": account_id})
                    return [row[0] for row in cur.fetchall()]
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list provider message IDs.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected list provider message IDs error ({type(exc).__name__}): {exc}"
            ) from exc

    def exists(self, account_id: str, provider_message_id: str) -> bool:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        queries.EXISTS_BY_MESSAGE_ID,
                        {
                            "account_id": account_id,
                            "provider_message_id": provider_message_id,
                        },
                    )
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return False
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to check email metadata existence.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata exists check error ({type(exc).__name__}): {exc}"
            ) from exc
        return row is not None


    def get_trash_emails_by_ids(self, account_id: str, message_ids: list[str]) -> list[dict[str, Any]]:
        if not message_ids:
            return []
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.GET_TRASH_EMAILS_BY_IDS,
                        {"account_id": account_id, "message_ids": message_ids},
                    )
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get trash emails by IDs.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected get trash emails error ({type(exc).__name__}): {exc}"
            ) from exc
        return [dict(row) for row in rows]

    def mark_as_deleted_batch(self, account_id: str, message_ids: list[str]) -> int:
        if not message_ids:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        queries.MARK_AS_DELETED_BATCH,
                        {"account_id": account_id, "message_ids": message_ids},
                    )
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to mark emails as deleted.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected mark as deleted error ({type(exc).__name__}): {exc}"
            ) from exc

    def restore_from_trash_batch(self, account_id: str, rows: list[tuple]) -> int:
        return self._execute_batch_values(
            queries.RESTORE_FROM_TRASH_BATCH, rows, "Failed to restore emails from trash.",
        )

    def restore_from_trash_discovered_batch(self, account_id: str, rows: list[tuple]) -> int:
        return self._execute_batch_values(
            queries.RESTORE_FROM_TRASH_DISCOVERED_BATCH, rows,
            "Failed to restore emails with discovered box.",
        )

    def move_to_trash_batch(self, account_id: str, rows: list[tuple]) -> int:
        return self._execute_batch_values(
            queries.MOVE_TO_TRASH_BATCH, rows, "Failed to move emails to trash.",
        )

    def update_spam_status_batch(self, account_id: str, rows: list[tuple]) -> int:
        if not rows:
            return 0
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        queries.UPDATE_SPAM_STATUS_BATCH,
                        rows,
                        page_size=500,
                    )
                    return cur.rowcount
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to update email spam status batch.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email spam status update error ({type(exc).__name__}): {exc}"
            ) from exc


    def list_by_account_and_box(self, account_id: str, box: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.LIST_BY_ACCOUNT_AND_BOX,
                        {"account_id": account_id, "box": box},
                    )
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list email metadata by account and box.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata list by account and box error ({type(exc).__name__}): {exc}"
            ) from exc
        return [dict(row) for row in rows]

    def list_by_mailbox_and_box(self, mailbox_id: str, box: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.LIST_BY_MAILBOX_AND_BOX,
                        {"mailbox_id": mailbox_id, "box": box},
                    )
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list email metadata by mailbox and box.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata list by mailbox and box error ({type(exc).__name__}): {exc}"
            ) from exc
        return [dict(row) for row in rows]


email_metadata_store = PgEmailMetadataStore()
