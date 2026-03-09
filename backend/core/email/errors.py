from __future__ import annotations

from typing import Any


class CoreError(Exception):
    code = "core_error"
    default_message = "Core error."

    def __init__(self, message: str | None = None, detail: dict[str, Any] | None = None) -> None:
        if message is None:
            message = self.default_message
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def __str__(self) -> str:
        return self.message


class EmailError(CoreError):
    code = "email_error"
    default_message = "Email error."


class EmailAuthError(EmailError):
    code = "email_auth_error"
    default_message = "Email authentication error."


class EmailConfigError(EmailError):
    code = "email_config_error"
    default_message = "Email configuration error."


class EmailAccountRecordError(EmailConfigError):
    code = "email_account_record_error"
    default_message = "Account record is invalid."


class EmailProviderConfigError(EmailConfigError):
    code = "email_provider_config_error"
    default_message = "Provider configuration is invalid."


class EmailInvalidExpiryError(EmailConfigError):
    code = "email_invalid_expiry_error"
    default_message = "Invalid or unparseable expiry value."


class EmailInvalidCredentialsDataError(EmailConfigError):
    code = "email_invalid_credentials_data_error"
    default_message = "App credentials data is structurally invalid."


class EmailInvalidTokenDataError(EmailConfigError):
    code = "email_invalid_token_data_error"
    default_message = "Token data is structurally invalid."


class EmailMissingAppCredentialsError(EmailConfigError):
    code = "email_missing_app_credentials_error"
    default_message = "Missing app credentials."


class EmailDuplicateAccountLabelError(EmailConfigError):
    code = "email_duplicate_account_label_error"
    default_message = "Account label already exists."


class EmailAccountNotFoundError(EmailError):
    code = "email_account_not_found_error"
    default_message = "Account not found."


class EmailMissingTokenError(EmailAuthError):
    code = "email_missing_token_error"
    default_message = "Access token is missing."


class EmailMissingRefreshTokenError(EmailAuthError):
    code = "email_missing_refresh_token_error"
    default_message = "Refresh token is missing."


class EmailRefreshFailedError(EmailAuthError):
    code = "email_refresh_failed_error"
    default_message = "Token refresh failed."


class EmailNotAuthenticatedError(EmailAuthError):
    code = "email_not_authenticated_error"
    default_message = "Client is not authenticated."


class EmailRecipientsMissingError(EmailError):
    code = "email_recipients_missing_error"
    default_message = "At least one recipient is required."


class EmailExternalAPIError(EmailError):
    code = "email_external_api_error"
    default_message = "External API call failed."
