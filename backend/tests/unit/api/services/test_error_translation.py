"""
Unit tests for translate_core_error, translate_database_error, and translate_auth_error.

Each test parametrizes over the full mapping table and verifies that the
source error is translated to the correct ApiError subclass with the
expected message and detail propagation.
"""

from __future__ import annotations

import pytest

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    AppCredentialsInvalid,
    AppCredentialsMissing,
    CredentialFileError,
    DatabaseConnectionError,
    DatabaseMigrationError,
    DatabaseQueryError,
    EnvVarError,
    ExternalAPIError,
    RecipientsMissing,
    TokenDecryptionError,
    TokenEncryptionError,
    TokenIntegrityError,
    Unauthorized,
)
from api.services.services_helpers import (
    translate_auth_error,
    translate_core_error,
    translate_database_error,
)
from auth import (
    AuthError,
    AuthSettingsError,
    AuthTokenError,
    AuthTokenInvalidError,
    AuthTokenNetworkError,
    AuthTokenProviderError,
)
from core.email.errors import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailAuthError,
    EmailConfigError,
    EmailDuplicateAccountLabelError,
    EmailExternalAPIError,
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from database import (
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


# ==================================================================
# Core → API translation
# ==================================================================

_CORE_CASES = [
    (EmailAccountNotFoundError, AccountNotFound),
    (EmailMissingTokenError, AccountNotConnected),
    (EmailMissingRefreshTokenError, AccountNotConnected),
    (EmailRefreshFailedError, AccountNotConnected),
    (EmailNotAuthenticatedError, AccountNotConnected),
    (EmailAuthError, AccountNotConnected),
    (EmailInvalidExpiryError, AccountMisconfigured),
    (EmailInvalidCredentialsDataError, AppCredentialsInvalid),
    (EmailInvalidTokenDataError, AccountMisconfigured),
    (EmailAccountRecordError, AccountMisconfigured),
    (EmailProviderConfigError, AccountMisconfigured),
    (EmailMissingAppCredentialsError, AppCredentialsMissing),
    (EmailDuplicateAccountLabelError, AccountMisconfigured),
    (EmailConfigError, AccountMisconfigured),
    (EmailRecipientsMissingError, RecipientsMissing),
    (EmailExternalAPIError, ExternalAPIError),
    (CoreError, ApiError),
]


class TestTranslateCoreError:

    @pytest.mark.parametrize("core_cls, api_cls", _CORE_CASES)
    def test_mapping(self, core_cls, api_cls):
        exc = core_cls("test message")
        result = translate_core_error(exc)
        assert isinstance(result, api_cls)
        assert result.message == "test message"
        assert result.detail.get("core_code") == core_cls.code

    def test_non_core_error_uses_fallback(self):
        result = translate_core_error(RuntimeError("boom"))
        assert isinstance(result, ApiError)
        assert "boom" in result.message

    def test_custom_fallback(self):
        result = translate_core_error(RuntimeError("oops"), fallback=ExternalAPIError)
        assert isinstance(result, ExternalAPIError)

    def test_context_propagation(self):
        exc = EmailAuthError("auth fail")
        ctx = {"account_id": "a1"}
        result = translate_core_error(exc, context=ctx)
        assert result.detail.get("account_id") == "a1"
        assert result.detail.get("core_code") == EmailAuthError.code


# ==================================================================
# Database → API translation
# ==================================================================

_DB_CASES = [
    (ConnectionPoolError, DatabaseConnectionError),
    (QueryError, DatabaseQueryError),
    (MigrationError, DatabaseMigrationError),
    (SettingsError, EnvVarError),
    (TokenCryptoError, TokenDecryptionError),
    (TokenEncryptError, TokenEncryptionError),
    (TokenDecryptError, TokenDecryptionError),
    (TokenValidationError, TokenIntegrityError),
    (CredentialReadError, CredentialFileError),
    (UnknownProviderError, AccountMisconfigured),
    (DatabaseError, ApiError),
]


class TestTranslateDatabaseError:

    @pytest.mark.parametrize("db_cls, api_cls", _DB_CASES)
    def test_mapping(self, db_cls, api_cls):
        exc = db_cls("test message")
        result = translate_database_error(exc)
        assert isinstance(result, api_cls)
        assert result.message == "test message"
        assert result.detail.get("db_code") == db_cls.code

    def test_non_database_error_uses_fallback(self):
        result = translate_database_error(RuntimeError("boom"))
        assert isinstance(result, ApiError)
        assert "boom" in result.message

    def test_context_propagation(self):
        exc = QueryError("query fail")
        ctx = {"table": "accounts"}
        result = translate_database_error(exc, context=ctx)
        assert result.detail.get("table") == "accounts"
        assert result.detail.get("db_code") == QueryError.code


# ==================================================================
# Auth → API translation
# ==================================================================

_AUTH_CASES = [
    (AuthSettingsError, EnvVarError),
    (AuthTokenNetworkError, ExternalAPIError),
    (AuthTokenInvalidError, Unauthorized),
    (AuthTokenProviderError, Unauthorized),
    (AuthTokenError, Unauthorized),
    (AuthError, ApiError),
]


class TestTranslateAuthError:

    @pytest.mark.parametrize("auth_cls, api_cls", _AUTH_CASES)
    def test_mapping(self, auth_cls, api_cls):
        exc = auth_cls("test message")
        result = translate_auth_error(exc)
        assert isinstance(result, api_cls)
        assert result.message == "test message"
        assert result.detail.get("auth_code") == auth_cls.code

    def test_non_auth_error_uses_fallback(self):
        result = translate_auth_error(RuntimeError("boom"))
        assert isinstance(result, ApiError)
        assert "boom" in result.message

    def test_context_propagation(self):
        exc = AuthTokenInvalidError("invalid")
        ctx = {"provider": "google"}
        result = translate_auth_error(exc, context=ctx)
        assert result.detail.get("provider") == "google"
        assert result.detail.get("auth_code") == AuthTokenInvalidError.code
