"""
Unit tests for the mailboxes service layer.

All database stores are monkeypatched to avoid real DB calls.
"""

from __future__ import annotations

import pytest

from api.errors.exceptions import ApiError, DatabaseQueryError, MailboxNotFound
from api.schemas.mailbox import MailboxCreate, MailboxOut
from api.services import mailboxes_service
from database import QueryError


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_FAKE_MAILBOX = {
    "mailbox_id": "00000000-0000-0000-0000-000000000001",
    "display_name": "Test Mailbox",
    "owner_user_id": "00000000-0000-0000-0000-000000000002",
    "created_at": "2025-01-01T00:00:00+00:00",
}


class FakeMailboxStore:
    def __init__(self, *, records=None, create_return=None):
        self._records = list(records or [])
        self._create_return = create_return
        self.deleted_ids: list[str] = []

    def create(self, record):
        if self._create_return is not None:
            return self._create_return
        return {**record, "created_at": "2025-01-01T00:00:00+00:00"}

    def list_by_owner(self, user_id):
        return [r for r in self._records if r["owner_user_id"] == user_id]

    def delete(self, mailbox_id):
        self.deleted_ids.append(mailbox_id)


class FakeMailboxStoreRaising:
    """Store that raises on every method."""

    def __init__(self, exc):
        self._exc = exc

    def create(self, record):
        raise self._exc

    def list_by_owner(self, user_id):
        raise self._exc

    def delete(self, mailbox_id):
        raise self._exc


# ------------------------------------------------------------------
# create_mailbox
# ------------------------------------------------------------------


class TestCreateMailbox:

    def test_happy_path_returns_mailbox_out(self, monkeypatch):
        monkeypatch.setattr(mailboxes_service, "mailbox_store", FakeMailboxStore())
        payload = MailboxCreate(display_name="New MB")
        result = mailboxes_service.create_mailbox(payload, "user-1")
        assert isinstance(result, MailboxOut)
        assert result.display_name == "New MB"
        assert result.owner_user_id == "user-1"

    def test_database_error_translated(self, monkeypatch):
        store = FakeMailboxStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        payload = MailboxCreate(display_name="X")
        with pytest.raises(DatabaseQueryError):
            mailboxes_service.create_mailbox(payload, "user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        store = FakeMailboxStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        payload = MailboxCreate(display_name="X")
        with pytest.raises(ApiError, match="Failed to create mailbox"):
            mailboxes_service.create_mailbox(payload, "user-1")


# ------------------------------------------------------------------
# list_mailboxes
# ------------------------------------------------------------------


class TestListMailboxes:

    def test_happy_path_returns_list(self, monkeypatch):
        store = FakeMailboxStore(records=[_FAKE_MAILBOX])
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        result = mailboxes_service.list_mailboxes(_FAKE_MAILBOX["owner_user_id"])
        assert len(result) == 1
        assert isinstance(result[0], MailboxOut)

    def test_empty_list_returns_empty(self, monkeypatch):
        store = FakeMailboxStore()
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        result = mailboxes_service.list_mailboxes("user-1")
        assert result == []

    def test_database_error_translated(self, monkeypatch):
        store = FakeMailboxStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        with pytest.raises(DatabaseQueryError):
            mailboxes_service.list_mailboxes("user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        store = FakeMailboxStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        with pytest.raises(ApiError, match="Failed to list mailboxes"):
            mailboxes_service.list_mailboxes("user-1")


# ------------------------------------------------------------------
# get_mailbox
# ------------------------------------------------------------------


class TestGetMailbox:

    def test_happy_path_returns_mailbox(self, monkeypatch):
        monkeypatch.setattr(
            mailboxes_service, "ensure_mailbox_access",
            lambda mid, uid: _FAKE_MAILBOX,
        )
        result = mailboxes_service.get_mailbox("mb-1", "user-1")
        assert isinstance(result, MailboxOut)
        assert result.mailbox_id == _FAKE_MAILBOX["mailbox_id"]


# ------------------------------------------------------------------
# delete_mailbox
# ------------------------------------------------------------------


class TestDeleteMailbox:

    def test_happy_path_returns_deleted_status(self, monkeypatch):
        store = FakeMailboxStore()
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        monkeypatch.setattr(
            mailboxes_service, "ensure_mailbox_access",
            lambda mid, uid: _FAKE_MAILBOX,
        )
        result = mailboxes_service.delete_mailbox("mb-1", "user-1")
        assert result == {"status": "deleted"}
        assert "mb-1" in store.deleted_ids

    def test_database_error_on_delete_translated(self, monkeypatch):
        store = FakeMailboxStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        monkeypatch.setattr(
            mailboxes_service, "ensure_mailbox_access",
            lambda mid, uid: _FAKE_MAILBOX,
        )
        with pytest.raises(DatabaseQueryError):
            mailboxes_service.delete_mailbox("mb-1", "user-1")

    def test_generic_exception_on_delete_raises_api_error(self, monkeypatch):
        store = FakeMailboxStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(mailboxes_service, "mailbox_store", store)
        monkeypatch.setattr(
            mailboxes_service, "ensure_mailbox_access",
            lambda mid, uid: _FAKE_MAILBOX,
        )
        with pytest.raises(ApiError, match="Failed to delete mailbox"):
            mailboxes_service.delete_mailbox("mb-1", "user-1")
