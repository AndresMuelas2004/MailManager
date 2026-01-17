"""
Custom API exceptions used across routers and services.

Raising these exceptions keeps error handling consistent and avoids
leaking low-level details directly to HTTP responses.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """
    Base class for API errors with a stable error code and optional details.
    """

    code = "api_error"

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class MailboxNotFound(ApiError):
    code = "mailbox_not_found"


class AccountNotFound(ApiError):
    code = "account_not_found"


class ProviderNotSupported(ApiError):
    code = "provider_not_supported"


class StorageError(ApiError):
    code = "storage_error"


class ProviderAuthError(ApiError):
    code = "provider_auth_error"


class AccountNotConnected(ApiError):
    code = "account_not_connected"


class EmailFetchError(ApiError):
    code = "email_fetch_error"


class EmailSendError(ApiError):
    code = "email_send_error"


class AccountMisconfigured(ApiError):
    code = "account_misconfigured"


class EnvVarError(ApiError):
    code = "env_var_error"
