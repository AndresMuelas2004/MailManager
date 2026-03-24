from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    box: str  # "ALL_MAIL" | "SENT" | "SPAM" | "TRASH"
    account_id: str = ""  # Stamped by the service layer before persistence


@dataclass
class LabelUpdate:
    """Partial update carrying only label-derived fields for an existing message."""
    provider_message_id: str
    is_read: bool
    box: str  # "ALL_MAIL" | "SENT" | "SPAM" | "TRASH"


@dataclass
class SyncResult:
    """
    Result of fetch_email_metadata, supporting both bootstrap and incremental sync.

    - upserts: full metadata to insert or update.
    - new_cursor: opaque sync cursor for the next call.
    - deletes: provider_message_ids to remove from persistence.
    - label_updates: partial updates (is_read, box) for messages already persisted.
    """
    upserts: list[EmailMetadata]
    new_cursor: str
    deletes: list[str] = field(default_factory=list)
    label_updates: list[LabelUpdate] = field(default_factory=list)
    is_full_sync: bool = False


@dataclass
class SpamMoveResult:
    """Result of a spam move/restore for a single message."""
    old_id: str
    new_id: str  # Same as old_id for Gmail; different for Outlook


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
    ) -> SyncResult:
        """
        Fetch email metadata from the provider.

        Returns a SyncResult with upserts, deletes, label_updates and new_cursor.
        - If sync_cursor is None -> bootstrap (Path 1).
        - If sync_cursor is not None -> attempt incremental (Path 2),
          fallback to bootstrap on failure.
        """

    @abstractmethod
    def send_email(
        self,
        subject: str,
        body: str,
        recipients: list[str],
    ) -> EmailMetadata:
        """
        Send a simple email message using this provider.
        :param subject: Email subject line.
        :param body: Plain text body of the email.
        :param recipients: List of recipient email addresses.
        :return: Metadata of the sent email.
        """

    @abstractmethod
    def verify_message_existence(self, message_ids: list[str]) -> list[str]:
        """Return the subset of message_ids that still exist at the provider."""

    @abstractmethod
    def update_read_status(self, message_ids: list[str], is_read: bool) -> list[str]:
        """Mark messages as read/unread at the provider. Returns IDs successfully updated."""

    @abstractmethod
    def move_to_spam(self, message_ids: list[str]) -> list[SpamMoveResult]:
        """Move messages to spam at the provider. Returns results for successfully moved messages."""

    @abstractmethod
    def restore_from_spam(self, message_ids: list[str]) -> list[SpamMoveResult]:
        """Restore messages from spam at the provider. Returns results for successfully restored messages."""

    @abstractmethod
    def get_account_label(self) -> str:
        """
        Return a human-readable label for this account (for example,
        'personal_gmail', 'university_outlook', etc).
        This helps the manager know which account is which.
        """
