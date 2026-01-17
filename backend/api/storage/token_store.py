"""
Token storage helpers for provider accounts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from api.errors.exceptions import AccountMisconfigured, EnvVarError, ProviderNotSupported


def token_path_for_account(record: dict[str, Any]) -> Path:
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


def delete_account_tokens(record: dict[str, Any]) -> None:
    """
    Best-effort deletion of account tokens on disk.
    """
    try:
        token_path = token_path_for_account(record)
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
        delete_account_tokens(account)
