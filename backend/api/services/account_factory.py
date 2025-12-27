"""
Factory for building provider-specific EmailClient instances.

All provider wiring is centralized here to keep routers and storage generic.
"""

from __future__ import annotations

from typing import Any

from core.email.email_client import EmailClient
from core.email.gmail_client import GmailClient

from api.errors.exceptions import AccountMisconfigured, ProviderNotSupported


def build_client_label(user_id: str, account_id: str) -> str:
    """
    Generate a unique client label to avoid token collisions across users.
    """
    return f"{user_id}__{account_id}"


def create_client(account_record: dict[str, Any]) -> EmailClient:
    """
    Build an EmailClient instance for the account record.
    """
    provider = (account_record.get("provider") or "").lower()
    user_id = account_record.get("user_id")
    account_id = account_record.get("account_id")

    if not user_id or not account_id:
        raise AccountMisconfigured("Account record is missing required identifiers.")

    client_label = build_client_label(user_id, account_id)

    try:
        if provider == "gmail":
            return GmailClient(account_label=client_label)
        if provider == "outlook":
            raise ProviderNotSupported("Outlook provider is not supported yet.")
    except ProviderNotSupported:
        raise
    except Exception as exc:
        raise AccountMisconfigured("Failed to initialize provider client.") from exc

    raise ProviderNotSupported(f"Provider '{provider}' is not supported.")
