"""
Error package exports for the API layer.
"""

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    EmailFetchError,
    EmailSendError,
    EnvVarError,
    ExternalAPIError,
    StorageError,
    MailboxNotFound,
)

__all__ = [
    "AccountConnectAuthError",
    "AccountMisconfigured",
    "AccountNotConnected",
    "AccountNotFound",
    "ApiError",
    "EmailFetchError",
    "EmailSendError",
    "EnvVarError",
    "ExternalAPIError",
    "StorageError",
    "MailboxNotFound",
]
