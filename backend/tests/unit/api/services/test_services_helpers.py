"""
Unit tests for services_helpers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.errors.exceptions import (
    AccountMisconfigured,
    ApiError,
    DatabaseQueryError,
    Forbidden,
)
from api.services.services_helpers import (
    build_manager_for_accounts,
    catch_database_errors,
    ensure_mailbox_access,
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
            with pytest.raises(AccountMisconfigured, match="RuntimeError"):
                build_manager_for_accounts([account])


# ------------------------------------------------------------------
# catch_database_errors — except Exception fallback
# ------------------------------------------------------------------

class TestCatchDatabaseErrorsGenericFallback:

    def test_generic_exception_uses_default_fallback(self):
        """A non-DatabaseError inside catch_database_errors → default ApiError."""
        with pytest.raises(ApiError, match="RuntimeError"):
            with catch_database_errors():
                raise RuntimeError("unexpected db boom")

    def test_generic_exception_uses_custom_fallback(self):
        """A non-DatabaseError with fallback=DatabaseQueryError → that type."""
        with pytest.raises(DatabaseQueryError, match="ValueError"):
            with catch_database_errors(fallback=DatabaseQueryError):
                raise ValueError("bad value")
