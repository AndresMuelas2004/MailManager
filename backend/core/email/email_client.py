from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class EmailMessage:
    """
    Simple data container representing a normalized email message
    used across the application, regardless of the provider.
    """
    message_id: str
    subject: str
    sender: str
    recipients: list[str]
    body: str
    sent_at: datetime
    is_unread: bool
    provider: str
    thread_id: str | None = None
    raw_rfc822_b64url: str | None = None


class EmailClient(ABC):
    """
    Abstract base class that defines the contract for any email provider
    (Gmail, Outlook, etc). All concrete clients must implement these methods.
    """

    @abstractmethod
    def authenticate(
        self,
        app_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Perform any authentication or token refresh needed for this client.
        This method should be called before making API calls.
        """

    @abstractmethod
    def authenticate_silent(
        self,
        app_credentials: dict[str, Any] | None = None,
        user_tokens: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Perform authentication without starting interactive flows.
        Returns updated token payload when a refresh occurs.
        """

    @abstractmethod
    def fetch_unread_emails(self, max_total: int = 200, page_size: int = 50) -> list[EmailMessage]:
        """
        Retrieve unread emails from the provider and return them as a list
        of normalized EmailMessage objects.
        """

    @abstractmethod
    def send_email(
        self,
        subject: str,
        body: str,
        recipients: list[str],
    ) -> None:
        """
        Send a simple email message using this provider.
        :param subject: Email subject line.
        :param body: Plain text body of the email.
        :param recipients: List of recipient email addresses.
        """

    @abstractmethod
    def get_account_label(self) -> str:
        """
        Return a human-readable label for this account (for example,
        'personal_gmail', 'university_outlook', etc).
        This helps the manager know which account is which.
        """
