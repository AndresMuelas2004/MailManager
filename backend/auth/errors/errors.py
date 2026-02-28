"""
Custom auth exceptions used across the authentication layer.

Raising these exceptions keeps error handling consistent within the auth
package and avoids leaking API-layer concerns into authentication code.
"""

from __future__ import annotations

from typing import Any


class AuthError(Exception):
    """
    Base class for auth errors with a stable error code and optional details.
    """

    code = "auth_error"
    default_message = "Authentication error."

    def __init__(self, message: str | None = None, detail: dict[str, Any] | None = None) -> None:
        if message is None:
            message = self.default_message
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def __str__(self) -> str:
        return self.message


class AuthSettingsError(AuthError):
    code = "auth_settings_error"
    default_message = "Auth settings error."


class AuthTokenError(AuthError):
    code = "auth_token_error"
    default_message = "Token verification error."


class AuthTokenNetworkError(AuthTokenError):
    code = "auth_token_network_error"
    default_message = "Token verification network error."


class AuthTokenInvalidError(AuthTokenError):
    code = "auth_token_invalid_error"
    default_message = "Token is malformed or invalid."


class AuthTokenProviderError(AuthTokenError):
    code = "auth_token_provider_error"
    default_message = "Token rejected by provider."
