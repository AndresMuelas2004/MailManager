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


class AccountConnectAuthError(ApiError):
    code = "account_connect_auth_error"


class AccountNotConnected(ApiError):
    code = "account_not_connected"


class CredentialFileError(ApiError):
    code = "credential_file_error"


class DatabaseConnectionError(ApiError):
    code = "database_connection_error"


class DatabaseMigrationError(ApiError):
    code = "database_migration_error"


class DatabaseQueryError(ApiError):
    code = "database_query_error"


class EmailFetchError(ApiError):
    code = "email_fetch_error"


class EmailSendError(ApiError):
    code = "email_send_error"


class ExternalAPIError(ApiError):
    code = "external_api_error"


class AccountMisconfigured(ApiError):
    code = "account_misconfigured"


class AppCredentialsInvalid(ApiError):
    code = "app_credentials_invalid"


class AppCredentialsMissing(ApiError):
    code = "app_credentials_missing"


class RecipientsMissing(ApiError):
    code = "recipients_missing"


class EnvVarError(ApiError):
    code = "env_var_error"


class Unauthorized(ApiError):
    code = "unauthorized"


class Forbidden(ApiError):
    code = "forbidden"


class TokenDecryptionError(ApiError):
    code = "token_decryption_error"


class TokenEncryptionError(ApiError):
    code = "token_encryption_error"


class TokenIntegrityError(ApiError):
    code = "token_integrity_error"


class UserNotFound(ApiError):
    code = "user_not_found"


class EmailNotInTrash(ApiError):
    code = "email_not_in_trash"


class TrashOperationError(ApiError):
    code = "trash_operation_error"


class MoveToTrashError(ApiError):
    code = "move_to_trash_error"


class ReadStatusUpdateError(ApiError):
    code = "read_status_update_error"


class SpamMoveError(ApiError):
    code = "spam_move_error"


class SpamRestoreError(ApiError):
    code = "spam_restore_error"


class EmailListError(ApiError):
    code = "email_list_error"
