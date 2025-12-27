"""
User router for minimal user management.

Authentication is out of scope for now, so user_id is explicit in paths.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from api.errors.exceptions import UserNotFound
from api.schemas.user import UserCreate, UserOut
from api.services.manager_registry import invalidate
from api.storage.json_store import account_store, now_iso, user_store


router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate) -> UserOut:
    """
    Create a user record for grouping accounts and email operations.
    """
    record = {
        "user_id": str(uuid4()),
        "display_name": payload.display_name,
        "created_at": now_iso(),
    }
    created = user_store.create(record)
    return UserOut(**created)


@router.get("", response_model=list[UserOut])
def list_users() -> list[UserOut]:
    """
    List all users stored in the system.
    """
    return [UserOut(**user) for user in user_store.list()]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str) -> UserOut:
    """
    Retrieve a single user by identifier.
    """
    record = user_store.get(user_id)
    if record is None:
        raise UserNotFound(f"User '{user_id}' not found.")
    return UserOut(**record)


@router.delete("/{user_id}")
def delete_user(user_id: str) -> dict[str, str]:
    """
    Delete a user and all accounts owned by the user.
    """
    record = user_store.get(user_id)
    if record is None:
        raise UserNotFound(f"User '{user_id}' not found.")

    accounts = account_store.list_by_user(user_id)
    for account in accounts:
        account_id = str(account.get("account_id", ""))
        if account_id:
            account_store.delete(user_id, account_id)

    user_store.delete(user_id)
    invalidate(user_id)
    return {"status": "deleted"}
