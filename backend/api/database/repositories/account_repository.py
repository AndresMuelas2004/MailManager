"""
PostgreSQL account repository.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg2.errors
import psycopg2.extras

from api.database import connection
from api.database.contracts import AccountStore
from api.database.queries import accounts
from api.errors.exceptions import DatabaseError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("mailbox_id", "account_id"):
        if result.get(key) is not None:
            result[key] = str(result[key])
    if result.get("created_at") is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result


class PgAccountStore(AccountStore):
    """
    PostgreSQL-backed account persistence.
    """

    def list_by_mailbox(self, mailbox_id: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(accounts.LIST_ACCOUNTS_BY_MAILBOX, {"mailbox_id": mailbox_id})
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to list accounts.") from exc
        return [_row_to_dict(row) for row in rows]

    def get(self, mailbox_id: str, account_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(accounts.GET_ACCOUNT, {"mailbox_id": mailbox_id, "account_id": account_id})
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to get account.") from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def upsert(self, account: dict[str, Any]) -> dict[str, Any]:
        params = dict(account)
        if isinstance(params.get("config"), dict):
            params["config"] = json.dumps(params["config"])
        elif params.get("config") is None:
            params["config"] = "{}"

        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(accounts.UPSERT_ACCOUNT, params)
                    row = cur.fetchone()
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to upsert account.") from exc
        return _row_to_dict(row)

    def delete(self, mailbox_id: str, account_id: str) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(accounts.DELETE_ACCOUNT, {"mailbox_id": mailbox_id, "account_id": account_id})
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to delete account.") from exc


account_store = PgAccountStore()

