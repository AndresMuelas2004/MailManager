"""
Error package exports for the API layer.
"""

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    CredentialFileError,
    DatabaseConnectionError,
    DatabaseMigrationError,
    DatabaseQueryError,
    EmailFetchError,
    EmailSendError,
    EnvVarError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
    TokenDecryptionError,
    TokenIntegrityError,
    Unauthorized,
    UserNotFound,
)

__all__ = [
    "AccountConnectAuthError",
    "AccountMisconfigured",
    "AccountNotConnected",
    "AccountNotFound",
    "ApiError",
    "CredentialFileError",
    "DatabaseConnectionError",
    "DatabaseMigrationError",
    "DatabaseQueryError",
    "EmailFetchError",
    "EmailSendError",
    "EnvVarError",
    "ExternalAPIError",
    "Forbidden",
    "MailboxNotFound",
    "TokenDecryptionError",
    "TokenIntegrityError",
    "Unauthorized",
    "UserNotFound",
]
