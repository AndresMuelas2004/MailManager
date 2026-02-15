from __future__ import annotations

from typing import Any
from .email_client import EmailClient, EmailMessage
from .errors import (
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailDuplicateAccountLabelError,
    EmailProviderConfigError,
)
from .gmail_client import GmailClient
from .outlook_client import OutlookClient


class EmailManager:
    """
    Coordinator for multiple EmailClient instances.
    This class is responsible for orchestrating multi-account flows.
    """

    def __init__(self) -> None:
        """
        Initialize the manager with empty client and error registries.
        """
        self._clients: list[EmailClient] = []
        self._last_errors: dict[str, Exception] = {}

    def add_account_record(self, record: dict[str, Any]) -> None:
        """
        Build and register an EmailClient based on a persisted account record.
        """
        mailbox_id = str(record.get("mailbox_id") or "")
        account_id = str(record.get("account_id") or "")
        provider = str(record.get("provider") or "").lower()
        if not mailbox_id:
            raise EmailAccountRecordError("Account record is missing mailbox_id.")
        if not account_id:
            raise EmailAccountRecordError("Account record is missing account_id.")
        if not provider:
            raise EmailAccountRecordError("Account record is missing provider.")

        account_label = f"{mailbox_id}__{account_id}"
        client = self._build_client(provider, account_label)
        self.add_client(client)

    def _build_client(self, provider: str, account_label: str) -> EmailClient:
        if provider == "gmail":
            return GmailClient(account_label=account_label)
        if provider == "outlook":
            return OutlookClient(account_label=account_label)
        raise EmailProviderConfigError(f"Unknown provider '{provider}'.")

    def add_client(self, client: EmailClient) -> None:
        """
        Register a new EmailClient with a unique account label.
        """
        new_label = client.get_account_label()
        for existing in self._clients:
            if existing.get_account_label() == new_label:
                raise EmailDuplicateAccountLabelError(f"Account label '{new_label}' already exists.")
        self._clients.append(client)

    def authenticate_all_silent(
        self,
        auth_payloads: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Authenticate all registered clients without interactive flows.
        """
        self._last_errors = {}
        refreshed_tokens: dict[str, dict[str, Any]] = {}
        for client in self._clients:
            try:
                if auth_payloads is None:
                    updated = client.authenticate_silent()
                else:
                    app_credentials = None
                    user_tokens = None
                    payload = auth_payloads.get(client.get_account_label())
                    if payload is not None:
                        app_credentials, user_tokens = payload
                    updated = client.authenticate_silent(app_credentials, user_tokens)
                if isinstance(updated, dict) and updated:
                    refreshed_tokens[client.get_account_label()] = updated
            except Exception as exc:
                self._last_errors[client.get_account_label()] = exc
        return refreshed_tokens

    def connect_account(
        self,
        account_label: str,
        app_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Authenticate a single account by its label.
        This method is for UI flows, not for scripts or batch jobs.
        """
        self._last_errors = {}
        for client in self._clients:
            if client.get_account_label() != account_label:
                continue
            try:
                return client.authenticate(app_credentials)
            except Exception as exc:
                self._last_errors[account_label] = exc
                raise
        raise EmailAccountNotFoundError(
            f"Account '{account_label}' not found.",
            {"account_label": account_label},
        )

    def fetch_all_unread_emails(self) -> list[EmailMessage]:
        """
        Fetch unread messages from all clients and return a unified list.
        """
        self._last_errors = {}
        all_unread: list[EmailMessage] = []

        for client in self._clients:
            try:
                all_unread.extend(client.fetch_unread_emails())
            except Exception as exc:
                self._last_errors[client.get_account_label()] = exc

        return all_unread

    def send_email_from_account(
        self,
        account_label: str,
        subject: str,
        body: str,
        recipients: list[str],
    ) -> None:
        """
        Send an email using the client that matches the requested account label.
        """
        for client in self._clients:
            if client.get_account_label() == account_label:
                client.send_email(subject, body, recipients)
                return

        raise EmailAccountNotFoundError(
            f"Account '{account_label}' not found.",
            {"account_label": account_label},
        )

    def get_last_errors(self) -> dict[str, Exception]:
        """
        Return a snapshot of the most recent errors per account label.
        """
        return dict(self._last_errors)
