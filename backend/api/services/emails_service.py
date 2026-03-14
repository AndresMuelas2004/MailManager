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
from core.email.email_client import SyncResult
from core.email.email_manager import EmailManager
from api.services.services_helpers import (
    build_manager_for_accounts,
    delete_email_metadata_batch,
    ensure_mailbox_access,
    load_stored_message_ids,
    load_sync_cursors,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    persist_email_metadata_batch,
    raise_on_silent_auth_errors,
    translate_core_error,
    translate_database_error,
    unwrap_secret,
    update_email_metadata_labels_batch,
    update_sync_cursor,
)
from database import account_store, DatabaseError


def _reconcile_ghost_emails(
    manager: EmailManager,
    account_label: str,
    account_id: str,
    sync_result: SyncResult,
) -> tuple[int, list[str]]:
    """Best-effort: verify DB emails still exist at provider after bootstrap.
    Returns (deleted_count, ghost_ids). Skips on any error."""
    try:
        stored_ids = load_stored_message_ids(account_id)
    except Exception:
        logger.warning("Reconciliation skipped for %s: failed to load stored IDs.", account_id)
        return 0, []

    bootstrap_ids = {m.provider_message_id for m in sync_result.upserts}
    suspect_ids = [mid for mid in stored_ids if mid not in bootstrap_ids]
    if not suspect_ids:
        return 0, []

    try:
        still_exist = set(manager.verify_message_existence(account_label, suspect_ids))
    except Exception as exc:
        logger.warning(
            "Reconciliation skipped for %s: verification failed (%s): %s",
            account_id, type(exc).__name__, exc,
        )
        return 0, []

    ghost_ids = [mid for mid in suspect_ids if mid not in still_exist]
    if not ghost_ids:
        return 0, []

    deleted = delete_email_metadata_batch(account_id, ghost_ids)
    logger.info("Reconciliation for %s: %d suspect, %d ghosts deleted.", account_id, len(suspect_ids), deleted)
    return deleted, ghost_ids


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
        try:
            account_store.upsert_tokens(mailbox_id, account_id, provider, payload)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning("Unexpected token refresh persist error (%s): %s", type(exc).__name__, exc)
            raise ApiError("Failed to persist refreshed tokens.") from exc


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

    try:
        accounts = account_store.list_by_mailbox(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected account listing error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to list accounts.") from exc

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

            reconciled, ghost_ids = 0, []
            if sync_result.is_full_sync:
                reconciled, ghost_ids = _reconcile_ghost_emails(manager, label, aid, sync_result)

            count = upserted + deleted + label_updated + reconciled
            total_synced += count

            events: list[str] = []
            for meta in sync_result.upserts:
                events.append(
                    f"UPSERT  | id={meta.provider_message_id} | box={meta.box} | subject={meta.subject!r}"
                )
            for msg_id in sync_result.deletes:
                events.append(f"DELETE  | id={msg_id}")
            for lu in sync_result.label_updates:
                events.append(
                    f"LABEL   | id={lu.provider_message_id} | box={lu.box} | is_read={lu.is_read}"
                )
            for ghost_id in ghost_ids:
                events.append(f"GHOST   | id={ghost_id}")

            if events:
                logger.info("Sync events for account %s (%s) [%d events]:", aid, provider, len(events))
                for event in events:
                    logger.info("  %s", event)

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
    try:
        account = account_store.get(mailbox_id, payload.account_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected account lookup error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to look up account.") from exc
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
