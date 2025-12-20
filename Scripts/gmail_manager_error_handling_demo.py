from __future__ import annotations

import os
from typing import List

from core.email.email_client import EmailClient, EmailMessage
from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


class FailingClient(EmailClient):
    def __init__(self, account_label: str, reason: str) -> None:
        self._account_label = account_label
        self._reason = reason

    def authenticate(self) -> None:
        raise RuntimeError(self._reason)

    def fetch_unread_emails(self) -> List[EmailMessage]:
        raise RuntimeError(self._reason)

    def send_email(self, subject: str, body: str, recipients: List[str]) -> None:
        raise RuntimeError(self._reason)

    def get_account_label(self) -> str:
        return self._account_label


def main() -> None:
    manager = EmailManager()

    # Simulates a broken account without needing real credentials.
    manager.add_client(FailingClient(account_label="broken_account", reason="Simulated failure"))

    # Optional: include a real Gmail account for a mixed-success run.
    include_gmail = os.getenv("MIA_TEST_INCLUDE_GMAIL") == "1"
    if include_gmail:
        manager.add_client(GmailClient(account_label="real_gmail"))

    manager.authenticate_all()
    print("Authenticate errors:", manager.get_last_errors())

    manager.fetch_all_unread_emails()
    print("Fetch errors:", manager.get_last_errors())


if __name__ == "__main__":
    main()
