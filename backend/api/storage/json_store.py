"""
JSON-backed storage implementation for mailboxes and accounts.

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
from api.storage.base import AccountStore, MailboxStore


_BASE_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _BASE_DIR / "data"
_MAILBOXES_PATH = _DATA_DIR / "mailboxes.json"
_ACCOUNTS_PATH = _DATA_DIR / "accounts.json"

_mailboxes_lock = threading.Lock()
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
        raw = path.read_text(encoding="utf-8-sig").strip()
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


class JsonMailboxStore(MailboxStore):
    """
    JSON persistence for mailboxes.
    """

    def create(self, mailbox: dict[str, Any]) -> dict[str, Any]:
        with _mailboxes_lock:
            mailboxes = _load_list(_MAILBOXES_PATH)
            mailboxes.append(mailbox)
            _write_list(_MAILBOXES_PATH, mailboxes)
        return mailbox

    def list(self) -> list[dict[str, Any]]:
        with _mailboxes_lock:
            return _load_list(_MAILBOXES_PATH)

    def get(self, mailbox_id: str) -> dict[str, Any] | None:
        with _mailboxes_lock:
            mailboxes = _load_list(_MAILBOXES_PATH)
        for mailbox in mailboxes:
            if mailbox.get("mailbox_id") == mailbox_id:
                return mailbox
        return None

    def delete(self, mailbox_id: str) -> None:
        with _mailboxes_lock:
            mailboxes = _load_list(_MAILBOXES_PATH)
            next_mailboxes = [
                mailbox for mailbox in mailboxes if mailbox.get("mailbox_id") != mailbox_id
            ]
            _write_list(_MAILBOXES_PATH, next_mailboxes)


class JsonAccountStore(AccountStore):
    """
    JSON persistence for accounts.
    """

    def list_by_mailbox(self, mailbox_id: str) -> list[dict[str, Any]]:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
        return [account for account in accounts if account.get("mailbox_id") == mailbox_id]

    def get(self, mailbox_id: str, account_id: str) -> dict[str, Any] | None:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
        for account in accounts:
            if (
                account.get("mailbox_id") == mailbox_id
                and account.get("account_id") == account_id
            ):
                return account
        return None

    def upsert(self, account: dict[str, Any]) -> dict[str, Any]:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
            replaced = False
            for index, existing in enumerate(accounts):
                if (
                    existing.get("mailbox_id") == account.get("mailbox_id")
                    and existing.get("account_id") == account.get("account_id")
                ):
                    accounts[index] = account
                    replaced = True
                    break
            if not replaced:
                accounts.append(account)
            _write_list(_ACCOUNTS_PATH, accounts)
        return account

    def delete(self, mailbox_id: str, account_id: str) -> None:
        with _accounts_lock:
            accounts = _load_list(_ACCOUNTS_PATH)
            next_accounts = [
                account
                for account in accounts
                if not (
                    account.get("mailbox_id") == mailbox_id
                    and account.get("account_id") == account_id
                )
            ]
            _write_list(_ACCOUNTS_PATH, next_accounts)


mailbox_store = JsonMailboxStore()
account_store = JsonAccountStore()


def now_iso() -> str:
    """
    Provide a stable timestamp for record creation used at "create_at" in mailbox_ID and accounts record.
    """
    return datetime.now(timezone.utc).isoformat()
