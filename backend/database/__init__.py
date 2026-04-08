"""
Database package public surface.
"""

from __future__ import annotations

from database.connection import close_pool
from database.errors import (
    ConnectionPoolError,
    CredentialReadError,
    DatabaseError,
    MigrationError,
    QueryError,
    SettingsError,
    TokenCryptoError,
    TokenDecryptError,
    TokenEncryptError,
    TokenValidationError,
    UnknownProviderError,
)
from database.lifecycle import run_startup_migrations_if_enabled, warmup_connection
from database.repositories import account_store, email_content_store, email_metadata_store, mailbox_store, session_store, user_store
from database.security import load_app_credentials

__all__ = [
    "account_store",
    "close_pool",
    "email_content_store",
    "ConnectionPoolError",
    "CredentialReadError",
    "DatabaseError",
    "email_metadata_store",
    "load_app_credentials",
    "mailbox_store",
    "MigrationError",
    "QueryError",
    "run_startup_migrations_if_enabled",
    "session_store",
    "SettingsError",
    "TokenCryptoError",
    "TokenDecryptError",
    "TokenEncryptError",
    "TokenValidationError",
    "UnknownProviderError",
    "user_store",
    "warmup_connection",
]
