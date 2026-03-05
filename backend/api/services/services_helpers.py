"""
Shared helpers used across service modules.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable

logger = logging.getLogger(__name__)

from pydantic import SecretStr

from auth import (
    AuthError,
    AuthSettingsError,
    AuthTokenError,
    AuthTokenInvalidError,
    AuthTokenNetworkError,
    AuthTokenProviderError,
)
from core.email import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailAuthError,
    EmailConfigError,
    EmailDuplicateAccountLabelError,
    EmailExternalAPIError,
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
    EmailManager,
    EmailMetadata,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
    LabelUpdate,
)

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    AppCredentialsInvalid,
    AppCredentialsMissing,
    CredentialFileError,
    DatabaseConnectionError,
    DatabaseMigrationError,
    DatabaseQueryError,
    EnvVarError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
    RecipientsMissing,
    TokenDecryptionError,
    TokenIntegrityError,
    Unauthorized,
)
from database import (
    account_store,
    ConnectionPoolError,
    CredentialReadError,
    DatabaseError,
    email_metadata_store,
    load_app_credentials,
    mailbox_store,
    MigrationError,
    QueryError,
    SettingsError,
    TokenDecryptError,
    TokenValidationError,
    UnknownProviderError,
)


# ---------------------------------------------------------------------------
# Core → API error mapping (most specific first; evaluated with isinstance)
# ---------------------------------------------------------------------------

_CORE_TO_API_MAP: list[tuple[type[CoreError], type[ApiError]]] = [
    (EmailAccountNotFoundError, AccountNotFound),
    (EmailMissingTokenError, AccountNotConnected),
    (EmailMissingRefreshTokenError, AccountNotConnected),
    (EmailRefreshFailedError, AccountNotConnected),
    (EmailNotAuthenticatedError, AccountNotConnected),
    (EmailAuthError, AccountNotConnected),
    (EmailInvalidExpiryError, AccountMisconfigured),
    (EmailInvalidCredentialsDataError, AppCredentialsInvalid),
    (EmailInvalidTokenDataError, AccountMisconfigured),
    (EmailAccountRecordError, AccountMisconfigured),
    (EmailProviderConfigError, AccountMisconfigured),
    (EmailMissingAppCredentialsError, AppCredentialsMissing),
    (EmailDuplicateAccountLabelError, AccountMisconfigured),
    (EmailConfigError, AccountMisconfigured),
    (EmailRecipientsMissingError, RecipientsMissing),
    (EmailExternalAPIError, ExternalAPIError),
    (CoreError, ApiError),
]


# ---------------------------------------------------------------------------
# Database → API error mapping (most specific first; evaluated with isinstance)
# ---------------------------------------------------------------------------

_DB_TO_API_MAP: list[tuple[type[DatabaseError], type[ApiError]]] = [
    (ConnectionPoolError, DatabaseConnectionError),
    (QueryError, DatabaseQueryError),
    (MigrationError, DatabaseMigrationError),
    (SettingsError, EnvVarError),
    (TokenDecryptError, TokenDecryptionError),
    (TokenValidationError, TokenIntegrityError),
    (CredentialReadError, CredentialFileError),
    (UnknownProviderError, AccountMisconfigured),
    (DatabaseError, ApiError),
]


# ---------------------------------------------------------------------------
# Auth → API error mapping (most specific first; evaluated with isinstance)
# ---------------------------------------------------------------------------

_AUTH_TO_API_MAP: list[tuple[type[AuthError], type[ApiError]]] = [
    (AuthSettingsError, EnvVarError),
    (AuthTokenNetworkError, ExternalAPIError),
    (AuthTokenInvalidError, Unauthorized),
    (AuthTokenProviderError, Unauthorized),
    (AuthTokenError, Unauthorized),
    (AuthError, ApiError),
]


def translate_auth_error(
    exc: Exception,
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate an AuthError into the corresponding ApiError using the mapping.

    If *exc* is an AuthError subclass the first matching entry in
    ``_AUTH_TO_API_MAP`` is used.  Otherwise *fallback* is instantiated.
    """
    if isinstance(exc, AuthError):
        for auth_type, api_type in _AUTH_TO_API_MAP:
            if isinstance(exc, auth_type):
                detail = exc.detail if hasattr(exc, "detail") else {}
                if context:
                    detail = {**detail, **context}
                detail["auth_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when AuthError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "auth_code": exc.code})
    return fallback(str(exc) or "Unexpected auth error.", context or {})


def translate_core_error(
    exc: Exception,
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate a CoreError into the corresponding ApiError using the mapping.

    If *exc* is a CoreError subclass the first matching entry in
    ``_CORE_TO_API_MAP`` is used.  Otherwise *fallback* is instantiated.
    """
    if isinstance(exc, CoreError):
        for core_type, api_type in _CORE_TO_API_MAP:
            if isinstance(exc, core_type):
                detail = exc.detail if hasattr(exc, "detail") else {}
                if context:
                    detail = {**detail, **context}
                detail["core_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when CoreError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "core_code": exc.code})
    return fallback(str(exc) or "Unexpected error.", context or {})


def translate_database_error(
    exc: Exception,
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate a DatabaseError into the corresponding ApiError using the mapping.

    If *exc* is a DatabaseError subclass the first matching entry in
    ``_DB_TO_API_MAP`` is used.  Otherwise *fallback* is instantiated.
    """
    if isinstance(exc, DatabaseError):
        for db_type, api_type in _DB_TO_API_MAP:
            if isinstance(exc, db_type):
                detail = exc.detail if hasattr(exc, "detail") else {}
                if context:
                    detail = {**detail, **context}
                detail["db_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when DatabaseError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "db_code": exc.code})
    return fallback(str(exc) or "Unexpected database error.", context or {})


@contextmanager
def catch_database_errors(
    *,
    fallback: type[ApiError] = ApiError,
    context: dict[str, Any] | None = None,
):
    """
    Context manager that catches ``DatabaseError`` and re-raises as ``ApiError``.
    """
    try:
        yield
    except DatabaseError as exc:
        raise translate_database_error(exc, fallback=fallback, context=context) from exc
    except Exception as exc:
        logger.warning("Unexpected database operation error (%s): %s", type(exc).__name__, exc)
        raise fallback(
            "Unexpected database operation error.",
            context or {},
        ) from exc


def translate_connect_error(
    exc: Exception,
    *,
    context: dict[str, Any] | None = None,
) -> ApiError:
    """
    Translate errors for the interactive account-connect flow.

    Unlike mailbox operations that require a pre-connected account (409),
    connect-time authentication failures should return 401.
    """
    if isinstance(exc, EmailAuthError):
        detail = exc.detail if hasattr(exc, "detail") else {}
        if context:
            detail = {**detail, **context}
        detail["core_code"] = exc.code
        return AccountConnectAuthError(exc.message, detail)
    return translate_core_error(exc, fallback=AccountConnectAuthError, context=context)


def ensure_mailbox_access(mailbox_id: str, user_id: str) -> dict[str, Any]:
    """
    Ensure the mailbox exists and the authenticated user owns it.

    Returns the mailbox record so callers can reuse it without a second fetch.
    """
    with catch_database_errors():
        record = mailbox_store.get(mailbox_id)
    if record is None:
        raise MailboxNotFound(f"Mailbox '{mailbox_id}' not found.")
    if record.get("owner_user_id") != user_id:
        raise Forbidden("You do not have access to this mailbox.")
    return record


def build_manager_for_accounts(accounts: Iterable[dict[str, Any]]) -> EmailManager:
    """
    Build an EmailManager and register all account records on it.
    """
    manager = EmailManager()
    for account in accounts:
        try:
            manager.add_account_record(account)
        except CoreError as exc:
            raise translate_core_error(exc, fallback=AccountMisconfigured) from exc
        except Exception as exc:
            logger.warning("Failed to register account in manager (%s): %s", type(exc).__name__, exc)
            raise AccountMisconfigured(
                "Failed to register account in manager."
            ) from exc
    return manager


def raise_on_silent_auth_errors(
    errors: dict[str, Exception],
    *,
    fallback: type[ApiError] = ApiError,
) -> None:
    """
    Inspect the per-account errors collected during EmailManager.authenticate_all_silent().

    - Non-auth CoreErrors are translated via the centralized mapping and raised immediately.
    - Auth-related errors are accumulated and raised as a single AccountNotConnected.
    - Non-CoreError exceptions are raised through the fallback path.
    """
    if not errors:
        return

    auth_labels: list[str] = []
    reasons: dict[str, str] = {}
    for label, error in errors.items():
        if is_auth_error(error):
            auth_labels.append(label)
            reason = str(error).strip()
            if reason:
                reasons[label] = reason
        else:
            raise translate_core_error(error, fallback=fallback) from error

    if auth_labels:
        detail: dict[str, Any] = {"account_labels": auth_labels}
        if reasons:
            detail["reasons"] = reasons
        raise AccountNotConnected(
            "One or more accounts are not connected. Call /connect first.",
            detail,
        )


def is_auth_error(exc: Exception) -> bool:
    """
    Return True when the exception is a typed core authentication error.
    """
    return isinstance(exc, EmailAuthError)


def _wrap_secret(value: Any) -> Any:
    if value is None:
        return None
    return SecretStr(str(value))


def unwrap_secret(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def load_wrapped_app_credentials(provider: str) -> dict[str, Any]:
    """
    Load app credentials for *provider* and wrap the client_secret as SecretStr.
    """
    with catch_database_errors():
        credentials = load_app_credentials(provider)
    payload = dict(credentials) if isinstance(credentials, dict) else {}
    if "client_secret" in payload:
        payload["client_secret"] = _wrap_secret(payload.get("client_secret"))
    return payload


def load_wrapped_account_tokens(
    mailbox_id: str, account_id: str, provider: str,
) -> dict[str, Any]:
    """
    Load account tokens for *provider* and wrap access/refresh tokens as SecretStr.
    """
    with catch_database_errors():
        token_data = account_store.get_tokens(mailbox_id, account_id, provider)
    payload = dict(token_data) if isinstance(token_data, dict) else {}
    if "access_token" in payload:
        payload["access_token"] = _wrap_secret(payload.get("access_token"))
    if "refresh_token" in payload:
        payload["refresh_token"] = _wrap_secret(payload.get("refresh_token"))
    return payload


# ---------------------------------------------------------------------------
# Email metadata persistence helpers
# ---------------------------------------------------------------------------


def persist_email_metadata_batch(
    account_id: str,
    metadata_list: list[EmailMetadata],
) -> int:
    """Persist email metadata to DB via batch upsert. Returns rows affected."""
    if not metadata_list:
        return 0
    rows = [
        (
            m.provider_message_id, account_id, m.thread_id, m.from_email,
            m.from_name, m.subject, m.received_at, m.is_read, m.box,
        )
        for m in metadata_list
    ]
    with catch_database_errors():
        return email_metadata_store.upsert_batch(account_id, rows)


def load_sync_cursors(
    label_lookup: dict[str, tuple[str, str, str]],
) -> dict[str, str | None]:
    """Load the sync cursor for each account, keyed by account label."""
    cursors: dict[str, str | None] = {}
    for label, (mailbox_id, account_id, _provider) in label_lookup.items():
        with catch_database_errors():
            cursors[label] = account_store.get_sync_cursor(mailbox_id, account_id)
    return cursors


def delete_email_metadata_batch(
    account_id: str,
    message_ids: list[str],
) -> int:
    """Delete email metadata by provider_message_ids. Returns rows deleted."""
    if not message_ids:
        return 0
    with catch_database_errors():
        return email_metadata_store.delete_batch_by_message_ids(account_id, message_ids)


def update_email_metadata_labels_batch(
    account_id: str,
    label_updates: list[LabelUpdate],
) -> int:
    """Update only is_read and box for specific messages. Returns rows updated."""
    if not label_updates:
        return 0
    rows = [
        (lu.provider_message_id, account_id, lu.is_read, lu.box)
        for lu in label_updates
    ]
    with catch_database_errors():
        return email_metadata_store.update_labels_batch(account_id, rows)


def update_sync_cursor(mailbox_id: str, account_id: str, cursor: str) -> None:
    """Persist the new sync_cursor for an account."""
    with catch_database_errors():
        account_store.update_sync_cursor(mailbox_id, account_id, cursor)
