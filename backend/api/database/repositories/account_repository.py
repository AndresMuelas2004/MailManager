"""
PostgreSQL account repository with integrated token persistence.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg2.errors
import psycopg2.extras

from api.database import connection
from api.database.contracts import AccountStore
from api.database.queries import accounts
from api.database.security import token_crypto
from api.errors.exceptions import (
    ApiError,
    DatabaseQueryError,
    EnvVarError,
    TokenIntegrityError,
)

logger = logging.getLogger(__name__)


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("mailbox_id", "account_id"):
        if result.get(key) is not None:
            result[key] = str(result[key])
    if result.get("created_at") is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result


# ---------------------------------------------------------------------------
# Token helpers (migrated from token_repository)
# ---------------------------------------------------------------------------


def _normalize_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if not normalized:
        raise TokenIntegrityError("Provider is required to load account tokens.")
    return normalized


def _serialize_scopes(scopes: Any) -> list[str] | None:
    if scopes is None:
        return None
    if isinstance(scopes, list):
        return [str(scope) for scope in scopes]
    return None


def _token_payload_from_row(row: dict[str, Any]) -> tuple[dict[str, Any], bool] | None:
    """
    Convert row into API payload and flag whether plaintext fallback was used.

    Returns ``None`` when no usable token exists (no encrypted columns and
    plaintext fallback disabled).  A malformed ``TOKEN_ENCRYPTION_KEY`` raises
    ``EnvVarError`` immediately — it never silently falls back to plaintext.
    """
    encrypted_access = row.get("access_token_encrypted")
    encrypted_refresh = row.get("refresh_token_encrypted")
    used_plaintext = False

    if encrypted_access is not None or encrypted_refresh is not None:
        fernet = token_crypto.get_fernet(required=False)
        if fernet is not None:
            access_token = token_crypto.decrypt_token(encrypted_access)
            refresh_token = token_crypto.decrypt_token(encrypted_refresh)
        elif token_crypto.is_plaintext_fallback_enabled():
            used_plaintext = True
            access_token = row.get("access_token")
            refresh_token = row.get("refresh_token")
        else:
            return None
    else:
        if not token_crypto.is_plaintext_fallback_enabled():
            return None
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
                cur.execute(accounts.BACKFILL_LEGACY_TOKENS, params)
    except Exception:
        logger.warning(
            "Lazy token backfill failed for account %s; will retry on next read.",
            account_id,
            exc_info=True,
        )


class PgAccountStore(AccountStore):
    """
    PostgreSQL-backed account persistence with integrated token operations.
    """

    def list_by_mailbox(self, mailbox_id: str) -> list[dict[str, Any]]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(accounts.LIST_ACCOUNTS_BY_MAILBOX, {"mailbox_id": mailbox_id})
                    rows = cur.fetchall()
        except psycopg2.errors.InvalidTextRepresentation:
            return []
        except ApiError:
            raise
        except psycopg2.Error as exc:
            raise DatabaseQueryError("Failed to list accounts.") from exc
        except Exception as exc:
            raise DatabaseQueryError(
                f"Unexpected account list error ({type(exc).__name__}): {exc}"
            ) from exc
        return [_row_to_dict(row) for row in rows]

    def get(self, mailbox_id: str, account_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(accounts.GET_ACCOUNT, {"mailbox_id": mailbox_id, "account_id": account_id})
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except ApiError:
            raise
        except psycopg2.Error as exc:
            raise DatabaseQueryError("Failed to get account.") from exc
        except Exception as exc:
            raise DatabaseQueryError(
                f"Unexpected account get error ({type(exc).__name__}): {exc}"
            ) from exc
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
        except ApiError:
            raise
        except psycopg2.Error as exc:
            raise DatabaseQueryError("Failed to upsert account.") from exc
        except Exception as exc:
            raise DatabaseQueryError(
                f"Unexpected account upsert error ({type(exc).__name__}): {exc}"
            ) from exc
        return _row_to_dict(row)

    def delete(self, mailbox_id: str, account_id: str) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(accounts.DELETE_ACCOUNT, {"mailbox_id": mailbox_id, "account_id": account_id})
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except ApiError:
            raise
        except psycopg2.Error as exc:
            raise DatabaseQueryError("Failed to delete account.") from exc
        except Exception as exc:
            raise DatabaseQueryError(
                f"Unexpected account delete error ({type(exc).__name__}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Token operations
    # ------------------------------------------------------------------

    def get_tokens(self, mailbox_id: str, account_id: str, provider: str) -> dict[str, Any] | None:
        normalized_provider = _normalize_provider(provider)
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        accounts.SELECT_TOKENS_BY_CONTEXT,
                        {"account_id": account_id, "mailbox_id": mailbox_id, "provider": normalized_provider},
                    )
                    row = cur.fetchone()
        except ApiError:
            raise
        except psycopg2.Error as exc:
            raise DatabaseQueryError("Failed to read token from database.") from exc
        except Exception as exc:
            raise DatabaseQueryError(
                f"Unexpected token get error ({type(exc).__name__}): {exc}"
            ) from exc

        if row is None:
            return None

        result = _token_payload_from_row(row)
        if result is None:
            return None

        payload, used_plaintext = result
        if used_plaintext:
            _backfill_plaintext_tokens(mailbox_id, account_id, normalized_provider, payload)
        return payload

    def upsert_tokens(
        self,
        mailbox_id: str,
        account_id: str,
        provider: str,
        token_data: dict[str, Any],
    ) -> None:
        if not isinstance(token_data, dict):
            raise TokenIntegrityError(
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
        fernet = token_crypto.get_fernet(required=False)
        if fernet is not None:
            encrypted_access_token = (
                token_crypto.encrypt_token(str(access_token)) if access_token is not None else None
            )
            encrypted_refresh_token = (
                token_crypto.encrypt_token(str(refresh_token)) if refresh_token is not None else None
            )
        elif token_crypto.is_plaintext_fallback_enabled():
            use_encryption = False
        else:
            raise EnvVarError(
                "TOKEN_ENCRYPTION_KEY is required when plaintext fallback is disabled."
            )

        if use_encryption:
            query = accounts.UPSERT_TOKENS_ENCRYPTED
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
            query = accounts.UPSERT_TOKENS_PLAINTEXT
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
                        raise TokenIntegrityError(
                            "Token context validation failed.",
                            {
                                "mailbox_id": mailbox_id,
                                "account_id": account_id,
                                "provider": normalized_provider,
                            },
                        )
        except ApiError:
            raise
        except psycopg2.Error as exc:
            raise DatabaseQueryError("Failed to save token to database.") from exc
        except Exception as exc:
            raise DatabaseQueryError(
                f"Unexpected token upsert error ({type(exc).__name__}): {exc}"
            ) from exc


account_store = PgAccountStore()
