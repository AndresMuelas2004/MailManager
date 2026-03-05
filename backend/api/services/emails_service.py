"""
Service layer for email operations.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from api.errors.exceptions import (
    AccountNotFound,
    ApiError,
    EmailFetchError,
    EmailSendError,
)
from core.email import CoreError
from api.schemas.email import AccountSyncDetail, EmailSendRequest, SyncResultOut
from api.services.services_helpers import (
    build_manager_for_accounts,
    catch_database_errors,
    delete_email_metadata_batch,
    ensure_mailbox_access,
    load_sync_cursors,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    persist_email_metadata_batch,
    raise_on_silent_auth_errors,
    translate_core_error,
    unwrap_secret,
    update_email_metadata_labels_batch,
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


def sync_email_metadata(mailbox_id: str, user_id: str) -> SyncResultOut:
    """Fetch and persist email metadata for all accounts under a mailbox."""
    ensure_mailbox_access(mailbox_id, user_id)

    with catch_database_errors():
        accounts = account_store.list_by_mailbox(mailbox_id)

    try:
        auth_payloads, label_lookup = _build_auth_context(accounts, mailbox_id)

        manager = build_manager_for_accounts(accounts)

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=EmailFetchError)

        sync_cursors = load_sync_cursors(label_lookup)

        try:
            results = manager.fetch_all_email_metadata(sync_cursors)
        except CoreError as exc:
            raise translate_core_error(exc, fallback=EmailFetchError) from exc

        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=EmailFetchError)

        account_details: list[AccountSyncDetail] = []
        total_synced = 0

        for label, sync_result in results.items():
            ids = label_lookup.get(label)
            if not ids:
                continue
            mid, aid, provider = ids

            upserted = persist_email_metadata_batch(aid, sync_result.upserts)
            deleted = delete_email_metadata_batch(aid, sync_result.deletes)
            label_updated = update_email_metadata_labels_batch(aid, sync_result.label_updates)
            update_sync_cursor(mid, aid, sync_result.new_cursor)

            count = upserted + deleted + label_updated
            total_synced += count
            account_details.append(AccountSyncDetail(
                account_id=aid,
                provider=provider,
                emails_synced=count,
                sync_cursor=sync_result.new_cursor,
            ))

        return SyncResultOut(total_synced=total_synced, accounts=account_details)
    except ApiError:
        raise
    except Exception as exc:
        logger.warning("Unexpected sync error (%s): %s", type(exc).__name__, exc)
        raise EmailFetchError("Failed to sync email metadata.") from exc


def send_email(mailbox_id: str, payload: EmailSendRequest, user_id: str) -> dict[str, str]:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        account = account_store.get(mailbox_id, payload.account_id)
    if account is None:
        raise AccountNotFound(f"Account '{payload.account_id}' not found.")

    try:
        auth_payloads, label_lookup = _build_auth_context([account], mailbox_id)
        manager = build_manager_for_accounts([account])
        account_label = f"{mailbox_id}__{payload.account_id}"

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=EmailSendError)

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

        return {"status": "sent"}
    except ApiError:
        raise
    except Exception as exc:
        logger.warning("Unexpected send error (%s): %s", type(exc).__name__, exc)
        raise EmailSendError("Failed to send email.") from exc
