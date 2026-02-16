"""
PostgreSQL-backed persistence for mailboxes and accounts.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg2.errors
import psycopg2.extras

from api.database.base import AccountStore, MailboxStore
from api.database.db import get_connection
from api.errors.exceptions import StorageError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a RealDictRow to a plain dict with serialisable values."""
    result = dict(row)
    for key in ("mailbox_id", "account_id"):
        if key in result and result[key] is not None:
            result[key] = str(result[key])
    if "created_at" in result and result["created_at"] is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result


class PgMailboxStore(MailboxStore):
    """PostgreSQL persistence for mailboxes."""

    def create(self, mailbox: dict[str, Any]) -> dict[str, Any]:
        sql = """
            INSERT INTO mailboxes (mailbox_id, display_name)
            VALUES (%(mailbox_id)s, %(display_name)s)
            RETURNING mailbox_id, display_name, created_at
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, mailbox)
                    row = cur.fetchone()
        except psycopg2.Error as exc:
            raise StorageError("Failed to create mailbox.") from exc
        return _row_to_dict(row)

    def list(self) -> list[dict[str, Any]]:
        sql = "SELECT mailbox_id, display_name, created_at FROM mailboxes ORDER BY created_at"
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
        except psycopg2.Error as exc:
            raise StorageError("Failed to list mailboxes.") from exc
        return [_row_to_dict(r) for r in rows]

    def get(self, mailbox_id: str) -> dict[str, Any] | None:
        sql = """
            SELECT mailbox_id, display_name, created_at
            FROM mailboxes WHERE mailbox_id = %s
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (mailbox_id,))
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except psycopg2.Error as exc:
            raise StorageError("Failed to get mailbox.") from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def delete(self, mailbox_id: str) -> None:
        sql = "DELETE FROM mailboxes WHERE mailbox_id = %s"
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (mailbox_id,))
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except psycopg2.Error as exc:
            raise StorageError("Failed to delete mailbox.") from exc


class PgAccountStore(AccountStore):
    """PostgreSQL persistence for accounts."""

    def list_by_mailbox(self, mailbox_id: str) -> list[dict[str, Any]]:
        sql = """
            SELECT account_id, mailbox_id, provider, display_label, config, created_at
            FROM accounts WHERE mailbox_id = %s ORDER BY created_at
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (mailbox_id,))
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except psycopg2.Error as exc:
            raise StorageError("Failed to list accounts.") from exc
        return [_row_to_dict(r) for r in rows]

    def get(self, mailbox_id: str, account_id: str) -> dict[str, Any] | None:
        sql = """
            SELECT account_id, mailbox_id, provider, display_label, config, created_at
            FROM accounts WHERE mailbox_id = %s AND account_id = %s
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (mailbox_id, account_id))
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except psycopg2.Error as exc:
            raise StorageError("Failed to get account.") from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def upsert(self, account: dict[str, Any]) -> dict[str, Any]:
        sql = """
            INSERT INTO accounts (account_id, mailbox_id, provider, display_label, config)
            VALUES (%(account_id)s, %(mailbox_id)s, %(provider)s, %(display_label)s,
                    %(config)s::jsonb)
            ON CONFLICT (account_id) DO UPDATE SET
                display_label = EXCLUDED.display_label,
                config = EXCLUDED.config
            RETURNING account_id, mailbox_id, provider, display_label, config, created_at
        """
        params = dict(account)
        if isinstance(params.get("config"), dict):
            params["config"] = json.dumps(params["config"])
        elif params.get("config") is None:
            params["config"] = "{}"
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone()
        except psycopg2.Error as exc:
            raise StorageError("Failed to upsert account.") from exc
        return _row_to_dict(row)

    def delete(self, mailbox_id: str, account_id: str) -> None:
        sql = "DELETE FROM accounts WHERE mailbox_id = %s AND account_id = %s"
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (mailbox_id, account_id))
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except psycopg2.Error as exc:
            raise StorageError("Failed to delete account.") from exc


mailbox_store = PgMailboxStore()
account_store = PgAccountStore()
