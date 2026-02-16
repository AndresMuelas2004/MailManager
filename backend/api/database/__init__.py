"""
Database package — PostgreSQL persistence layer.

Re-exports all public symbols so consumers import from ``api.database``.
"""

from api.database.db import close_pool, get_connection, init_db
from api.database.repository import account_store, mailbox_store
from api.database.token_store import (
    delete_account_tokens_for_records,
    load_account_tokens,
    load_app_credentials,
    save_account_tokens,
)

__all__ = [
    "account_store",
    "close_pool",
    "delete_account_tokens_for_records",
    "get_connection",
    "init_db",
    "load_account_tokens",
    "load_app_credentials",
    "mailbox_store",
    "save_account_tokens",
]
