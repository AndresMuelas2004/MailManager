from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class EmailMetadata:
    """
    Normalized email metadata returned by provider clients.
    """
    provider_message_id: str
    thread_id: str
    from_email: str
    from_name: str
    subject: str
    received_at: datetime
    is_read: bool
    box: str  # "ALL_MAIL" | "SPAM" | "TRASH"
    account_id: str = ""  # Stamped by the service layer before persistence


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
    def fetch_email_metadata(
        self,
        sync_cursor: str | None = None,
        max_total: int = 500,
    ) -> tuple[list[EmailMetadata], str]:
        """
        Fetch email metadata from the provider.

        Returns (metadata_list, new_sync_cursor).
        - If sync_cursor is None -> bootstrap (Camino 1).
        - If sync_cursor is not None -> attempt incremental (Camino 2),
          fallback to bootstrap on failure.
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
