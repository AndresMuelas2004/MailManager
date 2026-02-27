"""
Service layer for account operations.
"""

from __future__ import annotations

from uuid import uuid4

from api.errors.exceptions import (
    AccountNotFound,
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
    catch_database_errors,
    ensure_mailbox_access,
    load_wrapped_app_credentials,
    translate_connect_error,
    unwrap_secret,
)
from database import account_store


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


def list_accounts(mailbox_id: str, user_id: str) -> list[AccountOut]:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        accounts = account_store.list_by_mailbox(mailbox_id)
    return [_build_response(account) for account in accounts]


def create_account(mailbox_id: str, payload: AccountCreate, user_id: str) -> AccountOut:
    ensure_mailbox_access(mailbox_id, user_id)
    account_id = str(uuid4())
    record = {
        "account_id": account_id,
        "mailbox_id": mailbox_id,
        "provider": payload.provider,
        "display_label": payload.display_label,
        "config": payload.config,
    }
    with catch_database_errors():
        created = account_store.upsert(record)
    return _build_response(created)


def get_account(mailbox_id: str, account_id: str, user_id: str) -> AccountOut:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")
    return _build_response(record)


def update_account(mailbox_id: str, account_id: str, payload: AccountUpdate, user_id: str) -> AccountOut:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")

    if payload.display_label is not None:
        record["display_label"] = payload.display_label
    if payload.config is not None:
        record["config"] = payload.config

    with catch_database_errors():
        updated = account_store.upsert(record)
    return _build_response(updated)


def delete_account(mailbox_id: str, account_id: str, user_id: str) -> dict[str, str]:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")
    # ON DELETE CASCADE removes associated tokens automatically.
    with catch_database_errors():
        account_store.delete(mailbox_id, account_id)
    return {"status": "deleted"}


def connect_account(mailbox_id: str, account_id: str, user_id: str) -> AccountConnectResponse:
    ensure_mailbox_access(mailbox_id, user_id)
    with catch_database_errors():
        record = account_store.get(mailbox_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")

    provider = str(record.get("provider") or "").lower()
    account_label = f"{mailbox_id}__{account_id}"
    manager = build_manager_for_accounts([record])
    app_credentials = load_wrapped_app_credentials(provider)

    connect_context = {
        "account_id": account_id,
        "provider": record.get("provider"),
        "account_label": account_label,
    }
    try:
        wrapped_tokens = manager.connect_account(account_label, app_credentials)
    except CoreError as exc:
        raise translate_connect_error(exc, context=connect_context) from exc

    token_payload = dict(wrapped_tokens or {})
    token_payload["access_token"] = unwrap_secret(token_payload.get("access_token"))
    token_payload["refresh_token"] = unwrap_secret(token_payload.get("refresh_token"))
    with catch_database_errors():
        account_store.upsert_tokens(mailbox_id, account_id, provider, token_payload)

    return AccountConnectResponse(
        connected=True,
        provider=record.get("provider", ""),
        account_id=account_id,
        account_label=account_label,
        message="Account connected successfully.",
    )
