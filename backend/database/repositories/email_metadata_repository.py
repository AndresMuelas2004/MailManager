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
from database.errors.exceptions import DatabaseError, QueryError


class PgEmailMetadataStore(EmailMetadataStore):
    """
    PostgreSQL-backed email metadata persistence.
    """

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

    def list_by_account(self, account_id: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(queries.LIST_BY_ACCOUNT, {"account_id": account_id})
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list email metadata.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata list error ({type(exc).__name__}): {exc}"
            ) from exc
        return [dict(row) for row in rows]

    def delete_by_account(self, account_id: str) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(queries.DELETE_BY_ACCOUNT, {"account_id": account_id})
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete email metadata.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected email metadata delete error ({type(exc).__name__}): {exc}"
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


email_metadata_store = PgEmailMetadataStore()
