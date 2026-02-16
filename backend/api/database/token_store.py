"""
Token storage helpers for provider accounts.

App credentials are loaded from environment-variable file paths (unchanged).
Account tokens are stored in the PostgreSQL tokens table.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg2.extras

from api.database.db import get_connection
from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    EnvVarError,
    StorageError,
)


_ENV_CREDENTIALS: dict[str, str] = {
    "gmail": "MIA_GMAIL_CREDENTIALS_PATH",
    "outlook": "MIA_OUTLOOK_CREDENTIALS_PATH",
}


# ---- App credentials (unchanged, reads from file system) ----


def load_app_credentials(provider: str) -> dict[str, Any]:
    """
    Load app credentials for the given provider from its environment-variable path.
    """
    provider = provider.lower()
    env_var = _ENV_CREDENTIALS.get(provider)
    if not env_var:
        raise AccountMisconfigured(f"Unknown provider '{provider}'.")

    credentials_path = os.getenv(env_var)
    if not credentials_path:
        raise EnvVarError(f"{env_var} is not set.")
    config_path = Path(credentials_path)
    try:
        raw = config_path.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError("Failed to read config storage file.", {"path": str(config_path)}) from exc

    if not isinstance(data, dict):
        raise StorageError("Config storage file is corrupted.", {"path": str(config_path)})

    if provider == "gmail":
        if isinstance(data.get("installed"), dict):
            return data["installed"]
        if isinstance(data.get("web"), dict):
            return data["web"]

    return data


# ---- Account tokens (PostgreSQL tokens table) ----


def load_account_tokens(mailbox_id: str, account_id: str, provider: str) -> dict[str, Any]:
    """
    Load token credentials for a specific account from the tokens table.
    """
    sql = """
        SELECT access_token, refresh_token, expiry, scopes
        FROM tokens WHERE account_id = %s
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (account_id,))
                row = cur.fetchone()
    except psycopg2.Error as exc:
        raise StorageError("Failed to read token from database.") from exc

    if row is None:
        raise AccountNotConnected("Account token not found.")

    return {
        "access_token": row.get("access_token"),
        "refresh_token": row.get("refresh_token"),
        "expiry": row["expiry"].isoformat() if row.get("expiry") else None,
        "scopes": list(row["scopes"]) if row.get("scopes") else None,
    }


def save_account_tokens(
    mailbox_id: str,
    account_id: str,
    provider: str,
    token_data: dict[str, Any],
) -> None:
    """
    Persist token credentials for an account in the tokens table (upsert).
    """
    if not isinstance(token_data, dict):
        raise StorageError(
            "Token payload is invalid.",
            {"mailbox_id": mailbox_id, "account_id": account_id},
        )

    sql = """
        INSERT INTO tokens (account_id, access_token, refresh_token, expiry, scopes, updated_at)
        VALUES (%(account_id)s, %(access_token)s, %(refresh_token)s,
                %(expiry)s, %(scopes)s, now())
        ON CONFLICT (account_id) DO UPDATE SET
            access_token  = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            expiry        = EXCLUDED.expiry,
            scopes        = EXCLUDED.scopes,
            updated_at    = now()
    """
    scopes = token_data.get("scopes")
    if isinstance(scopes, list):
        scopes = list(scopes)

    params = {
        "account_id": account_id,
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expiry": token_data.get("expiry"),
        "scopes": scopes,
    }
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
    except psycopg2.Error as exc:
        raise StorageError("Failed to save token to database.") from exc


def delete_account_tokens_for_records(accounts: Iterable[dict[str, Any]]) -> None:
    """
    Best-effort deletion of tokens for a list of account records.
    """
    account_ids = [
        str(acc.get("account_id"))
        for acc in accounts
        if acc.get("account_id")
    ]
    if not account_ids:
        return

    sql = "DELETE FROM tokens WHERE account_id = ANY(%s)"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (account_ids,))
    except psycopg2.Error as exc:
        raise StorageError("Failed to delete tokens from database.") from exc
