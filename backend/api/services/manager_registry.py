"""
EmailManager registry for per-user caching.

Managers are rebuilt from storage whenever invalidated to avoid persisting
live client objects to disk.
"""

from __future__ import annotations

import threading

from core.email.email_manager import EmailManager

from api.errors.exceptions import AccountMisconfigured, UserNotFound
from api.services.account_factory import create_client
from api.storage.json_store import account_store, user_store


_cache_lock = threading.Lock()
_manager_cache: dict[str, EmailManager] = {}


def get_manager(user_id: str) -> EmailManager:
    """
    Resolve the EmailManager for a user, rebuilding if missing.
    """
    with _cache_lock:
        manager = _manager_cache.get(user_id)
        if manager:
            return manager

    if user_store.get(user_id) is None:
        raise UserNotFound(f"User '{user_id}' not found.")

    manager = EmailManager()
    accounts = account_store.list_by_user(user_id)

    for account in accounts:
        client = create_client(account)
        try:
            manager.add_client(client)
        except ValueError as exc:
            raise AccountMisconfigured("Duplicate account label detected.") from exc

    with _cache_lock:
        _manager_cache[user_id] = manager

    return manager


def invalidate(user_id: str) -> None:
    """
    Remove a cached manager so it will be rebuilt on the next request.
    """
    with _cache_lock:
        _manager_cache.pop(user_id, None)
