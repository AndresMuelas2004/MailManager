"""
Unit tests for emails_service.sync_email_metadata and emails_service.send_email.

All external dependencies are monkeypatched so tests run without DB or provider APIs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.errors.exceptions import (
    AccountNotConnected,
    AccountNotFound,
    EmailFetchError,
    EmailSendError,
    ExternalAPIError,
)
# Note: EmailExternalAPIError maps to ExternalAPIError via _CORE_TO_API_MAP,
# while generic (non-CoreError) exceptions fall back to the caller-specified fallback.
from api.services import emails_service
from core.email import EmailManager, SyncResult
from core.email.errors import EmailAuthError, EmailExternalAPIError
from tests.shared.email_fakes import FakeEmailClient, build_metadata


_MAILBOX_ID = "mb1"
_ACCOUNT_ID = "acc1"
_USER_ID = "user1"
_PROVIDER = "gmail"
_LABEL = f"{_MAILBOX_ID}__{_ACCOUNT_ID}"


def _fake_account(account_id=_ACCOUNT_ID, provider=_PROVIDER) -> dict:
    return {
        "account_id": account_id,
        "mailbox_id": _MAILBOX_ID,
        "provider": provider,
        "display_label": f"{provider}:{account_id}",
    }


def _patch_common(monkeypatch, *, fake_client_kwargs=None):
    """Apply common monkeypatches for emails_service tests."""
    monkeypatch.setattr(
        emails_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    monkeypatch.setattr(
        emails_service.account_store, "list_by_mailbox",
        lambda _mb: [_fake_account()],
    )
    monkeypatch.setattr(
        emails_service.account_store, "get",
        lambda _mb, _aid: _fake_account() if _aid == _ACCOUNT_ID else None,
    )
    monkeypatch.setattr(
        emails_service, "load_wrapped_app_credentials",
        lambda _prov: {"client_id": "cid", "client_secret": "cs"},
    )
    monkeypatch.setattr(
        emails_service, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: {"access_token": "at", "refresh_token": "rt"},
    )
    monkeypatch.setattr(
        emails_service.account_store, "upsert_tokens",
        lambda *_a, **_kw: None,
    )

    kwargs = fake_client_kwargs or {}

    def _build(accounts):
        manager = EmailManager()
        for acc in accounts:
            mid = str(acc.get("mailbox_id", ""))
            aid = str(acc.get("account_id", ""))
            label = f"{mid}__{aid}"
            manager.add_client(FakeEmailClient(
                label,
                metadata=[build_metadata()],
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                **kwargs,
            ))
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build)

    # Stub persistence helpers
    monkeypatch.setattr(emails_service, "persist_email_metadata_batch", lambda _aid, _meta: len(_meta))
    monkeypatch.setattr(emails_service, "delete_email_metadata_batch", lambda _aid, _ids: len(_ids))
    monkeypatch.setattr(emails_service, "update_email_metadata_labels_batch", lambda _aid, _lu: len(_lu))
    monkeypatch.setattr(emails_service, "load_sync_cursors", lambda _lookup: {})
    monkeypatch.setattr(emails_service, "update_sync_cursor", lambda _mb, _acc, _cur: None)


# ==================================================================
# sync_email_metadata
# ==================================================================


class TestSyncEmailMetadata:

    def test_happy_path(self, monkeypatch):
        _patch_common(monkeypatch)
        result = emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert result.total_synced >= 0
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == _ACCOUNT_ID

    def test_empty_accounts_returns_zero(self, monkeypatch):
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            emails_service.account_store, "list_by_mailbox",
            lambda _mb: [],
        )

        def _build_empty(accounts):
            return EmailManager()

        monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_empty)
        result = emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert result.total_synced == 0

    def test_auth_error_raises_account_not_connected(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        with pytest.raises(AccountNotConnected):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)

    def test_fetch_core_error_uses_centralized_mapping(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "fetch_exc": EmailExternalAPIError("API fail"),
        })
        with pytest.raises(ExternalAPIError):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)

    def test_fetch_generic_exception_raises_email_fetch_error(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "fetch_exc": RuntimeError("unexpected"),
        })
        with pytest.raises(EmailFetchError):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)

    def test_persists_refreshed_tokens(self, monkeypatch):
        _patch_common(monkeypatch)
        upsert_calls = []
        monkeypatch.setattr(
            emails_service.account_store, "upsert_tokens",
            lambda *args, **kwargs: upsert_calls.append(args),
        )
        # FakeEmailClient returns auth_return by default on authenticate_silent,
        # so manager.authenticate_all_silent will return updated tokens
        # only when the client returns non-None from authenticate_silent.
        # For this test, we use auth_silent_return to force token refresh.

        def _build_refreshing(accounts):
            manager = EmailManager()
            for acc in accounts:
                mid = str(acc.get("mailbox_id", ""))
                aid = str(acc.get("account_id", ""))
                label = f"{mid}__{aid}"
                manager.add_client(FakeEmailClient(
                    label,
                    metadata=[build_metadata()],
                    auth_silent_return={"access_token": "new_tok", "refresh_token": "new_ref"},
                ))
            return manager

        monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_refreshing)
        emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert len(upsert_calls) >= 1

    def test_sync_cursors_loaded(self, monkeypatch):
        _patch_common(monkeypatch)
        load_calls = []
        original_load = emails_service.load_sync_cursors
        monkeypatch.setattr(
            emails_service, "load_sync_cursors",
            lambda lookup: (load_calls.append(lookup), {})[1],
        )
        emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert len(load_calls) == 1

    def test_metadata_persisted(self, monkeypatch):
        _patch_common(monkeypatch)
        persist_calls = []
        monkeypatch.setattr(
            emails_service, "persist_email_metadata_batch",
            lambda aid, meta: (persist_calls.append((aid, meta)), len(meta))[1],
        )
        emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert len(persist_calls) >= 1


# ==================================================================
# send_email
# ==================================================================


class TestSendEmail:

    def _make_payload(self, account_id=_ACCOUNT_ID):
        from api.schemas.email import EmailSendRequest
        return EmailSendRequest(
            account_id=account_id,
            subject="Hello",
            body="World",
            recipients=["dest@example.com"],
        )

    def test_happy_path(self, monkeypatch):
        _patch_common(monkeypatch)
        result = emails_service.send_email(_MAILBOX_ID, self._make_payload(), _USER_ID)
        assert result == {"status": "sent"}

    def test_account_not_found_raises_404(self, monkeypatch):
        _patch_common(monkeypatch)
        with pytest.raises(AccountNotFound):
            emails_service.send_email(
                _MAILBOX_ID, self._make_payload("nonexistent"), _USER_ID,
            )

    def test_auth_error_raises_account_not_connected(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        with pytest.raises(AccountNotConnected):
            emails_service.send_email(_MAILBOX_ID, self._make_payload(), _USER_ID)

    def test_send_core_error_translated(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "send_exc": EmailExternalAPIError("SMTP reject"),
        })
        with pytest.raises(ExternalAPIError):
            emails_service.send_email(_MAILBOX_ID, self._make_payload(), _USER_ID)

    def test_send_generic_exception_raises_email_send_error(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "send_exc": RuntimeError("unexpected"),
        })
        with pytest.raises(EmailSendError):
            emails_service.send_email(_MAILBOX_ID, self._make_payload(), _USER_ID)

    def test_persists_refreshed_tokens(self, monkeypatch):
        _patch_common(monkeypatch)
        upsert_calls = []
        monkeypatch.setattr(
            emails_service.account_store, "upsert_tokens",
            lambda *args, **kwargs: upsert_calls.append(args),
        )

        def _build_refreshing(accounts):
            manager = EmailManager()
            for acc in accounts:
                mid = str(acc.get("mailbox_id", ""))
                aid = str(acc.get("account_id", ""))
                label = f"{mid}__{aid}"
                manager.add_client(FakeEmailClient(
                    label,
                    auth_silent_return={"access_token": "new_tok", "refresh_token": "new_ref"},
                ))
            return manager

        monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_refreshing)
        emails_service.send_email(_MAILBOX_ID, self._make_payload(), _USER_ID)
        assert len(upsert_calls) >= 1
