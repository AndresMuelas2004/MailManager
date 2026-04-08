"""
Persistence contracts for the API layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MailboxStore(ABC):
    """
    Contract for mailbox persistence.
    """

    @abstractmethod
    def create(self, mailbox: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get(self, mailbox_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, mailbox_id: str) -> None:
        raise NotImplementedError


class AccountStore(ABC):
    """
    Contract for account persistence.
    """

    @abstractmethod
    def list_by_mailbox(self, mailbox_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get(self, mailbox_id: str, account_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, account: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, mailbox_id: str, account_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_tokens(self, mailbox_id: str, account_id: str, provider: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_tokens(self, mailbox_id: str, account_id: str, provider: str, token_data: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_sync_cursor(self, mailbox_id: str, account_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def update_sync_cursor(self, mailbox_id: str, account_id: str, cursor: str) -> None:
        raise NotImplementedError


class EmailMetadataStore(ABC):
    """
    Contract for email metadata persistence.
    """

    @abstractmethod
    def upsert_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete_batch_by_message_ids(self, account_id: str, message_ids: list[str]) -> int:
        raise NotImplementedError

    @abstractmethod
    def update_labels_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def update_read_status_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_provider_message_ids(self, account_id: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_trash_emails_by_ids(self, account_id: str, message_ids: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def mark_as_deleted_batch(self, account_id: str, message_ids: list[str]) -> int:
        raise NotImplementedError

    @abstractmethod
    def restore_from_trash_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def restore_from_trash_discovered_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def move_to_trash_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def update_spam_status_batch(self, account_id: str, rows: list[tuple]) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_by_account_and_box(self, account_id: str, box: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_by_mailbox_and_box(self, mailbox_id: str, box: str) -> list[dict[str, Any]]:
        raise NotImplementedError


class UserStore(ABC):
    """
    Contract for user persistence.
    """

    @abstractmethod
    def upsert(self, user: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, user_id: str) -> bool:
        raise NotImplementedError


class SessionStore(ABC):
    """
    Contract for session persistence.
    """

    @abstractmethod
    def create(self, session: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get(self, session_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_expired(self) -> None:
        raise NotImplementedError
