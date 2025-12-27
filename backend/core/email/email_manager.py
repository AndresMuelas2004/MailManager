from __future__ import annotations

from typing import List
from .email_client import EmailClient, EmailMessage


class EmailManager:
    """
    Coordinator for multiple EmailClient instances.
    This class is responsible for orchestrating multi-account flows.
    """

    def __init__(self) -> None:
        """
        Initialize the manager with empty client and error registries.
        """
        self._clients: List[EmailClient] = []
        self._last_errors: dict[str, Exception] = {}

    def add_client(self, client: EmailClient) -> None:
        """
        Register a new EmailClient with a unique account label.
        """
        new_label = client.get_account_label()
        for existing in self._clients:
            if existing.get_account_label() == new_label:
                raise ValueError(f"Account label '{new_label}' already exists.")
        self._clients.append(client)


    def authenticate_all(self) -> None:
        """
        Authenticate all registered clients, tracking failures per account.

        Convenience method intended for scripts, batch jobs, or non-UI flows.
        Avoid calling this from API/web request handlers.
        """
        self._last_errors = {}
        for client in self._clients:
            try:
                client.authenticate()
            except Exception as exc:
                self._last_errors[client.get_account_label()] = exc

    def connect_account(self, account_label: str) -> None:
        """
        Authenticate a single account by its label.
        """
        self._last_errors = {}
        for client in self._clients:
            if client.get_account_label() != account_label:
                continue
            try:
                client.authenticate()
            except Exception as exc:
                self._last_errors[account_label] = exc
                raise
            return
        raise ValueError(f"Account '{account_label}' not found.")

    def fetch_all_unread_emails(self) -> List[EmailMessage]:
        """
        Fetch unread messages from all clients and return a unified list.
        """
        self._last_errors = {}
        all_unread: List[EmailMessage] = []

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
        recipients: List[str],
    ) -> None:
        """
        Send an email using the client that matches the requested account label.
        """
        for client in self._clients:
            if client.get_account_label() == account_label:
                client.send_email(subject, body, recipients)
                return

        raise ValueError(f"Account '{account_label}' not found.")

    def get_last_errors(self) -> dict[str, Exception]:
        """
        Return a snapshot of the most recent errors per account label.
        """
        return dict(self._last_errors)
