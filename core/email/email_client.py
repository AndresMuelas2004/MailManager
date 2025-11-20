from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List


@dataclass
class EmailMessage:
    """
    Simple data container representing a normalized email message
    used across the application, regardless of the provider.
    """
    message_id: str
    subject: str
    sender: str
    recipients: List[str]
    body: str
    sent_at: datetime
    is_unread: bool
    provider: str
    raw_payload: Any | None = None  # Optional raw data from the provider


class EmailClient(ABC):
    """
    Abstract base class that defines the contract for any email provider
    (Gmail, Outlook, etc). All concrete clients must implement these methods.
    """

    @abstractmethod
    def authenticate(self) -> None:
        """
        Perform any authentication or token refresh needed for this client.
        This method should be called before making API calls.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_unread_emails(self) -> List[EmailMessage]:
        """
        Retrieve unread emails from the provider and return them as a list
        of normalized EmailMessage objects.
        """
        raise NotImplementedError

    @abstractmethod
    def send_email(
        self,
        subject: str,
        body: str,
        recipients: List[str],
    ) -> None:
        """
        Send a simple email message using this provider.

        :param subject: Email subject line.
        :param body: Plain text body of the email.
        :param recipients: List of recipient email addresses.
        """
        raise NotImplementedError

    @abstractmethod
    def get_account_label(self) -> str:
        """
        Return a human-readable label for this account (for example,
        'personal_gmail', 'university_outlook', etc).
        This helps the manager know which account is which.
        """
        raise NotImplementedError