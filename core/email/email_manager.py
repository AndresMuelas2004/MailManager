from __future__ import annotations

from typing import List, Dict

from .email_client import EmailClient, EmailMessage


class EmailManager:
    """
    High-level orchestrator for all email accounts.
    It exposes a simple interface to the rest of the application
    while hiding provider-specific details (Gmail, Outlook, etc.).
    """

    def __init__(self, clients: List[EmailClient] | None = None) -> None:
        """
        :param clients: Optional initial list of email clients to manage.
        """
        self._clients: List[EmailClient] = clients or []

    def add_client(self, client: EmailClient) -> None:
        """
        Register a new email client (for example a Gmail or Outlook account).
        """
        self._clients.append(client)

    def authenticate_all(self) -> None:
        """
        Call authenticate() on all registered clients.
        This should be run before fetching or sending emails.
        """
        for client in self._clients:
            client.authenticate()

    def fetch_all_unread_emails(self) -> List[EmailMessage]:
        """
        Fetch unread emails from all registered clients and return them
        as a single unified list of EmailMessage objects.
        """
        all_unread: List[EmailMessage] = []

        for client in self._clients:
            client_unread = client.fetch_unread_emails()
            all_unread.extend(client_unread)

        # Optionally, we could sort by sent date here
        all_unread.sort(key=lambda msg: msg.sent_at, reverse=True)
        return all_unread

    def send_email_from_account(
        self,
        account_label: str,
        subject: str,
        body: str,
        recipients: List[str],
    ) -> None:
        """
        Send an email using a specific account identified by its label.

        :param account_label: Label of the account that should send the email.
        """
        for client in self._clients:
            if client.get_account_label() == account_label:
                client.send_email(subject=subject, body=body, recipients=recipients)
                return

        raise ValueError(
            f"No email client found with label '{account_label}'. "
            "Make sure the account is registered in EmailManager."
        )