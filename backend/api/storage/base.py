"""
Storage interfaces for the API layer.

These abstract classes keep routers and services independent from the
current persistence implementation (JSON today, database later).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class UserStore(ABC):
    """
    Contract for user persistence.
    """

    @abstractmethod
    def create(self, user: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get(self, user_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, user_id: str) -> None:
        raise NotImplementedError


class AccountStore(ABC):
    """
    Contract for account persistence.
    """

    @abstractmethod
    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get(self, user_id: str, account_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, account: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, user_id: str, account_id: str) -> None:
        raise NotImplementedError
