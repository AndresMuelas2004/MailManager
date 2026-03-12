"""
Unit tests for the accounts service layer.

All database stores and external helpers are monkeypatched to avoid real calls.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountNotFound,
    ApiError,
    DatabaseQueryError,
)
from api.schemas.account import AccountConnectResponse, AccountCreate, AccountOut, AccountUpdate
from api.services import accounts_service
from core.email import EmailAuthError, EmailManager
from database import QueryError
from tests.shared.email_fakes import FakeEmailClient


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_FAKE_RECORD = {
    "account_id": "00000000-0000-0000-0000-000000000001",
    "mailbox_id": "00000000-0000-0000-0000-000000000002",
    "provider": "gmail",
    "display_label": "my-gmail",
    "config": {},
}


class FakeAccountStore:
    """In-memory account store for unit tests."""

    def __init__(self, *, records=None, get_return=None, tokens=None):
        self._records = list(records or [])
        self._get_return = get_return
        self._tokens = tokens
        self.deleted: list[tuple[str, str]] = []
        self.upserted_tokens: list[tuple] = []

    def list_by_mailbox(self, mailbox_id):
        return [r for r in self._records if r["mailbox_id"] == mailbox_id]

    def get(self, mailbox_id, account_id):
        return dict(self._get_return) if self._get_return else None

    def upsert(self, record):
        return {**record}

    def delete(self, mailbox_id, account_id):
        self.deleted.append((mailbox_id, account_id))

    def upsert_tokens(self, mailbox_id, account_id, provider, token_payload):
        self.upserted_tokens.append((mailbox_id, account_id, provider, token_payload))


class FakeAccountStoreRaising:
    """Account store that raises on every method."""

    def __init__(self, exc, *, get_return=None):
        self._exc = exc
        self._get_return = get_return

    def list_by_mailbox(self, mailbox_id):
        raise self._exc

    def get(self, mailbox_id, account_id):
        if self._get_return is not None:
            return dict(self._get_return)
        raise self._exc

    def upsert(self, record):
        raise self._exc

    def delete(self, mailbox_id, account_id):
        raise self._exc

    def upsert_tokens(self, mailbox_id, account_id, provider, token_payload):
        raise self._exc


def _patch_access(monkeypatch):
    """Bypass ensure_mailbox_access in all tests."""
    monkeypatch.setattr(
        accounts_service, "ensure_mailbox_access",
        lambda mid, uid: {"mailbox_id": mid, "owner_user_id": uid},
    )


# ------------------------------------------------------------------
# _resolve_display_label (pure function)
# ------------------------------------------------------------------


class TestResolveDisplayLabel:

    def test_returns_display_label_when_present(self):
        record = {"display_label": "Custom", "provider": "gmail", "account_id": "a1"}
        assert accounts_service._resolve_display_label(record) == "Custom"

    def test_falls_back_to_provider_account_id(self):
        record = {"provider": "outlook", "account_id": "a2"}
        assert accounts_service._resolve_display_label(record) == "outlook:a2"


# ------------------------------------------------------------------
# list_accounts
# ------------------------------------------------------------------


class TestListAccounts:

    def test_happy_path_returns_list(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(records=[_FAKE_RECORD])
        monkeypatch.setattr(accounts_service, "account_store", store)
        result = accounts_service.list_accounts(_FAKE_RECORD["mailbox_id"], "user-1")
        assert len(result) == 1
        assert isinstance(result[0], AccountOut)

    def test_database_error_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(DatabaseQueryError):
            accounts_service.list_accounts("mb-1", "user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(ApiError, match="Failed to list accounts"):
            accounts_service.list_accounts("mb-1", "user-1")


# ------------------------------------------------------------------
# create_account
# ------------------------------------------------------------------


class TestCreateAccount:

    def test_happy_path_returns_created_account(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore()
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountCreate(provider="gmail", display_label="my-acc", config={})
        result = accounts_service.create_account("mb-1", payload, "user-1")
        assert isinstance(result, AccountOut)
        assert result.provider == "gmail"

    def test_database_error_on_upsert_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountCreate(provider="gmail", display_label="x", config={})
        with pytest.raises(DatabaseQueryError):
            accounts_service.create_account("mb-1", payload, "user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountCreate(provider="gmail", display_label="x", config={})
        with pytest.raises(ApiError, match="Failed to create account"):
            accounts_service.create_account("mb-1", payload, "user-1")


# ------------------------------------------------------------------
# get_account
# ------------------------------------------------------------------


class TestGetAccount:

    def test_happy_path_returns_account(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=_FAKE_RECORD)
        monkeypatch.setattr(accounts_service, "account_store", store)
        result = accounts_service.get_account("mb-1", "acc-1", "user-1")
        assert isinstance(result, AccountOut)

    def test_not_found_when_none(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=None)
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(AccountNotFound):
            accounts_service.get_account("mb-1", "acc-1", "user-1")

    def test_database_error_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(DatabaseQueryError):
            accounts_service.get_account("mb-1", "acc-1", "user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(ApiError, match="Failed to look up account"):
            accounts_service.get_account("mb-1", "acc-1", "user-1")


# ------------------------------------------------------------------
# update_account
# ------------------------------------------------------------------


class TestUpdateAccount:

    def test_happy_path_updates_display_label(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=_FAKE_RECORD)
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountUpdate(display_label="renamed")
        result = accounts_service.update_account("mb-1", "acc-1", payload, "user-1")
        assert isinstance(result, AccountOut)
        assert result.display_label == "renamed"

    def test_not_found_when_none(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=None)
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountUpdate(display_label="x")
        with pytest.raises(AccountNotFound):
            accounts_service.update_account("mb-1", "acc-1", payload, "user-1")

    def test_database_error_on_get_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountUpdate(display_label="x")
        with pytest.raises(DatabaseQueryError):
            accounts_service.update_account("mb-1", "acc-1", payload, "user-1")

    def test_database_error_on_upsert_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        # get succeeds, upsert fails
        store = FakeAccountStoreRaising(QueryError("DB fail"), get_return=_FAKE_RECORD)
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountUpdate(display_label="x")
        with pytest.raises(DatabaseQueryError):
            accounts_service.update_account("mb-1", "acc-1", payload, "user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        payload = AccountUpdate(display_label="x")
        with pytest.raises(ApiError, match="Failed to look up account"):
            accounts_service.update_account("mb-1", "acc-1", payload, "user-1")


# ------------------------------------------------------------------
# delete_account
# ------------------------------------------------------------------


class TestDeleteAccount:

    def test_happy_path_returns_deleted_status(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=_FAKE_RECORD)
        monkeypatch.setattr(accounts_service, "account_store", store)
        result = accounts_service.delete_account("mb-1", "acc-1", "user-1")
        assert result == {"status": "deleted"}

    def test_not_found_when_none(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=None)
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(AccountNotFound):
            accounts_service.delete_account("mb-1", "acc-1", "user-1")

    def test_database_error_on_get_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(QueryError("DB fail"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(DatabaseQueryError):
            accounts_service.delete_account("mb-1", "acc-1", "user-1")

    def test_database_error_on_delete_translated(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(QueryError("DB fail"), get_return=_FAKE_RECORD)
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(DatabaseQueryError):
            accounts_service.delete_account("mb-1", "acc-1", "user-1")

    def test_generic_exception_raises_api_error(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStoreRaising(RuntimeError("boom"))
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(ApiError, match="Failed to look up account"):
            accounts_service.delete_account("mb-1", "acc-1", "user-1")


# ------------------------------------------------------------------
# connect_account
# ------------------------------------------------------------------


class TestConnectAccount:

    _MID = _FAKE_RECORD["mailbox_id"]
    _AID = _FAKE_RECORD["account_id"]

    def _patch_connect_deps(self, monkeypatch, *, store=None, auth_exc=None):
        """Wire all connect_account dependencies."""
        _patch_access(monkeypatch)
        if store is None:
            store = FakeAccountStore(get_return=_FAKE_RECORD)
        monkeypatch.setattr(accounts_service, "account_store", store)

        fake_creds = {"client_id": "fake", "client_secret": SecretStr("fake")}
        monkeypatch.setattr(
            accounts_service, "load_wrapped_app_credentials", lambda p: fake_creds,
        )
        monkeypatch.setattr(accounts_service, "unwrap_secret", lambda v: v)

        def _build_manager(accounts):
            manager = EmailManager()
            for acc in accounts:
                mid = str(acc.get("mailbox_id") or "")
                aid = str(acc.get("account_id") or "")
                label = f"{mid}__{aid}"
                manager.add_client(
                    FakeEmailClient(
                        label,
                        auth_exc=auth_exc,
                        auth_return={"access_token": "tok", "refresh_token": "ref"},
                    )
                )
            return manager

        monkeypatch.setattr(accounts_service, "build_manager_for_accounts", _build_manager)

    def test_happy_path_returns_connect_response(self, monkeypatch):
        self._patch_connect_deps(monkeypatch)
        result = accounts_service.connect_account(self._MID, self._AID, "user-1")
        assert isinstance(result, AccountConnectResponse)
        assert result.connected is True

    def test_not_found_when_none(self, monkeypatch):
        _patch_access(monkeypatch)
        store = FakeAccountStore(get_return=None)
        monkeypatch.setattr(accounts_service, "account_store", store)
        with pytest.raises(AccountNotFound):
            accounts_service.connect_account(self._MID, self._AID, "user-1")

    def test_core_error_during_connect_translated(self, monkeypatch):
        self._patch_connect_deps(monkeypatch, auth_exc=EmailAuthError("token rejected"))
        with pytest.raises(AccountConnectAuthError):
            accounts_service.connect_account(self._MID, self._AID, "user-1")

    def test_generic_exception_during_connect(self, monkeypatch):
        self._patch_connect_deps(monkeypatch, auth_exc=RuntimeError("crash"))
        with pytest.raises(AccountConnectAuthError, match="Failed to connect account"):
            accounts_service.connect_account(self._MID, self._AID, "user-1")

    def test_database_error_on_upsert_tokens_translated(self, monkeypatch):
        self._patch_connect_deps(monkeypatch)
        store = accounts_service.account_store

        def _fail(*args, **kwargs):
            raise QueryError("DB fail")

        monkeypatch.setattr(store, "upsert_tokens", _fail)
        with pytest.raises(DatabaseQueryError):
            accounts_service.connect_account(self._MID, self._AID, "user-1")

    def test_generic_exception_on_upsert_tokens(self, monkeypatch):
        self._patch_connect_deps(monkeypatch)
        store = accounts_service.account_store

        def _fail(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(store, "upsert_tokens", _fail)
        with pytest.raises(ApiError, match="Failed to persist tokens"):
            accounts_service.connect_account(self._MID, self._AID, "user-1")
