"""
Service layer for account operations.
"""

from __future__ import annotations

from uuid import uuid4

from api.errors.exceptions import (
    AccountNotFound,
    ProviderAuthError,
)
from core.email.errors import CoreError
from api.schemas.account import (
    AccountConnectResponse,
    AccountCreate,
    AccountOut,
    AccountUpdate,
)
from api.services.services_helpers import (
    build_manager_for_accounts,
    ensure_mailbox_exists,
    load_wrapped_app_credentials,
    translate_core_error,
    unwrap_secret,
)
from api.storage.token_store import delete_account_tokens_for_records, save_account_tokens
from api.storage.json_store import account_store, now_iso


def _resolve_display_label(record: dict) -> str:
    display_label = record.get("display_label") or record.get("label")
    if display_label:
        return str(display_label)
    provider = record.get("provider", "account")
    account_id = record.get("account_id", "unknown")
    return f"{provider}:{account_id}"


def _build_response(record: dict) -> AccountOut:
    payload = dict(record)
    payload["display_label"] = _resolve_display_label(record)
    return AccountOut(**payload)


def list_accounts(mailbox_id: str) -> list[AccountOut]:
    ensure_mailbox_exists(mailbox_id)
    accounts = account_store.list_by_mailbox(mailbox_id)
    return [_build_response(account) for account in accounts]


def create_account(mailbox_id: str, payload: AccountCreate) -> AccountOut:
    ensure_mailbox_exists(mailbox_id)
    account_id = str(uuid4())
    record = {
        "account_id": account_id,
        "mailbox_id": mailbox_id,
        "provider": payload.provider,
        "display_label": payload.display_label,
        "config": payload.config,
        "created_at": now_iso(),
    }
    created = account_store.upsert(record)
    return _build_response(created)


def get_account(mailbox_id: str, account_id: str) -> AccountOut:
    ensure_mailbox_exists(mailbox_id)
    record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")
    return _build_response(record)


def update_account(mailbox_id: str, account_id: str, payload: AccountUpdate) -> AccountOut:
    ensure_mailbox_exists(mailbox_id)
    record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")

    if payload.display_label is not None:
        record["display_label"] = payload.display_label
    if payload.config is not None:
        record["config"] = payload.config

    updated = account_store.upsert(record)
    return _build_response(updated)


def delete_account(mailbox_id: str, account_id: str) -> dict[str, str]:
    ensure_mailbox_exists(mailbox_id)
    record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")
    # Best-effort cleanup of provider tokens before removing the account record.
    delete_account_tokens_for_records([record])
    account_store.delete(mailbox_id, account_id)
    return {"status": "deleted"}


def connect_account(mailbox_id: str, account_id: str) -> AccountConnectResponse:
    ensure_mailbox_exists(mailbox_id)
    record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")

    account_label = f"{mailbox_id}__{account_id}"
    manager = build_manager_for_accounts([record])
    app_credentials = load_wrapped_app_credentials()

    connect_context = {
        "account_id": account_id,
        "provider": record.get("provider"),
        "account_label": account_label,
    }
    try:
        wrapped_tokens = manager.connect_account(account_label, app_credentials)
    except CoreError as exc:
        raise translate_core_error(
            exc, fallback=ProviderAuthError, context=connect_context,
        ) from exc
    except Exception as exc:
        raise ProviderAuthError(
            "Failed to authenticate provider client.",
            connect_context,
        ) from exc

    token_payload = dict(wrapped_tokens or {})
    token_payload["access_token"] = unwrap_secret(token_payload.get("access_token"))
    token_payload["refresh_token"] = unwrap_secret(token_payload.get("refresh_token"))
    save_account_tokens(mailbox_id, account_id, token_payload)

    return AccountConnectResponse(
        connected=True,
        provider=record.get("provider", ""),
        account_id=account_id,
        account_label=account_label,
        message="Account connected successfully.",
    )
