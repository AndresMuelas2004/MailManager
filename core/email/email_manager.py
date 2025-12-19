from __future__ import annotations

from typing import List
from .email_client import EmailClient, EmailMessage


class EmailManager:
    def __init__(self) -> None:
        self._clients: List[EmailClient] = []

    def add_client(self, client: EmailClient) -> None:
        self._clients.append(client)

    def authenticate_all(self) -> None:
        for client in self._clients:
            client.authenticate()

    def fetch_all_unread_emails(self) -> List[EmailMessage]:
        all_unread: List[EmailMessage] = []

        for client in self._clients:
            all_unread.extend(client.fetch_unread_emails())

        return all_unread

    def send_email_from_account(
        self,
        account_label: str,
        subject: str,
        body: str,
        recipients: List[str],
    ) -> None:
        for client in self._clients:
            if client.get_account_label() == account_label:
                client.send_email(subject, body, recipients)
                return

        raise ValueError(f"Account '{account_label}' not found.")
