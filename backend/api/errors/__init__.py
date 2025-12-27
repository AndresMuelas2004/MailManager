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
    ProviderAuthError,
    ProviderNotSupported,
    StorageError,
    UserNotFound,
)

__all__ = [
    "AccountMisconfigured",
    "AccountNotConnected",
    "AccountNotFound",
    "ApiError",
    "EmailFetchError",
    "EmailSendError",
    "ProviderAuthError",
    "ProviderNotSupported",
    "StorageError",
    "UserNotFound",
]
