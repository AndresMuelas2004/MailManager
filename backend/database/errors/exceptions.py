"""
Custom database exceptions used across the persistence layer.

Raising these exceptions keeps error handling consistent within the database
package and avoids leaking API-layer concerns into persistence code.
"""

from __future__ import annotations

from typing import Any


class DatabaseError(Exception):
    """
    Base class for database errors with a stable error code and optional details.
    """

    code = "database_error"
    default_message = "Database error."

    def __init__(self, message: str | None = None, detail: dict[str, Any] | None = None) -> None:
        if message is None:
            message = self.default_message
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def __str__(self) -> str:
        return self.message


class ConnectionPoolError(DatabaseError):
    code = "connection_pool_error"
    default_message = "Database connection pool error."


class QueryError(DatabaseError):
    code = "query_error"
    default_message = "Database query error."


class MigrationError(DatabaseError):
    code = "migration_error"
    default_message = "Database migration error."


class SettingsError(DatabaseError):
    code = "settings_error"
    default_message = "Database settings error."


class TokenDecryptError(DatabaseError):
    code = "token_decrypt_error"
    default_message = "Failed to decrypt account token."


class TokenValidationError(DatabaseError):
    code = "token_validation_error"
    default_message = "Token integrity validation failed."


class CredentialReadError(DatabaseError):
    code = "credential_read_error"
    default_message = "Failed to read credential file."


class UnknownProviderError(DatabaseError):
    code = "unknown_provider_error"
    default_message = "Unknown email provider."
