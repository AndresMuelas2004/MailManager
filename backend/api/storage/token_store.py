"""
Token storage helpers for provider accounts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    EnvVarError,
    ProviderNotSupported,
    StorageError,
)




def _token_path_for_account(record: dict[str, Any]) -> Path:
    """
    Resolve the token path for a provider account using its config and label.
    """
    mailbox_id = str(record.get("mailbox_id") or "")
    account_id = str(record.get("account_id") or "")
    provider = str(record.get("provider") or "").lower()
    if not mailbox_id or not account_id or not provider:
        # Token resolution depends on provider and account identity.
        raise AccountMisconfigured("Account record is missing required identifiers.")
    account_label = f"{mailbox_id}__{account_id}"

    if provider == "gmail":
        token_dir = os.getenv("MIA_GMAIL_TOKEN_PATH")
        if not token_dir:
            raise EnvVarError("MIA_GMAIL_TOKEN_PATH is not set.")
        return Path(token_dir) / f"gmail_token_{account_label}.json"

    if provider == "outlook":
        raise ProviderNotSupported("Outlook provider is not supported yet.")

    raise ProviderNotSupported(f"Provider '{provider}' is not supported.")


def _delete_account_tokens(record: dict[str, Any]) -> None:
    """
    Best-effort deletion of account tokens on disk.
    """
    try:
        token_path = _token_path_for_account(record)
    except EnvVarError:
        raise
    except Exception:
        return

    try:
        if token_path.exists():
            # Ignore missing files or unlink errors to keep deletes non-blocking.
            token_path.unlink()
    except Exception:
        return


def delete_account_tokens_for_records(accounts: Iterable[dict[str, Any]]) -> None:
    """
    Best-effort deletion of tokens for a list of account records.
    """
    for account in accounts:
        # Ignore per-account failures so callers can continue cleanup.
        _delete_account_tokens(account)


def load_app_credentials() -> dict[str, Any]:
    """
    Load the Gmail app credentials from the JSON path in MIA_GMAIL_CREDENTIALS_PATH.
    """
    credentials_path = os.getenv("MIA_GMAIL_CREDENTIALS_PATH")
    if not credentials_path:
        raise EnvVarError("MIA_GMAIL_CREDENTIALS_PATH is not set.")
    config_path = Path(credentials_path)
    try:
        raw = config_path.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError("Failed to read config storage file.", {"path": str(config_path)}) from exc

    if not isinstance(data, dict):
        raise StorageError("Config storage file is corrupted.", {"path": str(config_path)})

    if isinstance(data.get("installed"), dict):
        return data["installed"]
    if isinstance(data.get("web"), dict):
        return data["web"]
    return data


def load_account_tokens(mailbox_id: str, account_id: str) -> dict[str, Any]:
    """
    Load token credentials for a specific mailbox/account.
    """
    record = {
        "mailbox_id": mailbox_id,
        "account_id": account_id,
        "provider": "gmail",
    }
    token_path = _token_path_for_account(record)
    if not token_path.exists():
        raise AccountNotConnected("Account token not found.")

    try:
        raw = token_path.read_text(encoding="utf-8-sig").strip()
        token_data = json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError("Failed to read token storage file.", {"path": str(token_path)}) from exc

    if not isinstance(token_data, dict):
        raise StorageError("Token storage file is corrupted.", {"path": str(token_path)})

    access_token = token_data.get("access_token") or token_data.get("token")
    return {
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token"),
        "expiry": token_data.get("expiry"),
        "scopes": token_data.get("scopes"),
    }


def save_account_tokens(
    mailbox_id: str,
    account_id: str,
    token_data: dict[str, Any],
) -> None:
    """
    Persist token credentials for a mailbox/account in the token directory.
    """
    if not isinstance(token_data, dict):
        raise StorageError(
            "Token payload is invalid.",
            {"mailbox_id": mailbox_id, "account_id": account_id},
        )

    record = {
        "mailbox_id": mailbox_id,
        "account_id": account_id,
        "provider": "gmail",
    }
    token_path = _token_path_for_account(record)
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(token_data, indent=2, sort_keys=True)
        token_path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise StorageError(
            "Failed to write token storage file.",
            {"path": str(token_path)},
        ) from exc
