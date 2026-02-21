"""
Account-token persistence with encryption and legacy plaintext fallback.
"""

from __future__ import annotations

from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from api.database import connection
from api.database.queries import tokens as token_queries
from api.database.security import token_crypto
from api.database.settings import is_token_plaintext_fallback_enabled
from api.errors.exceptions import AccountNotConnected, DatabaseError, EnvVarError


def _normalize_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if not normalized:
        raise DatabaseError("Provider is required to load account tokens.")
    return normalized


def _serialize_scopes(scopes: Any) -> list[str] | None:
    if scopes is None:
        return None
    if isinstance(scopes, list):
        return [str(scope) for scope in scopes]
    return None


def _token_payload_from_row(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    Convert row into API payload and flag whether plaintext fallback was used.
    """
    encrypted_access = row.get("access_token_encrypted")
    encrypted_refresh = row.get("refresh_token_encrypted")
    used_plaintext = False

    if encrypted_access is not None or encrypted_refresh is not None:
        try:
            access_token = token_crypto.decrypt_token(encrypted_access)
            refresh_token = token_crypto.decrypt_token(encrypted_refresh)
        except EnvVarError:
            if not is_token_plaintext_fallback_enabled():
                raise
            used_plaintext = True
            access_token = row.get("access_token")
            refresh_token = row.get("refresh_token")
    else:
        if not is_token_plaintext_fallback_enabled():
            raise AccountNotConnected("Account token not found.")
        used_plaintext = True
        access_token = row.get("access_token")
        refresh_token = row.get("refresh_token")

    payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expiry": row["expiry"].isoformat() if row.get("expiry") else None,
        "scopes": list(row["scopes"]) if row.get("scopes") else None,
    }
    return payload, used_plaintext


def _backfill_plaintext_tokens(
    mailbox_id: str,
    account_id: str,
    provider: str,
    payload: dict[str, Any],
) -> None:
    """
    Best-effort lazy migration from plaintext columns to encrypted columns.
    """
    try:
        fernet = token_crypto.get_fernet(required=False)
    except EnvVarError:
        return
    if fernet is None:
        return

    params = {
        "mailbox_id": mailbox_id,
        "account_id": account_id,
        "provider": provider,
        "access_token_encrypted": (
            fernet.encrypt(payload["access_token"].encode("utf-8")).decode("utf-8")
            if payload.get("access_token") is not None
            else None
        ),
        "refresh_token_encrypted": (
            fernet.encrypt(payload["refresh_token"].encode("utf-8")).decode("utf-8")
            if payload.get("refresh_token") is not None
            else None
        ),
        "encryption_key_id": token_crypto.get_active_key_id(),
    }

    try:
        with connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(token_queries.BACKFILL_LEGACY_TOKENS, params)
    except psycopg2.Error as exc:
        raise DatabaseError("Failed to lazily migrate plaintext token.") from exc


def load_account_tokens(mailbox_id: str, account_id: str, provider: str) -> dict[str, Any]:
    """
    Load account token credentials for account+mailbox+provider context.
    """
    normalized_provider = _normalize_provider(provider)
    try:
        with connection.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    token_queries.SELECT_TOKENS_BY_CONTEXT,
                    {"account_id": account_id, "mailbox_id": mailbox_id, "provider": normalized_provider},
                )
                row = cur.fetchone()
    except psycopg2.Error as exc:
        raise DatabaseError("Failed to read token from database.") from exc

    if row is None:
        raise AccountNotConnected("Account token not found.")

    payload, used_plaintext = _token_payload_from_row(row)
    if used_plaintext:
        _backfill_plaintext_tokens(mailbox_id, account_id, normalized_provider, payload)
    return payload


def save_account_tokens(
    mailbox_id: str,
    account_id: str,
    provider: str,
    token_data: dict[str, Any],
) -> None:
    """
    Persist token credentials in encrypted form with account-context validation.
    """
    if not isinstance(token_data, dict):
        raise DatabaseError(
            "Token payload is invalid.",
            {"mailbox_id": mailbox_id, "account_id": account_id},
        )

    normalized_provider = _normalize_provider(provider)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    scopes = _serialize_scopes(token_data.get("scopes"))
    expiry = token_data.get("expiry")

    use_encryption = True
    encrypted_access_token: str | None = None
    encrypted_refresh_token: str | None = None
    try:
        encrypted_access_token = (
            token_crypto.encrypt_token(str(access_token)) if access_token is not None else None
        )
        encrypted_refresh_token = (
            token_crypto.encrypt_token(str(refresh_token)) if refresh_token is not None else None
        )
    except EnvVarError:
        if not is_token_plaintext_fallback_enabled():
            raise
        use_encryption = False

    if use_encryption:
        query = token_queries.UPSERT_TOKENS_ENCRYPTED
        params = {
            "mailbox_id": mailbox_id,
            "account_id": account_id,
            "provider": normalized_provider,
            "access_token_encrypted": encrypted_access_token,
            "refresh_token_encrypted": encrypted_refresh_token,
            "encryption_key_id": token_crypto.get_active_key_id(),
            "expiry": expiry,
            "scopes": scopes,
        }
    else:
        query = token_queries.UPSERT_TOKENS_PLAINTEXT
        params = {
            "mailbox_id": mailbox_id,
            "account_id": account_id,
            "provider": normalized_provider,
            "access_token": str(access_token) if access_token is not None else None,
            "refresh_token": str(refresh_token) if refresh_token is not None else None,
            "expiry": expiry,
            "scopes": scopes,
        }

    try:
        with connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.rowcount == 0:
                    raise DatabaseError(
                        "Token context validation failed.",
                        {
                            "mailbox_id": mailbox_id,
                            "account_id": account_id,
                            "provider": normalized_provider,
                        },
                    )
    except psycopg2.Error as exc:
        raise DatabaseError("Failed to save token to database.") from exc


def delete_account_tokens_for_records(accounts: Iterable[dict[str, Any]]) -> None:
    """
    Best-effort token deletion for a list of account records.
    """
    account_ids = [str(acc.get("account_id")) for acc in accounts if acc.get("account_id")]
    if not account_ids:
        return

    try:
        with connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(token_queries.DELETE_TOKENS_BY_ACCOUNT_IDS, (account_ids,))
    except psycopg2.Error as exc:
        raise DatabaseError("Failed to delete tokens from database.") from exc
