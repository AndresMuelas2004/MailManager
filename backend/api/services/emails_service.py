"""
Service layer for email operations.
"""

from __future__ import annotations

from typing import Any

from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    EmailFetchError,
    EmailSendError,
)
from api.schemas.email import EmailOut, EmailSendRequest
from api.services.services_helpers import (
    build_manager_for_accounts,
    ensure_mailbox_exists,
    is_auth_error,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    raise_on_silent_auth_errors,
    unwrap_secret,
)
from api.storage.json_store import account_store
from api.storage.token_store import save_account_tokens


def _persist_refreshed_tokens(
    updated_tokens: dict[str, dict[str, Any]],
    label_lookup: dict[str, tuple[str, str]],
) -> None:
    for account_label, token_payload in updated_tokens.items():
        ids = label_lookup.get(account_label)
        if not ids:
            continue
        mailbox_id, account_id = ids
        payload = dict(token_payload or {})
        payload["access_token"] = unwrap_secret(payload.get("access_token"))
        payload["refresh_token"] = unwrap_secret(payload.get("refresh_token"))
        save_account_tokens(mailbox_id, account_id, payload)


def get_unread(mailbox_id: str) -> list[EmailOut]:
    ensure_mailbox_exists(mailbox_id)
    accounts = account_store.list_by_mailbox(mailbox_id)
    auth_payloads = {}
    label_lookup: dict[str, tuple[str, str]] = {}
    app_credentials = load_wrapped_app_credentials()
    for account in accounts:
        account_id = str(account.get("account_id") or "")
        if not account_id:
            continue
        account_label = f"{mailbox_id}__{account_id}"
        user_tokens = load_wrapped_account_tokens(mailbox_id, account_id)
        auth_payloads[account_label] = (app_credentials, user_tokens)
        label_lookup[account_label] = (mailbox_id, account_id)
    manager = build_manager_for_accounts(accounts)

    # Silent auth attempts may refresh tokens without launching interactive flows.
    updated_tokens = manager.authenticate_all_silent(auth_payloads)
    if updated_tokens:
        _persist_refreshed_tokens(updated_tokens, label_lookup)
    raise_on_silent_auth_errors(manager.get_last_errors())

    try:
        unread = manager.fetch_all_unread_emails()
    except Exception as exc:
        if is_auth_error(exc):
            raise AccountNotConnected(
                "One or more accounts are not connected. Call /connect first."
            ) from exc
        raise EmailFetchError("Failed to fetch unread emails.") from exc

    errors = manager.get_last_errors()
    if errors:
        auth_labels = [label for label, error in errors.items() if is_auth_error(error)]
        if auth_labels:
            raise AccountNotConnected(
                "One or more accounts are not connected. Call /connect first.",
                {"account_labels": auth_labels},
            )
        raise EmailFetchError(
            "Failed to fetch unread emails from one or more accounts.",
            {"account_labels": list(errors.keys())},
        )

    return [EmailOut.from_core(email) for email in unread]

def send_email(mailbox_id: str, payload: EmailSendRequest) -> dict[str, str]:
    ensure_mailbox_exists(mailbox_id)
    account = account_store.get(mailbox_id, payload.account_id)
    if account is None:
        raise AccountNotFound(f"Account '{payload.account_id}' not found.")

    manager = build_manager_for_accounts([account])
    account_label = f"{mailbox_id}__{payload.account_id}"
    app_credentials = load_wrapped_app_credentials()
    user_tokens = load_wrapped_account_tokens(mailbox_id, payload.account_id)
    auth_payloads = {account_label: (app_credentials, user_tokens)}
    label_lookup = {account_label: (mailbox_id, payload.account_id)}
    # Ensure the account is silently authenticated before sending.
    updated_tokens = manager.authenticate_all_silent(auth_payloads)
    if updated_tokens:
        _persist_refreshed_tokens(updated_tokens, label_lookup)
    raise_on_silent_auth_errors(manager.get_last_errors())

    try:
        manager.send_email_from_account(
            account_label=account_label,
            subject=payload.subject,
            body=payload.body,
            recipients=payload.recipients,
        )
    except Exception as exc:
        if is_auth_error(exc):
            raise AccountNotConnected(
                "Account is not connected. Call /connect first.",
                {"account_id": payload.account_id, "account_label": account_label},
            ) from exc
        raise EmailSendError("Failed to send email.") from exc

    return {"status": "sent"}
