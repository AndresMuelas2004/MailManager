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
    box: str  # "ALL_MAIL" | "SENT" | "SPAM" | "TRASH" | "DELETED"
    account_id: str = ""  # Stamped by the service layer before persistence


@dataclass
class LabelUpdate:
    """Partial update carrying only label-derived fields for an existing message."""
    provider_message_id: str
    is_read: bool
    box: str  # "ALL_MAIL" | "SENT" | "SPAM" | "TRASH" | "DELETED"


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


@dataclass
class EmailContent:
    """Full body content of a single email message."""
    html_body: str | None
    text_body: str | None


@dataclass
class DraftMetadata:
    """
    Normalized draft metadata returned by provider clients after creating a draft.
    """
    provider_draft_id: str
    to_recipients: list[str]
    cc_recipients: list[str]
    bcc_recipients: list[str]
    subject: str
    body_html: str
    created_at: datetime
    updated_at: datetime


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
    def create_draft(
        self,
        to_recipients: list[str],
        cc_recipients: list[str],
        bcc_recipients: list[str],
        subject: str,
        body_html: str,
    ) -> DraftMetadata:
        """
        Create a draft message at the provider. All fields may be empty
        (empty drafts are allowed). Returns normalized draft metadata.
        """

    @abstractmethod
    def update_draft(
        self,
        provider_draft_id: str,
        to_recipients: list[str],
        cc_recipients: list[str],
        bcc_recipients: list[str],
        subject: str,
        body_html: str,
    ) -> DraftMetadata:
        """
        Replace an existing draft's content at the provider (full-field
        replace). All fields may be empty (empty drafts are accepted).
        Returns normalized draft metadata — timestamps are best-effort
        (providers may not return them on update).
        """

    @abstractmethod
    def fetch_drafts(self) -> list[DraftMetadata]:
        """
        Fetch the most recent drafts from the provider as a flat list.

        Implementations MUST respect a hard cap of ``_DRAFTS_MAX_TOTAL``
        drafts per account (currently 100) and return the most recent
        ones. The exact ordering semantics depend on the provider:
        Outlook uses ``$orderby=lastModifiedDateTime desc`` explicitly;
        Gmail relies on the native API order (reverse-chronological by
        convention). Returns an empty list when the mailbox has no drafts.

        Implementations must raise CoreError subclasses on failure — never
        return a partial list silently.
        """

    @abstractmethod
    def verify_message_existence(self, message_ids: list[str]) -> list[str]:
        """Return the subset of message_ids that still exist at the provider."""

    @abstractmethod
    def delete_messages(self, message_ids: list[str]) -> list[str]:
        """Permanently delete messages at the provider.
        Returns the list of provider_message_ids that were successfully deleted.
        Implementations that cannot delete at the provider (e.g. scope limitations)
        should return all IDs as succeeded — the service layer handles local cleanup."""

    @abstractmethod
    def restore_from_trash(self, items: dict[str, str | None]) -> dict[str, str]:
        """Restore messages from trash at the provider.
        items maps provider_message_id → destination_box ('ALL_MAIL', 'SENT', 'SPAM')
        or None when the original box is unknown.
        Returns dict mapping original_id → new_id for successfully restored messages.
        For providers where the ID doesn't change on restore, original_id == new_id."""

    @abstractmethod
    def fetch_messages_metadata(self, message_ids: list[str]) -> list[EmailMetadata]:
        """Fetch current metadata for specific messages by ID.
        Returns metadata with box determined by the provider's label/folder state
        using the standard priority (SPAM > SENT > ALL_MAIL).
        Messages that cannot be fetched are silently skipped."""

    @abstractmethod
    def move_to_trash(self, message_ids: list[str]) -> dict[str, str]:
        """Move messages to trash at the provider.
        Returns dict mapping original_id → new_id for successfully trashed messages.
        For providers where the ID doesn't change on trash, original_id == new_id."""

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
    def fetch_email_content(self, provider_message_id: str) -> EmailContent:
        """Fetch the full body content for a single email message."""

    @abstractmethod
    def get_account_label(self) -> str:
        """
        Return a human-readable label for this account (for example,
        'personal_gmail', 'university_outlook', etc).
        This helps the manager know which account is which.
        """
