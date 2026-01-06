"""
Account router for provider-agnostic account management.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from api.errors.exceptions import AccountNotFound, ProviderAuthError, UserNotFound
from api.schemas.account import (
    AccountConnectResponse,
    AccountCreate,
    AccountOut,
    AccountUpdate,
)
from api.services.account_factory import build_client_label, create_client
from api.services.manager_registry import invalidate
from api.storage.json_store import account_store, now_iso, user_store


router = APIRouter(prefix="/users/{user_id}/accounts", tags=["accounts"])


def _ensure_user(user_id: str) -> None:
    if user_store.get(user_id) is None:
        raise UserNotFound(f"User '{user_id}' not found.")


def _resolve_display_label(record: dict) -> str:
    """
    Resolve the human-friendly label for API responses.
    """
    display_label = record.get("display_label") or record.get("label")
    if display_label:
        return str(display_label)
    provider = record.get("provider", "account")
    account_id = record.get("account_id", "unknown")
    return f"{provider}:{account_id}"


def _build_response(record: dict) -> AccountOut:
    """
    Normalize legacy storage fields and return a response model.
    """
    payload = dict(record)
    payload["display_label"] = _resolve_display_label(record)
    return AccountOut(**payload)


@router.get("", response_model=list[AccountOut])
def list_accounts(user_id: str) -> list[AccountOut]:
    """
    List all accounts for a user.
    """
    _ensure_user(user_id)
    accounts = account_store.list_by_user(user_id)
    return [_build_response(account) for account in accounts]


@router.post("", response_model=AccountOut)
def create_account(user_id: str, payload: AccountCreate) -> AccountOut:
    """
    Create a new account for the user.
    """
    _ensure_user(user_id)
    account_id = str(uuid4())
    display_label = payload.display_label or f"{payload.provider}:{account_id}"
    record = {
        "account_id": account_id,
        "user_id": user_id,
        "provider": payload.provider,
        "display_label": display_label,
        "config": payload.config,
        "created_at": now_iso(),
    }
    created = account_store.upsert(record)
    invalidate(user_id)
    return _build_response(created)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(user_id: str, account_id: str) -> AccountOut:
    """
    Fetch a single account by identifier.
    """
    _ensure_user(user_id)
    record = account_store.get(user_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")
    return _build_response(record)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(user_id: str, account_id: str, payload: AccountUpdate) -> AccountOut:
    """
    Update mutable fields of an account.
    """
    _ensure_user(user_id)
    record = account_store.get(user_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")

    if payload.display_label is not None:
        record["display_label"] = payload.display_label
    if payload.config is not None:
        record["config"] = payload.config

    updated = account_store.upsert(record)
    invalidate(user_id)
    return _build_response(updated)


@router.delete("/{account_id}")
def delete_account(user_id: str, account_id: str) -> dict[str, str]:
    """
    Delete an account and invalidate the user's manager cache.
    """
    _ensure_user(user_id)
    record = account_store.get(user_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")
    account_store.delete(user_id, account_id)
    invalidate(user_id)
    return {"status": "deleted"}


@router.post("/{account_id}/connect", response_model=AccountConnectResponse)
def connect_account(user_id: str, account_id: str) -> AccountConnectResponse:
    """
    Verify and connect an account by running provider authentication.
    """
    _ensure_user(user_id)
    record = account_store.get(user_id, account_id)
    if record is None:
        raise AccountNotFound(f"Account '{account_id}' not found.")

    client = create_client(record)
    print()
    account_label = build_client_label(user_id, account_id)

    try:
        client.authenticate()
    except Exception as exc:
        raise ProviderAuthError(
            "Failed to authenticate provider client.",
            {
                "account_id": account_id,
                "provider": record.get("provider"),
                "account_label": account_label,
            },
        ) from exc

    invalidate(user_id)

    return AccountConnectResponse(
        connected=True,
        provider=record.get("provider", ""),
        account_id=account_id,
        account_label=account_label,
        message="Account connected successfully.",
    )
