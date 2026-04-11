"""
Service layer for draft operations.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from api.errors.exceptions import (
    AccountNotFound,
    ApiError,
    DraftCreationError,
    DraftListError,
    DraftSyncError,
)
from api.schemas.draft import DraftCreate, DraftOut, DraftsAccountSyncDetail, DraftsSyncResultOut
from api.services.services_helpers import (
    build_manager_for_accounts,
    ensure_mailbox_access,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    raise_on_silent_auth_errors,
    translate_core_error,
    translate_database_error,
    unwrap_secret,
)
from core.email import CoreError
from database import account_store, draft_store, DatabaseError


def _persist_refreshed_tokens(
    updated_tokens: dict[str, dict[str, Any]],
    label_lookup: dict[str, tuple[str, str, str]],
    *,
    fallback: type[ApiError] = DraftCreationError,
) -> None:
    """Persist any refreshed tokens after a silent auth call during draft operations."""
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
            logger.warning(
                "Unexpected draft token refresh persist error (%s): %s",
                type(exc).__name__, exc,
            )
            raise fallback(
                "Failed to persist refreshed tokens during draft operation."
            ) from exc


def create_draft(
    mailbox_id: str,
    account_id: str,
    payload: DraftCreate,
    user_id: str,
) -> DraftOut:
    """
    Create a draft at the provider and persist it locally.
    Provider-First: only persist if the provider call succeeds.
    """
    ensure_mailbox_access(mailbox_id, user_id)

    try:
        account = account_store.get(mailbox_id, account_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected account lookup error during draft creation (%s): %s",
            type(exc).__name__, exc,
        )
        raise DraftCreationError(
            "Failed to look up account while creating draft."
        ) from exc
    if account is None:
        raise AccountNotFound(
            f"Account '{account_id}' not found in mailbox '{mailbox_id}' "
            "during draft creation."
        )

    try:
        provider = str(account.get("provider") or "").lower()
        account_label = f"{mailbox_id}__{account_id}"
        manager = build_manager_for_accounts([account])

        app_credentials = load_wrapped_app_credentials(provider)
        user_tokens = load_wrapped_account_tokens(mailbox_id, account_id, provider)
        auth_payloads: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
            account_label: (app_credentials, user_tokens),
        }
        label_lookup: dict[str, tuple[str, str, str]] = {
            account_label: (mailbox_id, account_id, provider),
        }

        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup)
        raise_on_silent_auth_errors(
            manager.get_last_errors(), fallback=DraftCreationError,
        )

        try:
            draft_metadata = manager.create_draft(
                account_label,
                payload.to_recipients,
                payload.cc_recipients,
                payload.bcc_recipients,
                payload.subject,
                payload.body_html,
            )
        except CoreError as exc:
            raise translate_core_error(
                exc,
                fallback=DraftCreationError,
                context={"account_id": account_id, "account_label": account_label},
            ) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected error during provider draft creation (%s): %s",
                type(exc).__name__, exc,
            )
            raise DraftCreationError(
                "Unexpected failure while creating draft at provider."
            ) from exc

        row = {
            "provider_draft_id": draft_metadata.provider_draft_id,
            "account_id": account_id,
            "to_recipients": list(payload.to_recipients),
            "cc_recipients": list(payload.cc_recipients),
            "bcc_recipients": list(payload.bcc_recipients),
            "subject": payload.subject,
            "body_html": payload.body_html,
        }
        try:
            persisted = draft_store.create(row)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected draft DB persist error (%s): %s",
                type(exc).__name__, exc,
            )
            raise DraftCreationError(
                "Failed to persist draft to database after provider creation."
            ) from exc

        return DraftOut(
            provider_draft_id=persisted["provider_draft_id"],
            account_id=str(persisted["account_id"]),
            to_recipients=persisted.get("to_recipients") or [],
            cc_recipients=persisted.get("cc_recipients") or [],
            bcc_recipients=persisted.get("bcc_recipients") or [],
            subject=persisted.get("subject") or "",
            body_html=persisted.get("body_html") or "",
            created_at=persisted["created_at"],
            updated_at=persisted["updated_at"],
        )
    except ApiError:
        raise
    except Exception as exc:
        logger.warning(
            "Unexpected draft creation error (%s): %s",
            type(exc).__name__, exc,
        )
        raise DraftCreationError("Failed to create draft.") from exc


def list_drafts(
    mailbox_id: str,
    user_id: str,
    account_id: str | None = None,
) -> list[DraftOut]:
    """
    List drafts for a mailbox, optionally filtered to a single account.

    Pure DB read: does not contact any provider. Enforces mailbox ownership
    via ensure_mailbox_access.
    """
    ensure_mailbox_access(mailbox_id, user_id)

    if account_id is not None:
        try:
            account = account_store.get(mailbox_id, account_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected account lookup error during draft listing (%s): %s",
                type(exc).__name__, exc,
            )
            raise DraftListError(
                "Failed to look up account for draft listing."
            ) from exc
        if account is None:
            raise AccountNotFound(
                f"Account '{account_id}' not found in mailbox '{mailbox_id}' "
                "during draft listing."
            )

        try:
            rows = draft_store.list_by_account(account_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected draft listing error for account '%s' (%s): %s",
                account_id, type(exc).__name__, exc,
            )
            raise DraftListError(
                "Failed to list drafts for account."
            ) from exc
    else:
        try:
            rows = draft_store.list_by_mailbox(mailbox_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected draft listing error for mailbox '%s' (%s): %s",
                mailbox_id, type(exc).__name__, exc,
            )
            raise DraftListError(
                "Failed to list drafts for mailbox."
            ) from exc

    return [
        DraftOut(
            provider_draft_id=row["provider_draft_id"],
            account_id=str(row["account_id"]),
            to_recipients=row.get("to_recipients") or [],
            cc_recipients=row.get("cc_recipients") or [],
            bcc_recipients=row.get("bcc_recipients") or [],
            subject=row.get("subject") or "",
            body_html=row.get("body_html") or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _build_draft_auth_context(
    accounts: list[dict[str, Any]],
    mailbox_id: str,
) -> tuple[
    dict[str, tuple[dict[str, Any], dict[str, Any]]],
    dict[str, tuple[str, str, str]],
]:
    """Build (auth_payloads, label_lookup) for a batch of accounts.

    Generalizes the inline auth-context setup used by ``create_draft``
    so ``sync_drafts`` can apply it uniformly to both the single-account
    and the unified-mailbox branches.
    """
    auth_payloads: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    label_lookup: dict[str, tuple[str, str, str]] = {}
    for account in accounts:
        account_id_local = str(account.get("account_id") or "")
        provider = str(account.get("provider") or "").lower()
        label = f"{mailbox_id}__{account_id_local}"
        app_credentials = load_wrapped_app_credentials(provider)
        user_tokens = load_wrapped_account_tokens(mailbox_id, account_id_local, provider)
        auth_payloads[label] = (app_credentials, user_tokens)
        label_lookup[label] = (mailbox_id, account_id_local, provider)
    return auth_payloads, label_lookup


def sync_drafts(
    mailbox_id: str,
    user_id: str,
    account_id: str | None = None,
) -> DraftsSyncResultOut:
    """
    Load drafts from the provider(s) into the local drafts table.

    If account_id is None, syncs every account in the mailbox; otherwise
    only that specific account. Ownership enforced via ensure_mailbox_access.
    Per account, the full provider draft list replaces the local rows
    atomically (upsert + delete-missing). Both providers cap the fetch
    at _DRAFTS_MAX_TOTAL = 100 drafts per account.
    """
    ensure_mailbox_access(mailbox_id, user_id)

    # Step 1: load accounts (single or full mailbox)
    if account_id is not None:
        try:
            account = account_store.get(mailbox_id, account_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected account lookup error during draft sync (%s): %s",
                type(exc).__name__, exc,
            )
            raise DraftSyncError(
                "Failed to look up account for draft sync."
            ) from exc
        if account is None:
            raise AccountNotFound(
                f"Account '{account_id}' not found in mailbox '{mailbox_id}' "
                "during draft sync."
            )
        accounts = [account]
    else:
        try:
            accounts = account_store.list_by_mailbox(mailbox_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected account list error during draft sync (%s): %s",
                type(exc).__name__, exc,
            )
            raise DraftSyncError(
                "Failed to list accounts for draft sync."
            ) from exc

    if not accounts:
        return DraftsSyncResultOut(total_synced=0, accounts=[])

    # Step 2: build manager + silent auth
    try:
        auth_payloads, label_lookup = _build_draft_auth_context(accounts, mailbox_id)
        manager = build_manager_for_accounts(accounts)
        updated_tokens = manager.authenticate_all_silent(auth_payloads)
        if updated_tokens:
            _persist_refreshed_tokens(updated_tokens, label_lookup, fallback=DraftSyncError)
        raise_on_silent_auth_errors(
            manager.get_last_errors(), fallback=DraftSyncError,
        )
    except ApiError:
        raise
    except Exception as exc:
        logger.warning(
            "Unexpected error during draft sync setup (%s): %s",
            type(exc).__name__, exc,
        )
        raise DraftSyncError(
            "Failed to prepare draft sync context."
        ) from exc

    # Step 3: fetch drafts from all clients
    try:
        fetch_results = manager.fetch_all_drafts()
    except CoreError as exc:
        raise translate_core_error(
            exc, fallback=DraftSyncError,
        ) from exc
    except Exception as exc:
        logger.warning(
            "Unexpected fetch_all_drafts error (%s): %s",
            type(exc).__name__, exc,
        )
        raise DraftSyncError(
            "Failed to fetch drafts from providers."
        ) from exc

    # Step 4: surface per-account errors captured by the manager
    raise_on_silent_auth_errors(
        manager.get_last_errors(), fallback=DraftSyncError,
    )

    # Step 5: persist per account (atomic replace)
    account_details: list[DraftsAccountSyncDetail] = []
    total_synced = 0
    for label, drafts in fetch_results.items():
        ids = label_lookup.get(label)
        if not ids:
            continue
        _, account_id_inner, provider = ids
        rows = [
            {
                "provider_draft_id": d.provider_draft_id,
                "to_recipients": list(d.to_recipients),
                "cc_recipients": list(d.cc_recipients),
                "bcc_recipients": list(d.bcc_recipients),
                "subject": d.subject,
                "body_html": d.body_html,
                "created_at": d.created_at,
                "updated_at": d.updated_at,
            }
            for d in drafts
        ]
        try:
            synced_count = draft_store.replace_all_for_account(account_id_inner, rows)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning(
                "Unexpected persist error during draft sync for account '%s' (%s): %s",
                account_id_inner, type(exc).__name__, exc,
            )
            raise DraftSyncError(
                "Failed to persist drafts during sync."
            ) from exc

        total_synced += synced_count
        account_details.append(DraftsAccountSyncDetail(
            account_id=account_id_inner,
            provider=provider,
            drafts_synced=synced_count,
        ))

    return DraftsSyncResultOut(
        total_synced=total_synced,
        accounts=account_details,
    )
