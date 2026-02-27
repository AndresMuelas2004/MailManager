"""
Unit tests for services_helpers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.errors.exceptions import Forbidden
from api.services.services_helpers import ensure_mailbox_access


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
