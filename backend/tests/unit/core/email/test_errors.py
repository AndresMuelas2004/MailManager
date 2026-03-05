"""Unit tests for the core email error hierarchy."""

from __future__ import annotations

import pytest

from core.email.errors import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailAuthError,
    EmailConfigError,
    EmailDuplicateAccountLabelError,
    EmailError,
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


class TestInheritanceChain:
    def test_core_error_is_exception(self):
        assert issubclass(CoreError, Exception)

    def test_email_error_inherits_core_error(self):
        assert issubclass(EmailError, CoreError)

    def test_email_auth_error_inherits_email_error(self):
        assert issubclass(EmailAuthError, EmailError)

    def test_email_config_error_inherits_email_error(self):
        assert issubclass(EmailConfigError, EmailError)

    @pytest.mark.parametrize(
        "cls",
        [
            EmailMissingTokenError,
            EmailMissingRefreshTokenError,
            EmailRefreshFailedError,
            EmailNotAuthenticatedError,
        ],
    )
    def test_auth_subclasses_inherit_email_auth_error(self, cls):
        assert issubclass(cls, EmailAuthError)

    @pytest.mark.parametrize(
        "cls",
        [
            EmailAccountRecordError,
            EmailProviderConfigError,
            EmailInvalidExpiryError,
            EmailInvalidCredentialsDataError,
            EmailInvalidTokenDataError,
            EmailMissingAppCredentialsError,
            EmailDuplicateAccountLabelError,
        ],
    )
    def test_config_subclasses_inherit_email_config_error(self, cls):
        assert issubclass(cls, EmailConfigError)

    def test_email_account_not_found_inherits_email_error(self):
        assert issubclass(EmailAccountNotFoundError, EmailError)

    def test_email_recipients_missing_inherits_email_error(self):
        assert issubclass(EmailRecipientsMissingError, EmailError)

    def test_email_external_api_error_inherits_email_error(self):
        assert issubclass(EmailExternalAPIError, EmailError)


class TestAttributes:
    def test_core_error_default_message(self):
        err = CoreError()
        assert err.message == "Core error."
        assert str(err) == "Core error."

    def test_core_error_custom_message(self):
        err = CoreError("custom msg")
        assert err.message == "custom msg"
        assert str(err) == "custom msg"

    def test_core_error_detail_defaults_to_empty_dict(self):
        err = CoreError()
        assert err.detail == {}

    def test_core_error_detail_preserved(self):
        detail = {"key": "value", "num": 42}
        err = CoreError(detail=detail)
        assert err.detail == detail

    def test_core_error_str_returns_message(self):
        err = EmailAuthError("auth failed")
        assert str(err) == "auth failed"

    def test_each_error_has_unique_code(self):
        all_classes = [
            CoreError,
            EmailError,
            EmailAuthError,
            EmailConfigError,
            EmailAccountRecordError,
            EmailProviderConfigError,
            EmailInvalidExpiryError,
            EmailInvalidCredentialsDataError,
            EmailInvalidTokenDataError,
            EmailMissingAppCredentialsError,
            EmailDuplicateAccountLabelError,
            EmailAccountNotFoundError,
            EmailMissingTokenError,
            EmailMissingRefreshTokenError,
            EmailRefreshFailedError,
            EmailNotAuthenticatedError,
            EmailRecipientsMissingError,
            EmailExternalAPIError,
        ]
        codes = [cls.code for cls in all_classes]
        assert len(codes) == len(set(codes)), f"Duplicate codes found: {codes}"

    def test_each_error_has_default_message(self):
        """Every error class must define a non-empty default_message."""
        all_classes = [
            CoreError,
            EmailError,
            EmailAuthError,
            EmailConfigError,
            EmailAccountRecordError,
            EmailProviderConfigError,
            EmailInvalidExpiryError,
            EmailInvalidCredentialsDataError,
            EmailInvalidTokenDataError,
            EmailMissingAppCredentialsError,
            EmailDuplicateAccountLabelError,
            EmailAccountNotFoundError,
            EmailMissingTokenError,
            EmailMissingRefreshTokenError,
            EmailRefreshFailedError,
            EmailNotAuthenticatedError,
            EmailRecipientsMissingError,
            EmailExternalAPIError,
        ]
        for cls in all_classes:
            assert cls.default_message, f"{cls.__name__} has empty default_message"

    def test_error_instance_is_catchable_as_exception(self):
        with pytest.raises(Exception):
            raise EmailAuthError("boom")

    def test_error_instance_is_catchable_as_core_error(self):
        with pytest.raises(CoreError):
            raise EmailMissingTokenError()
