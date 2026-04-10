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
)
from api.schemas.draft import DraftCreate, DraftOut
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
) -> None:
    """Persist any refreshed tokens after a silent auth call during draft creation."""
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
            raise DraftCreationError(
                "Failed to persist refreshed tokens during draft creation."
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
