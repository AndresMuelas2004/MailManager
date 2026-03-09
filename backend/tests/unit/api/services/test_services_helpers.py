"""
Unit tests for services_helpers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    ApiError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
)
from api.services.services_helpers import (
    build_manager_for_accounts,
    ensure_mailbox_access,
    raise_on_silent_auth_errors,
    translate_connect_error,
    translate_core_error,
)
from core.email.errors import (
    EmailAuthError,
    EmailExternalAPIError,
    EmailMissingTokenError,
)


class TestEnsureMailboxAccess:

    def test_null_owner_raises_forbidden(self):
        """A mailbox with owner_user_id=None must be rejected."""
        fake_record = {
            "mailbox_id": "mb-1",
            "display_name": "Orphan",
            "owner_user_id": None,
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = fake_record
            with pytest.raises(Forbidden):
                ensure_mailbox_access("mb-1", "some-user-id")

    def test_mismatched_owner_raises_forbidden(self):
        """A mailbox owned by a different user must be rejected."""
        fake_record = {
            "mailbox_id": "mb-1",
            "display_name": "Other's MB",
            "owner_user_id": "owner-a",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = fake_record
            with pytest.raises(Forbidden):
                ensure_mailbox_access("mb-1", "owner-b")

    def test_matching_owner_returns_record(self):
        """A mailbox owned by the requesting user is returned."""
        fake_record = {
            "mailbox_id": "mb-1",
            "display_name": "My MB",
            "owner_user_id": "owner-a",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = fake_record
            result = ensure_mailbox_access("mb-1", "owner-a")
        assert result == fake_record


# ------------------------------------------------------------------
# build_manager_for_accounts — except Exception fallback
# ------------------------------------------------------------------

class TestBuildManagerUnexpectedException:

    def test_unexpected_exception_raises_account_misconfigured(self):
        """A non-CoreError from add_account_record → AccountMisconfigured."""
        account = {"mailbox_id": "mb-1", "account_id": "acc-1", "provider": "gmail"}
        with patch(
            "api.services.services_helpers.EmailManager"
        ) as mock_manager_cls:
            mock_manager_cls.return_value.add_account_record.side_effect = (
                RuntimeError("unexpected boom")
            )
            with pytest.raises(AccountMisconfigured, match="Failed to register account"):
                build_manager_for_accounts([account])


# ------------------------------------------------------------------
# ensure_mailbox_access — store returns None
# ------------------------------------------------------------------

class TestEnsureMailboxAccessNotFound:

    def test_mailbox_not_found_when_store_returns_none(self):
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = None
            with pytest.raises(MailboxNotFound, match="not found"):
                ensure_mailbox_access("mb-1", "some-user-id")


# ------------------------------------------------------------------
# raise_on_silent_auth_errors
# ------------------------------------------------------------------

class TestRaiseOnSilentAuthErrors:

    def test_empty_errors_returns_none(self):
        assert raise_on_silent_auth_errors({}) is None

    def test_single_auth_error_raises_account_not_connected(self):
        errors = {"mb__acc1": EmailAuthError("token expired")}
        with pytest.raises(AccountNotConnected) as exc_info:
            raise_on_silent_auth_errors(errors)
        assert "mb__acc1" in exc_info.value.detail["account_labels"]

    def test_multiple_auth_errors_aggregated(self):
        errors = {
            "mb__acc1": EmailAuthError("expired"),
            "mb__acc2": EmailMissingTokenError("missing"),
        }
        with pytest.raises(AccountNotConnected) as exc_info:
            raise_on_silent_auth_errors(errors)
        labels = exc_info.value.detail["account_labels"]
        assert "mb__acc1" in labels
        assert "mb__acc2" in labels

    def test_non_auth_core_error_translated_and_raised(self):
        errors = {"mb__acc1": EmailExternalAPIError("API fail")}
        with pytest.raises(ExternalAPIError):
            raise_on_silent_auth_errors(errors)

    def test_non_core_error_raises_fallback_api_error(self):
        errors = {"mb__acc1": RuntimeError("something")}
        with pytest.raises(ApiError):
            raise_on_silent_auth_errors(errors)

    def test_reasons_included_in_detail(self):
        errors = {"mb__acc1": EmailAuthError("token expired")}
        with pytest.raises(AccountNotConnected) as exc_info:
            raise_on_silent_auth_errors(errors)
        assert "reasons" in exc_info.value.detail
        assert exc_info.value.detail["reasons"]["mb__acc1"] == "token expired"


# ------------------------------------------------------------------
# translate_connect_error
# ------------------------------------------------------------------

class TestTranslateConnectError:

    def test_email_auth_error_returns_account_connect_auth_error(self):
        exc = EmailAuthError("Token rejected.")
        result = translate_connect_error(exc)
        assert isinstance(result, AccountConnectAuthError)
        assert result.detail.get("core_code") == EmailAuthError.code

    def test_other_core_error_uses_standard_mapping(self):
        exc = EmailExternalAPIError("API fail")
        result = translate_connect_error(exc)
        assert isinstance(result, ExternalAPIError)

    def test_non_core_error_uses_fallback(self):
        exc = RuntimeError("unexpected")
        result = translate_connect_error(exc)
        assert isinstance(result, AccountConnectAuthError)
