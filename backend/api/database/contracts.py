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
    def list(self) -> list[dict[str, Any]]:
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

