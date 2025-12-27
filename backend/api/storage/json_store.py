"""
JSON-backed storage implementation for users and accounts.

This module persists simple serializable records to disk while keeping the
storage interface stable for a future database migration.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.errors.exceptions import StorageError
from api.storage.base import AccountStore, UserStore


_BASE_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BASE_DIR / "data"
_USERS_PATH = _DATA_DIR / "users.json"
_ACCOUNTS_PATH = _DATA_DIR / "accounts.json"

_users_lock = threading.Lock()
_accounts_lock = threading.Lock()


def _ensure_file(path: Path) -> None:
    """
    Guarantee the file exists with an empty JSON list if missing.
    """
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")


def _load_list(path: Path) -> list[dict[str, Any]]:
    """
    Load a JSON list from disk, returning an empty list on first run.
    """
    _ensure_file(path)
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError("Failed to read storage file.", {"path": str(path)}) from exc

    if not isinstance(data, list):
        raise StorageError("Storage file is corrupted.", {"path": str(path)})
    return data


def _write_list(path: Path, data: list[dict[str, Any]]) -> None:
    """
    Persist a JSON list to disk with a stable, human-readable format.

    Writes are atomic per process using a temp file + replace strategy.
    This reduces the risk of corruption when multiple processes are writing.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=True)
        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(path)
    except OSError as exc:
        raise StorageError("Failed to write storage file.", {"path": str(path)}) from exc


class JsonUserStore(UserStore):
    """
    JSON persistence for users.
    """

    def create(self, user: dict[str, Any]) -> dict[str, Any]:
        with _users_lock:
            users = _load_list(_USERS_PATH)
            users.append(user)
            _write_list(_USERS_PATH, users)
        return user

    def list(self) -> list[dict[str, Any]]:
        with _users_lock:
            return _load_list(_USERS_PATH)

    def get(self, user_id: str) -> dict[str, Any] | None:
        with _users_lock:
            users = _load_list(_USERS_PATH)
        for user in users:
            if user.get("user_id") == user_id:
                return user
        return None

    def delete(self, user_id: str) -> None:
        with _users_lock:
            users = _load_list(_USERS_PATH)
            next_users = [user for user in users if user.get("user_id") != user_id]
            _write_list(_USERS_PATH, next_users)


class JsonAccountStore(AccountStore):
    """
    JSON persistence for accounts.
    """

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
        return [account for account in accounts if account.get("user_id") == user_id]

    def get(self, user_id: str, account_id: str) -> dict[str, Any] | None:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
        for account in accounts:
            if account.get("user_id") == user_id and account.get("account_id") == account_id:
                return account
        return None

    def upsert(self, account: dict[str, Any]) -> dict[str, Any]:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
            replaced = False
            for index, existing in enumerate(accounts):
                if (
                    existing.get("user_id") == account.get("user_id")
                    and existing.get("account_id") == account.get("account_id")
                ):
                    accounts[index] = account
                    replaced = True
                    break
            if not replaced:
                accounts.append(account)
            _write_list(_ACCOUNTS_PATH, accounts)
        return account

    def delete(self, user_id: str, account_id: str) -> None:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
            next_accounts = [
                account
                for account in accounts
                if not (
                    account.get("user_id") == user_id
                    and account.get("account_id") == account_id
                )
            ]
            _write_list(_ACCOUNTS_PATH, next_accounts)


user_store = JsonUserStore()
account_store = JsonAccountStore()


def now_iso() -> str:
    """
    Provide a stable timestamp for record creation.
    """
    return datetime.now(timezone.utc).isoformat()
