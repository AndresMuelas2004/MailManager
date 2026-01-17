"""
Shared helpers used across service modules.
"""

from __future__ import annotations

from typing import Any, Iterable

from core.email.email_manager import EmailManager

from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    ApiError,
    EnvVarError,
    MailboxNotFound,
)
from api.storage.json_store import mailbox_store


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
