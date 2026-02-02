"""
Shared helpers used across service modules.
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import SecretStr

from core.email.email_manager import EmailManager

from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    ApiError,
    EnvVarError,
    MailboxNotFound,
)
from api.storage.json_store import mailbox_store
from api.storage.token_store import load_account_tokens, load_app_credentials


def ensure_mailbox_exists(mailbox_id: str) -> None:
    """
    Ensure the mailbox exists before executing any mailbox-scoped action.
    """
    # Central guard for mailbox-scoped service operations.
    if mailbox_store.get(mailbox_id) is None:
        raise MailboxNotFound(f"Mailbox '{mailbox_id}' not found.")


def build_manager_for_accounts(accounts: Iterable[dict[str, Any]]) -> EmailManager:
    """
    Build an EmailManager and register all account records on it.
    """
    manager = EmailManager()
    for account in accounts:
        try:
            # Each account record becomes a registered provider client.
            manager.add_account_record(account)
        except AttributeError as exc:
            raise AccountMisconfigured(
                "EmailManager is missing add_account_record(account_record)."
            ) from exc
        except ValueError as exc:
            raise AccountMisconfigured(str(exc)) from exc
    return manager


def raise_on_silent_auth_errors(errors: dict[str, Exception]) -> None:
    """
    Inspect the per-account errors collected during EmailManager.authenticate_all_silent().
    This stores at most one error per account label, so we iterate the dict and:
    - Raise immediately for non-auth errors (system/config issues) with the original message.
    - Accumulate all auth-related errors (missing token/refresh failures) and report them
      together as a single AccountNotConnected with the labels and reasons.
    """
    if not errors:
        return

    auth_labels = []
    reasons: dict[str, str] = {}
    for label, error in errors.items():
        if is_auth_error(error):
            auth_labels.append(label)
            reason = str(error).strip()
            if reason:
                reasons[label] = reason
        else:
            message = str(error).strip()
            if message in {
                "MIA_GMAIL_CREDENTIALS_PATH is not set.",
                "MIA_GMAIL_TOKEN_PATH is not set (must be a directory).",
            }:
                raise EnvVarError(message) from error
            # Any non-auth error is treated as an unexpected server failure.
            raise ApiError(message or "Unexpected server error.") from error

    if auth_labels:
        detail = {"account_labels": auth_labels}
        if reasons:
            detail["reasons"] = reasons
        raise AccountNotConnected(
            "One or more accounts are not connected. Call /connect first.",
            detail,
        )


_AUTH_ERROR_MESSAGES = {
    "missing_token",
    "missing_refresh_token",
    "refresh_failed",
    "gmailclient is not authenticated. call authenticate() first.",
}


def is_auth_error(exc: Exception) -> bool:
    """
    Return True when the exception matches a known auth/connectivity reason.
    """
    message = str(exc).strip().lower()
    return message in _AUTH_ERROR_MESSAGES


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


def load_wrapped_app_credentials() -> dict[str, Any]:
    """
    Load app credentials and wrap the client_secret as SecretStr.
    """
    credentials = load_app_credentials()
    payload = dict(credentials) if isinstance(credentials, dict) else {}
    if "client_secret" in payload:
        payload["client_secret"] = _wrap_secret(payload.get("client_secret"))
    return payload


def load_wrapped_account_tokens(mailbox_id: str, account_id: str) -> dict[str, Any]:
    """
    Load account tokens and wrap access/refresh tokens as SecretStr.
    """
    token_data = load_account_tokens(mailbox_id, account_id)
    payload = dict(token_data) if isinstance(token_data, dict) else {}
    if "access_token" in payload:
        payload["access_token"] = _wrap_secret(payload.get("access_token"))
    if "refresh_token" in payload:
        payload["refresh_token"] = _wrap_secret(payload.get("refresh_token"))
    return payload
