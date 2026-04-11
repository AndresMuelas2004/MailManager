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
    EmailContentFetchError,
    EmailFetchError,
    EmailListError,
    EmailNotInTrash,
    EmailSendError,
    MoveToTrashError,
    ReadStatusUpdateError,
    SpamMoveError,
    SpamRestoreError,
    TrashOperationError,
)
from core.email import CoreError
from api.schemas.email import (
    AccountReadStatusDetail,
    AccountSpamDetail,
    AccountSyncDetail,
    EmailContentOut,
    EmailMetadataOut,
    EmailSendRequest,
    MoveToTrashRequest,
    MoveToTrashResult,
    ReadStatusRequest,
    ReadStatusResponse,
    SpamRequest,
    SpamResponse,
    SyncResultOut,
    TrashActionRequest,
    TrashActionResult,
)
from core.email.email_client import SyncResult
from core.email.email_manager import EmailManager
from api.services.services_helpers import (
    build_manager_for_accounts,
    delete_email_metadata_batch,
    ensure_mailbox_access,
    get_email_content,
    get_trash_emails_by_ids,
    load_stored_message_ids,
    load_sync_cursors,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    mark_as_deleted_batch,
    move_to_trash_batch,
    persist_email_content,
    persist_email_metadata_batch,
    raise_on_silent_auth_errors,
    restore_from_trash_batch,
    restore_from_trash_discovered_batch,
    sanitize_email_html,
    translate_core_error,
    translate_database_error,
    unwrap_secret,
    update_email_metadata_labels_batch,
    update_email_read_status_batch,
    update_email_spam_status_batch,
    update_sync_cursor,
)
from database import account_store, email_metadata_store, DatabaseError


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
    except Exception as exc:
        logger.warning(
            "Reconciliation skipped for %s: failed to load stored IDs (%s): %s",
            account_id, type(exc).__name__, exc,
        )
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

    try:
        deleted = delete_email_metadata_batch(account_id, ghost_ids)
    except Exception as exc:
        logger.warning(
            "Reconciliation skipped for %s: failed to delete ghosts (%s): %s",
            account_id, type(exc).__name__, exc,
        )
        return 0, []
    logger.info("Reconciliation for %s: %d suspect, %d ghosts deleted.", account_id, len(suspect_ids), deleted)
    return deleted, ghost_ids


def _persist_refreshed_tokens(
    updated_tokens: dict[str, dict[str, Any]],
    label_lookup: dict[str, tuple[str, str, str]],
    *,
    fallback: type[ApiError] = ApiError,
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
            raise fallback("Failed to persist refreshed tokens.") from exc


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


def sync_email_metadata(
    mailbox_id: str,
    user_id: str,
    account_id: str | None = None,
) -> SyncResultOut:
    """Fetch and persist email metadata for a mailbox, or a single account if specified."""
    ensure_mailbox_access(mailbox_id, user_id)

    if account_id is not None:
        try:
            account = account_store.get(mailbox_id, account_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected account lookup error during metadata sync (%s): %s",
                type(exc).__name__, exc,
            )
            raise EmailFetchError(
                "Failed to look up account for metadata sync."
            ) from exc
        if account is None:
            raise AccountNotFound(
                f"Account '{account_id}' not found in mailbox '{mailbox_id}' "
                "during metadata sync."
            )
        accounts = [account]
    else:
        try:
            accounts = account_store.list_by_mailbox(mailbox_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning("Unexpected account listing error during sync (%s): %s", type(exc).__name__, exc)
            raise EmailFetchError("Failed to list accounts for metadata sync.") from exc

    try:
        auth_payloads, label_lookup = _build_auth_context(accounts, mailbox_id)

        manager = build_manager_for_accounts(accounts)

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=EmailFetchError)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=EmailFetchError)

        sync_cursors = load_sync_cursors(label_lookup, fallback=EmailFetchError)

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

            upserted = persist_email_metadata_batch(aid, sync_result.upserts, fallback=EmailFetchError)
            deleted = delete_email_metadata_batch(aid, sync_result.deletes, fallback=EmailFetchError)
            label_updated = update_email_metadata_labels_batch(aid, sync_result.label_updates, fallback=EmailFetchError)
            update_sync_cursor(mid, aid, sync_result.new_cursor, fallback=EmailFetchError)

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
        raise EmailSendError("Failed to look up account for email send.") from exc
    if account is None:
        raise AccountNotFound(f"Account '{payload.account_id}' not found.")

    try:
        auth_payloads, label_lookup = _build_auth_context([account], mailbox_id)
        manager = build_manager_for_accounts([account])
        account_label = f"{mailbox_id}__{payload.account_id}"

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=EmailSendError)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=EmailSendError)

        try:
            sent_metadata = manager.send_email_from_account(
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

        # Best-effort: email already sent, don't fail the response on metadata persist failure
        try:
            persist_email_metadata_batch(payload.account_id, [sent_metadata], fallback=EmailSendError)
        except Exception as exc:
            logger.warning(
                "Email sent but metadata persistence failed for account '%s' (%s): %s",
                payload.account_id, type(exc).__name__, exc,
            )

        return {"status": "sent"}
    except ApiError:
        raise
    except Exception as exc:
        logger.warning("Unexpected send error (%s): %s", type(exc).__name__, exc)
        raise EmailSendError("Failed to send email.") from exc


def manage_trash(mailbox_id: str, payload: TrashActionRequest, user_id: str) -> TrashActionResult:
    """Delete permanently or restore emails from trash."""
    ensure_mailbox_access(mailbox_id, user_id)

    try:
        accounts = account_store.list_by_mailbox(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected account listing error during trash operation (%s): %s", type(exc).__name__, exc)
        raise TrashOperationError("Failed to list accounts for trash operation.") from exc

    account_ids_in_mailbox = {str(a.get("account_id") or "") for a in accounts}

    # Group message IDs by account_id
    msg_ids_by_account: dict[str, list[str]] = {}
    for item in payload.items:
        if item.account_id not in account_ids_in_mailbox:
            raise AccountNotFound(
                f"Account '{item.account_id}' not found in mailbox '{mailbox_id}'."
            )
        msg_ids_by_account.setdefault(item.account_id, []).append(item.provider_message_id)

    # Verify all emails are in TRASH and collect trash data
    trash_data_by_account: dict[str, dict[str, str | None]] = {}
    for account_id, msg_ids in msg_ids_by_account.items():
        trash_rows = get_trash_emails_by_ids(account_id, msg_ids, fallback=TrashOperationError)
        found_ids = {str(r["provider_message_id"]) for r in trash_rows}
        missing = [mid for mid in msg_ids if mid not in found_ids]
        if missing:
            raise EmailNotInTrash(
                f"Emails not in trash for account '{account_id}': {missing}.",
                {"account_id": account_id, "missing_ids": missing},
            )
        trash_data_by_account[account_id] = {
            str(r["provider_message_id"]): r.get("previous_box")
            for r in trash_rows
        }

    # Build auth context only for referenced accounts
    referenced_accounts = [a for a in accounts if str(a.get("account_id") or "") in msg_ids_by_account]

    try:
        auth_payloads, label_lookup = _build_auth_context(referenced_accounts, mailbox_id)
        manager = build_manager_for_accounts(referenced_accounts)

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=TrashOperationError)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=TrashOperationError)

        total_affected = 0
        for account_id, msg_ids in msg_ids_by_account.items():
            account_label = f"{mailbox_id}__{account_id}"

            if payload.action == "delete":
                succeeded = manager.delete_messages(account_label, msg_ids)
                mark_as_deleted_batch(account_id, succeeded, fallback=TrashOperationError)
                total_affected += len(succeeded)
            else:  # restore
                trash_data = trash_data_by_account[account_id]
                provider_items = {mid: trash_data.get(mid) for mid in msg_ids}

                id_mapping = manager.restore_from_trash(account_label, provider_items)

                # Split: known previous_box vs NULL (needs discovery)
                known_rows: list[tuple] = []
                null_old_to_new: dict[str, str] = {}
                for old, new in id_mapping.items():
                    if trash_data.get(old):
                        known_rows.append((old, new, account_id))
                    else:
                        null_old_to_new[old] = new

                if known_rows:
                    restore_from_trash_batch(account_id, known_rows, fallback=TrashOperationError)

                if null_old_to_new:
                    new_ids = list(null_old_to_new.values())
                    metadata_list = manager.fetch_messages_metadata(account_label, new_ids)
                    box_map = {m.provider_message_id: m.box for m in metadata_list}
                    discovered_rows = [
                        (old, new, account_id, box_map.get(new, "ALL_MAIL"))
                        for old, new in null_old_to_new.items()
                    ]
                    restore_from_trash_discovered_batch(account_id, discovered_rows, fallback=TrashOperationError)

                total_affected += len(id_mapping)

        return TrashActionResult(affected=total_affected)
    except ApiError:
        raise
    except CoreError as exc:
        raise translate_core_error(exc, fallback=TrashOperationError) from exc
    except Exception as exc:
        logger.warning("Unexpected trash operation error (%s): %s", type(exc).__name__, exc)
        raise TrashOperationError("Failed to manage trash operation.") from exc


def move_to_trash(mailbox_id: str, payload: MoveToTrashRequest, user_id: str) -> MoveToTrashResult:
    """Move emails to trash (provider-first, then update DB)."""
    ensure_mailbox_access(mailbox_id, user_id)

    try:
        accounts = account_store.list_by_mailbox(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected account listing error during move-to-trash (%s): %s", type(exc).__name__, exc)
        raise MoveToTrashError("Failed to list accounts for move-to-trash operation.") from exc

    account_ids_in_mailbox = {str(a.get("account_id") or "") for a in accounts}

    items_by_account: dict[str, list[str]] = {}
    for item in payload.items:
        if item.account_id not in account_ids_in_mailbox:
            raise AccountNotFound(
                f"Account '{item.account_id}' not found in mailbox '{mailbox_id}'."
            )
        items_by_account.setdefault(item.account_id, []).append(item.provider_message_id)

    referenced_accounts = [a for a in accounts if str(a.get("account_id") or "") in items_by_account]

    try:
        auth_payloads, label_lookup = _build_auth_context(referenced_accounts, mailbox_id)
        manager = build_manager_for_accounts(referenced_accounts)

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=MoveToTrashError)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=MoveToTrashError)

        total_affected = 0
        for account_id, msg_ids in items_by_account.items():
            account_label = f"{mailbox_id}__{account_id}"
            id_mapping = manager.move_to_trash(account_label, msg_ids)
            if id_mapping:
                rows = [(old, new, account_id) for old, new in id_mapping.items()]
                affected = move_to_trash_batch(account_id, rows, fallback=MoveToTrashError)
                total_affected += affected

        return MoveToTrashResult(affected=total_affected)
    except ApiError:
        raise
    except CoreError as exc:
        raise translate_core_error(exc, fallback=MoveToTrashError) from exc
    except Exception as exc:
        logger.warning("Unexpected move-to-trash error (%s): %s", type(exc).__name__, exc)
        raise MoveToTrashError("Failed to move emails to trash.") from exc


def update_read_status(
    mailbox_id: str,
    payload: ReadStatusRequest,
    user_id: str,
) -> ReadStatusResponse:
    """Mark messages as read/unread across accounts in a mailbox."""
    ensure_mailbox_access(mailbox_id, user_id)

    items_by_account: dict[str, list[str]] = {}
    for item in payload.items:
        items_by_account.setdefault(item.account_id, []).append(item.provider_message_id)

    try:
        accounts = account_store.list_by_mailbox(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected account listing error (%s): %s",
            type(exc).__name__, exc,
        )
        raise ReadStatusUpdateError(
            "Failed to list accounts for read status update."
        ) from exc

    account_map = {str(a["account_id"]): a for a in accounts}
    for aid in items_by_account:
        if aid not in account_map:
            raise AccountNotFound(
                f"Account '{aid}' not found in mailbox '{mailbox_id}' "
                "during read status update."
            )

    referenced_accounts = [account_map[aid] for aid in items_by_account]

    try:
        auth_payloads, label_lookup = _build_auth_context(
            referenced_accounts, mailbox_id,
        )
        manager = build_manager_for_accounts(referenced_accounts)

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=ReadStatusUpdateError)
        raise_on_silent_auth_errors(
            manager.get_last_errors(), fallback=ReadStatusUpdateError,
        )

        account_details: list[AccountReadStatusDetail] = []
        total_updated = 0

        for aid, message_ids in items_by_account.items():
            account_label = f"{mailbox_id}__{aid}"

            try:
                updated_ids = manager.update_read_status(
                    account_label, message_ids, payload.is_read,
                )
            except CoreError as exc:
                raise translate_core_error(
                    exc, fallback=ReadStatusUpdateError,
                    context={"account_id": aid, "account_label": account_label},
                ) from exc

            if updated_ids:
                update_email_read_status_batch(aid, updated_ids, payload.is_read, fallback=ReadStatusUpdateError)

            account_details.append(AccountReadStatusDetail(
                account_id=aid,
                updated=len(updated_ids),
            ))
            total_updated += len(updated_ids)

        return ReadStatusResponse(
            updated_count=total_updated,
            accounts=account_details,
        )
    except ApiError:
        raise
    except Exception as exc:
        logger.warning(
            "Unexpected read status update error (%s): %s",
            type(exc).__name__, exc,
        )
        raise ReadStatusUpdateError(
            "Failed to update email read status."
        ) from exc


def move_to_spam(
    mailbox_id: str,
    payload: SpamRequest,
    user_id: str,
) -> SpamResponse:
    """Move emails to spam across accounts in a mailbox."""
    return _execute_spam_operation(
        mailbox_id, payload, user_id,
        manager_method="move_to_spam",
        target_box="SPAM",
        fallback_error=SpamMoveError,
        operation_label="spam move",
    )


def restore_from_spam(
    mailbox_id: str,
    payload: SpamRequest,
    user_id: str,
) -> SpamResponse:
    """Restore emails from spam across accounts in a mailbox."""
    return _execute_spam_operation(
        mailbox_id, payload, user_id,
        manager_method="restore_from_spam",
        target_box="ALL_MAIL",
        fallback_error=SpamRestoreError,
        operation_label="spam restore",
    )


def _execute_spam_operation(
    mailbox_id: str,
    payload: SpamRequest,
    user_id: str,
    *,
    manager_method: str,
    target_box: str,
    fallback_error: type[ApiError],
    operation_label: str,
) -> SpamResponse:
    """Shared implementation for move-to-spam and restore-from-spam."""
    ensure_mailbox_access(mailbox_id, user_id)

    items_by_account: dict[str, list[str]] = {}
    for item in payload.items:
        items_by_account.setdefault(item.account_id, []).append(item.provider_message_id)

    try:
        accounts = account_store.list_by_mailbox(mailbox_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected account listing error (%s): %s",
            type(exc).__name__, exc,
        )
        raise fallback_error("Failed to list accounts during spam operation.") from exc

    account_map = {str(a["account_id"]): a for a in accounts}
    for aid in items_by_account:
        if aid not in account_map:
            raise AccountNotFound(
                f"Account '{aid}' not found in mailbox '{mailbox_id}' "
                f"during {operation_label}."
            )

    referenced_accounts = [account_map[aid] for aid in items_by_account]

    try:
        auth_payloads, label_lookup = _build_auth_context(
            referenced_accounts, mailbox_id,
        )
        manager = build_manager_for_accounts(referenced_accounts)

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=fallback_error)
        raise_on_silent_auth_errors(
            manager.get_last_errors(), fallback=fallback_error,
        )

        account_details: list[AccountSpamDetail] = []
        total_moved = 0

        for aid, message_ids in items_by_account.items():
            account_label = f"{mailbox_id}__{aid}"

            try:
                results = getattr(manager, manager_method)(account_label, message_ids)
            except CoreError as exc:
                raise translate_core_error(
                    exc, fallback=fallback_error,
                    context={"account_id": aid, "account_label": account_label},
                ) from exc

            if results:
                update_email_spam_status_batch(aid, results, target_box, fallback=fallback_error)

            account_details.append(AccountSpamDetail(
                account_id=aid,
                moved=len(results),
            ))
            total_moved += len(results)

        return SpamResponse(
            moved_count=total_moved,
            accounts=account_details,
        )
    except ApiError:
        raise
    except Exception as exc:
        logger.warning(
            "Unexpected %s error (%s): %s",
            operation_label, type(exc).__name__, exc,
        )
        raise fallback_error(f"Failed to execute {operation_label}.") from exc


def list_emails(
    mailbox_id: str,
    box: str,
    user_id: str,
    account_id: str | None = None,
) -> list[EmailMetadataOut]:
    """List email metadata for a mailbox, optionally filtered to a single account."""
    ensure_mailbox_access(mailbox_id, user_id)

    if account_id is not None:
        try:
            account = account_store.get(mailbox_id, account_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected account lookup error during email listing (%s): %s",
                type(exc).__name__, exc,
            )
            raise EmailListError(
                "Failed to look up account for email listing."
            ) from exc
        if account is None:
            raise AccountNotFound(
                f"Account '{account_id}' not found in mailbox '{mailbox_id}' "
                "during email listing."
            )

        try:
            rows = email_metadata_store.list_by_account_and_box(account_id, box)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected email metadata listing error for account '%s' (%s): %s",
                account_id, type(exc).__name__, exc,
            )
            raise EmailListError(
                "Failed to list email metadata for account."
            ) from exc
    else:
        try:
            rows = email_metadata_store.list_by_mailbox_and_box(mailbox_id, box)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected email metadata listing error for mailbox '%s' (%s): %s",
                mailbox_id, type(exc).__name__, exc,
            )
            raise EmailListError(
                "Failed to list email metadata for mailbox."
            ) from exc

    return [
        EmailMetadataOut(
            provider_message_id=row["provider_message_id"],
            account_id=str(row["account_id"]),
            thread_id=row.get("thread_id"),
            from_email=row["from_email"],
            from_name=row.get("from_name"),
            subject=row.get("subject"),
            received_at=row["received_at"],
            is_read=row["is_read"],
            box=row["box"],
        )
        for row in rows
    ]


def get_email_full_content(
    mailbox_id: str,
    provider_message_id: str,
    account_id: str,
    user_id: str,
) -> EmailContentOut:
    """Return full email body, fetching from provider on cache miss."""
    ensure_mailbox_access(mailbox_id, user_id)

    try:
        account = account_store.get(mailbox_id, account_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected account lookup error during content fetch (%s): %s",
            type(exc).__name__, exc,
        )
        raise EmailContentFetchError(
            "Failed to look up account for email content fetch."
        ) from exc
    if account is None:
        raise AccountNotFound(
            f"Account '{account_id}' not found in mailbox '{mailbox_id}' "
            "during email content fetch."
        )

    row = get_email_content(account_id, provider_message_id, fallback=EmailContentFetchError)
    if row is not None:
        return EmailContentOut(html_body=row["html_body"], text_body=row["text_body"])

    try:
        auth_payloads, label_lookup = _build_auth_context([account], mailbox_id)
        manager = build_manager_for_accounts([account])
        account_label = f"{mailbox_id}__{account_id}"

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=EmailContentFetchError)
        raise_on_silent_auth_errors(manager.get_last_errors(), fallback=EmailContentFetchError)

        try:
            content = manager.fetch_email_content(account_label, provider_message_id)
        except CoreError as exc:
            raise translate_core_error(exc, fallback=EmailContentFetchError) from exc

        sanitized_html = sanitize_email_html(content.html_body) if content.html_body else None

        try:
            persist_email_content(account_id, provider_message_id, sanitized_html, content.text_body, fallback=EmailContentFetchError)
        except Exception as exc:
            logger.warning(
                "Content fetched but DB persist failed for account '%s' (%s): %s",
                account_id, type(exc).__name__, exc,
            )

        return EmailContentOut(html_body=sanitized_html, text_body=content.text_body)
    except ApiError:
        raise
    except Exception as exc:
        logger.warning(
            "Unexpected email content fetch error (%s): %s",
            type(exc).__name__, exc,
        )
        raise EmailContentFetchError("Failed to fetch email content.") from exc
