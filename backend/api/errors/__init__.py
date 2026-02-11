"""
Error package exports for the API layer.
"""

from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    EmailFetchError,
    EmailSendError,
    EnvVarError,
    ProviderAuthError,
    StorageError,
    MailboxNotFound,
)

__all__ = [
    "AccountMisconfigured",
    "AccountNotConnected",
    "AccountNotFound",
    "ApiError",
    "EmailFetchError",
    "EmailSendError",
    "EnvVarError",
    "ProviderAuthError",
    "StorageError",
    "MailboxNotFound",
]

