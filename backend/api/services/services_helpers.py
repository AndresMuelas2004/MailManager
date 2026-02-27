"""
Shared helpers used across service modules.
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import SecretStr

from core.email.email_manager import EmailManager
from core.email.errors import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAuthError,
    EmailConfigError,
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
    EmailAccountRecordError,
    EmailProviderConfigError,
    EmailDuplicateAccountLabelError,
)

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    EmailSendError,
    EnvVarError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
)
from api.database import account_store, load_app_credentials, mailbox_store


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
    (EmailAccountRecordError, AccountMisconfigured),
    (EmailProviderConfigError, AccountMisconfigured),
    (EmailMissingAppCredentialsError, AccountMisconfigured),
    (EmailDuplicateAccountLabelError, AccountMisconfigured),
    (EmailConfigError, AccountMisconfigured),
    (EmailRecipientsMissingError, EmailSendError),
    (EmailExternalAPIError, ExternalAPIError),
    (CoreError, ApiError),
]


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
                    detail = {**detail, **(context or {})}
                detail["core_code"] = exc.code
                return api_type(exc.message, detail)
        # Unreachable when CoreError is in the map, but safe fallback.
        return fallback(str(exc), {**(context or {}), "core_code": exc.code})
    return fallback(str(exc) or "Unexpected error.", context or {})


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
    return manager


def raise_on_silent_auth_errors(errors: dict[str, Exception]) -> None:
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
            raise translate_core_error(error) from error

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
    token_data = account_store.get_tokens(mailbox_id, account_id, provider)
    payload = dict(token_data) if isinstance(token_data, dict) else {}
    if "access_token" in payload:
        payload["access_token"] = _wrap_secret(payload.get("access_token"))
    if "refresh_token" in payload:
        payload["refresh_token"] = _wrap_secret(payload.get("refresh_token"))
    return payload
