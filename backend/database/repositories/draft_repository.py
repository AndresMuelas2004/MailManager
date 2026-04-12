"""
PostgreSQL draft repository.
"""
from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from database import connection
from database.contracts import DraftStore
from database.queries import drafts as queries
from database.errors import DatabaseError, QueryError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a psycopg2 RealDict row into a serializable dict."""
    result = dict(row)
    if result.get("account_id") is not None:
        result["account_id"] = str(result["account_id"])
    for key in ("to_recipients", "cc_recipients", "bcc_recipients"):
        if result.get(key) is None:
            result[key] = []
    return result


class PgDraftStore(DraftStore):
    """
    PostgreSQL-backed draft persistence.
    """

    def create(self, draft: dict[str, Any]) -> dict[str, Any]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(queries.INSERT_DRAFT, draft)
                    row = cur.fetchone()
            return _row_to_dict(row)
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to create draft.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected draft create error ({type(exc).__name__}): {exc}"
            ) from exc

    def get(
        self,
        provider_draft_id: str,
        account_id: str,
    ) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.GET_DRAFT,
                        {
                            "provider_draft_id": provider_draft_id,
                            "account_id": account_id,
                        },
                    )
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get draft.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected draft get error ({type(exc).__name__}): {exc}"
            ) from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def update(self, draft: dict[str, Any]) -> dict[str, Any]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(queries.UPDATE_DRAFT, draft)
                    row = cur.fetchone()
            if row is None:
                raise QueryError("Draft row to update not found.")
            return _row_to_dict(row)
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to update draft.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected draft update error ({type(exc).__name__}): {exc}"
            ) from exc

    def list_by_account(self, account_id: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.LIST_DRAFTS_BY_ACCOUNT,
                        {"account_id": account_id},
                    )
                    rows = cur.fetchall()
            return [_row_to_dict(row) for row in rows]
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list drafts by account.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected drafts list by account error ({type(exc).__name__}): {exc}"
            ) from exc

    def list_by_mailbox(self, mailbox_id: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.LIST_DRAFTS_BY_MAILBOX,
                        {"mailbox_id": mailbox_id},
                    )
                    rows = cur.fetchall()
            return [_row_to_dict(row) for row in rows]
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to list drafts by mailbox.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected drafts list by mailbox error ({type(exc).__name__}): {exc}"
            ) from exc

    def replace_all_for_account(
        self,
        account_id: str,
        drafts: list[dict[str, Any]],
    ) -> int:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    if drafts:
                        rows = [
                            (
                                str(d["provider_draft_id"]),
                                account_id,
                                list(d.get("to_recipients") or []),
                                list(d.get("cc_recipients") or []),
                                list(d.get("bcc_recipients") or []),
                                str(d.get("subject") or ""),
                                str(d.get("body_html") or ""),
                                d.get("created_at"),
                                d.get("updated_at"),
                            )
                            for d in drafts
                        ]
                        psycopg2.extras.execute_values(
                            cur, queries.UPSERT_DRAFTS_BATCH, rows,
                        )
                    keep_ids = [str(d["provider_draft_id"]) for d in drafts]
                    cur.execute(
                        queries.DELETE_DRAFTS_MISSING_FOR_ACCOUNT,
                        {"account_id": account_id, "keep_ids": keep_ids},
                    )
        except psycopg2.errors.InvalidTextRepresentation as exc:
            raise QueryError(
                f"Invalid account_id format for drafts replace: {exc}"
            ) from exc
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to replace drafts for account.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected drafts replace error ({type(exc).__name__}): {exc}"
            ) from exc
        return len(drafts)


    def get(self, account_id: str, provider_draft_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        queries.GET_DRAFT,
                        {"provider_draft_id": provider_draft_id, "account_id": account_id},
                    )
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get draft.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected draft get error ({type(exc).__name__}): {exc}"
            ) from exc
        return _row_to_dict(row) if row is not None else None

    def delete(self, account_id: str, provider_draft_id: str) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        queries.DELETE_DRAFT,
                        {"provider_draft_id": provider_draft_id, "account_id": account_id},
                    )
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete draft.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected draft delete error ({type(exc).__name__}): {exc}"
            ) from exc


draft_store = PgDraftStore()
