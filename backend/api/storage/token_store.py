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
    StorageError,
)


_ENV_CREDENTIALS: dict[str, str] = {
    "gmail": "MIA_GMAIL_CREDENTIALS_PATH",
    "outlook": "MIA_OUTLOOK_CREDENTIALS_PATH",
}


def _token_path_for_account(record: dict[str, Any]) -> Path:
    """
    Resolve the token path for a provider account using its config and label.
    """
    mailbox_id = str(record.get("mailbox_id") or "")
    account_id = str(record.get("account_id") or "")
    provider = str(record.get("provider") or "").lower()
    if not mailbox_id or not account_id or not provider:
        raise AccountMisconfigured("Account record is missing required identifiers.")
    account_label = f"{mailbox_id}__{account_id}"

    token_dir = os.getenv("MIA_TOKEN_PATH")
    if not token_dir:
        raise EnvVarError("MIA_TOKEN_PATH is not set.")

    if provider == "gmail":
        return Path(token_dir) / f"gmail_token_{account_label}.json"

    if provider == "outlook":
        return Path(token_dir) / f"outlook_token_{account_label}.json"

    raise AccountMisconfigured(f"Unknown provider '{provider}'.")


def _delete_account_tokens(record: dict[str, Any]) -> None:
    """
    Delete account tokens on disk.
    """
    token_path = _token_path_for_account(record)

    try:
        if token_path.exists():
            token_path.unlink()
    except OSError as exc:
        raise StorageError(
            "Failed to delete token storage file.",
            {"path": str(token_path)},
        ) from exc


def delete_account_tokens_for_records(accounts: Iterable[dict[str, Any]]) -> None:
    """
    Best-effort deletion of tokens for a list of account records.
    """
    for account in accounts:
        _delete_account_tokens(account)


def load_app_credentials(provider: str) -> dict[str, Any]:
    """
    Load app credentials for the given provider from its environment-variable path.
    """
    provider = provider.lower()
    env_var = _ENV_CREDENTIALS.get(provider)
    if not env_var:
        raise AccountMisconfigured(f"Unknown provider '{provider}'.")

    credentials_path = os.getenv(env_var)
    if not credentials_path:
        raise EnvVarError(f"{env_var} is not set.")
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

    # Gmail credentials may be nested under "installed" or "web" blocks.
    if provider == "gmail":
        if isinstance(data.get("installed"), dict):
            return data["installed"]
        if isinstance(data.get("web"), dict):
            return data["web"]

    return data


def load_account_tokens(mailbox_id: str, account_id: str, provider: str) -> dict[str, Any]:
    """
    Load token credentials for a specific mailbox/account/provider.
    """
    record = {
        "mailbox_id": mailbox_id,
        "account_id": account_id,
        "provider": provider,
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
    provider: str,
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
        "provider": provider,
    }
    token_path = _token_path_for_account(record)
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(token_data, indent=2, sort_keys=True)
        temp_path = token_path.with_name(f"{token_path.name}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(token_path)
    except OSError as exc:
        raise StorageError(
            "Failed to write token storage file.",
            {"path": str(token_path)},
        ) from exc
