"""
Service layer for email operations.
"""

from __future__ import annotations

from typing import Any

from api.errors.exceptions import (
    AccountNotConnected,
    AccountNotFound,
    EmailFetchError,
    EmailSendError,
)
from core.email import CoreError
from api.schemas.email import AccountSyncDetail, EmailSendRequest, SyncResultOut
from api.services.services_helpers import (
    build_manager_for_accounts,
    catch_database_errors,
    ensure_mailbox_access,
    is_auth_error,
    load_sync_cursors,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    persist_email_metadata_batch,
    raise_on_silent_auth_errors,
    translate_core_error,
    unwrap_secret,
    update_sync_cursor,
)
from database import account_store


def _persist_refreshed_tokens(
    updated_tokens: dict[str, dict[str, Any]],
    label_lookup: dict[str, tuple[str, str, str]],
) -> None:
    for account_label, token_payload in updated_tokens.items():
        ids = label_lookup.get(account_label)
        if not ids:
            continue
        mailbox_id, account_id, provider = ids
        payload = dict(token_payload or {})
        payload["access_token"] = unwrap_secret(payload.get("access_token"))
        payload["refresh_token"] = unwrap_secret(payload.get("refresh_token"))
        with catch_database_errors():
            account_store.upsert_tokens(mailbox_id, account_id, provider, payload)


def _build_auth_context(
    accounts: list[dict[str, Any]],
    mailbox_id: str,
) -> tuple[
    dict[str, tuple[dict[str, Any], dict[str, Any]]],
    dict[str, tuple[str, str, str]],
]:
    """Build auth_payloads and label_lookup for accounts."""
    auth_payloads: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    label_lookup: dict[str, tuple[str, str, str]] = {}
    credentials_cache: dict[str, dict[str, Any]] = {}
    for account in accounts:
        account_id = str(account.get("account_id") or "")
        provider = str(account.get("provider") or "").lower()
        if not account_id or not provider:
            continue
        if provider not in credentials_cache:
            credentials_cache[provider] = load_wrapped_app_credentials(provider)
        account_label = f"{mailbox_id}__{account_id}"
        auth_payloads[account_label] = (
            credentials_cache[provider],
            load_wrapped_account_tokens(mailbox_id, account_id, provider),
        )
        label_lookup[account_label] = (mailbox_id, account_id, provider)
    return auth_payloads, label_lookup


def _raise_on_fetch_errors(errors: dict[str, Exception]) -> None:
    """Raise appropriate API errors from per-account fetch errors."""
    if not errors:
        return
    auth_labels = [label for label, error in errors.items() if is_auth_error(error)]
    if auth_labels:
        raise AccountNotConnected(
            "One or more accounts are not connected. Call /connect first.",
            {"account_labels": auth_labels},
        )
    reasons = {label: str(exc) for label, exc in errors.items() if str(exc)}
    detail: dict[str, Any] = {"account_labels": list(errors.keys())}
    if reasons:
        detail["reasons"] = reasons
    raise EmailFetchError(
        "Failed to fetch email metadata from one or more accounts.",
        detail,
    )


def sync_email_metadata(mailbox_id: str, user_id: str) -> SyncResultOut:
    """Fetch and persist email metadata for all accounts under a mailbox."""
    ensure_mailbox_access(mailbox_id, user_id)

    with catch_database_errors():
        accounts = account_store.list_by_mailbox(mailbox_id)

    auth_payloads, label_lookup = _build_auth_context(accounts, mailbox_id)

    manager = build_manager_for_accounts(accounts)

    updated_tokens = manager.authenticate_all_silent(auth_payloads)
    if updated_tokens:
        _persist_refreshed_tokens(updated_tokens, label_lookup)
    raise_on_silent_auth_errors(manager.get_last_errors())

    sync_cursors = load_sync_cursors(label_lookup)

    try:
        results = manager.fetch_all_email_metadata(sync_cursors)
    except CoreError as exc:
        raise translate_core_error(exc, fallback=EmailFetchError) from exc
    except Exception as exc:
        raise EmailFetchError("Failed to sync email metadata.") from exc

    _raise_on_fetch_errors(manager.get_last_errors())

    account_details: list[AccountSyncDetail] = []
    total_synced = 0

    for label, (metadata_list, new_cursor) in results.items():
        ids = label_lookup.get(label)
        if not ids:
            continue
        mid, aid, provider = ids

        for m in metadata_list:
            m.account_id = aid

        count = persist_email_metadata_batch(aid, metadata_list)
        update_sync_cursor(mid, aid, new_cursor)

        total_synced += count
        account_details.append(AccountSyncDetail(
            account_id=aid,
            provider=provider,
            emails_synced=count,
            sync_cursor=new_cursor,
        ))

    return SyncResultOut(total_synced=total_synced, accounts=account_details)


def send_email(mailbox_id: str, payload: EmailSendRequest, user_id: str) -> dict[str, str]:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        account = account_store.get(mailbox_id, payload.account_id)
    if account is None:
        raise AccountNotFound(f"Account '{payload.account_id}' not found.")

    provider = str(account.get("provider") or "").lower()
    manager = build_manager_for_accounts([account])
    account_label = f"{mailbox_id}__{payload.account_id}"
    app_credentials = load_wrapped_app_credentials(provider)
    user_tokens = load_wrapped_account_tokens(mailbox_id, payload.account_id, provider)
    auth_payloads = {account_label: (app_credentials, user_tokens)}
    label_lookup: dict[str, tuple[str, str, str]] = {
        account_label: (mailbox_id, payload.account_id, provider),
    }
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
    except CoreError as exc:
        raise translate_core_error(
            exc,
            fallback=EmailSendError,
            context={"account_id": payload.account_id, "account_label": account_label},
        ) from exc
    except Exception as exc:
        raise EmailSendError("Failed to send email.") from exc

    return {"status": "sent"}
