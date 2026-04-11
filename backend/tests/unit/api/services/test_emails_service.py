"""
Unit tests for emails_service.sync_email_metadata, emails_service.send_email,
emails_service.update_read_status, emails_service.move_to_spam,
emails_service.restore_from_spam, and emails_service.get_email_full_content.

All external dependencies are monkeypatched so tests run without DB or provider APIs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.errors.exceptions import (
    AccountNotConnected,
    AccountNotFound,
    EmailContentFetchError,
    EmailFetchError,
    EmailListError,
    EmailNotFound,
    EmailNotInTrash,
    EmailSendError,
    ExternalAPIError,
    MoveToTrashError,
    ReadStatusUpdateError,
    SpamMoveError,
    SpamRestoreError,
    TrashOperationError,
)
from api.schemas.email import ReadStatusItem, ReadStatusRequest, SpamItem, SpamRequest
# Note: EmailExternalAPIError maps to ExternalAPIError via _CORE_TO_API_MAP,
# while generic (non-CoreError) exceptions fall back to the caller-specified fallback.
from api.services import emails_service
from core.email import EmailContent, EmailManager, SyncResult
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
        assert result.total_synced == 1
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

    def test_list_by_mailbox_database_error(self, monkeypatch):
        from database import DatabaseError
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            emails_service.account_store, "list_by_mailbox",
            MagicMock(side_effect=DatabaseError("db fail")),
        )
        from api.errors.exceptions import ApiError
        with pytest.raises(ApiError):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)

    def test_list_by_mailbox_unexpected_error(self, monkeypatch):
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            emails_service.account_store, "list_by_mailbox",
            MagicMock(side_effect=RuntimeError("unexpected")),
        )
        from api.errors.exceptions import ApiError
        with pytest.raises(ApiError):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)

    def test_persist_tokens_database_error(self, monkeypatch):
        from database import DatabaseError
        _patch_common(monkeypatch)

        def _build_refreshing(accounts):
            from core.email import EmailManager
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
        monkeypatch.setattr(
            emails_service.account_store, "upsert_tokens",
            MagicMock(side_effect=DatabaseError("db fail")),
        )
        from api.errors.exceptions import ApiError
        with pytest.raises(ApiError):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)

    def test_single_account_happy_path(self, monkeypatch):
        _patch_common(monkeypatch)
        result = emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)
        assert result.total_synced == 1
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == _ACCOUNT_ID

    def test_single_account_not_found_raises(self, monkeypatch):
        _patch_common(monkeypatch)
        with pytest.raises(AccountNotFound, match="during metadata sync"):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID, "nonexistent")

    def test_single_account_db_error_on_lookup(self, monkeypatch):
        from database import DatabaseError
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            emails_service.account_store, "get",
            MagicMock(side_effect=DatabaseError("db fail")),
        )
        from api.errors.exceptions import ApiError
        with pytest.raises(ApiError):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_single_account_unexpected_error_on_lookup(self, monkeypatch):
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            emails_service.account_store, "get",
            MagicMock(side_effect=RuntimeError("unexpected")),
        )
        with pytest.raises(EmailFetchError, match="Failed to look up account for metadata sync"):
            emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)


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

    def test_send_generic_exception_raises_external_api_error(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "send_exc": RuntimeError("unexpected"),
        })
        with pytest.raises(ExternalAPIError):
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

    def test_persists_sent_metadata(self, monkeypatch):
        """After send, metadata is persisted with the correct account_id."""
        _patch_common(monkeypatch)
        persist_calls = []
        monkeypatch.setattr(
            emails_service, "persist_email_metadata_batch",
            lambda aid, meta: (persist_calls.append((aid, meta)), len(meta))[1],
        )
        emails_service.send_email(_MAILBOX_ID, self._make_payload(), _USER_ID)
        assert len(persist_calls) == 1
        aid, meta_list = persist_calls[0]
        assert aid == _ACCOUNT_ID
        assert len(meta_list) == 1
        assert meta_list[0].box == "SENT"


# ==================================================================
# _reconcile_ghost_emails
# ==================================================================


class TestReconciliation:

    def test_full_sync_triggers_reconciliation(self, monkeypatch):
        """Bootstrap (is_full_sync=True) should trigger ghost reconciliation."""
        _patch_common(monkeypatch, fake_client_kwargs={
            "is_full_sync": True,
            "existing_message_ids": ["m1"],
        })
        # DB has m1 + m_ghost; bootstrap only returned m1
        monkeypatch.setattr(
            emails_service, "load_stored_message_ids",
            lambda _aid: ["m1", "m_ghost"],
        )
        delete_calls = []
        monkeypatch.setattr(
            emails_service, "delete_email_metadata_batch",
            lambda aid, ids: (delete_calls.append((aid, ids)), len(ids))[1],
        )
        result = emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        # m_ghost should have been deleted
        assert any("m_ghost" in ids for _, ids in delete_calls)

    def test_incremental_skips_reconciliation(self, monkeypatch):
        """Incremental (is_full_sync=False) should not trigger reconciliation."""
        _patch_common(monkeypatch, fake_client_kwargs={
            "is_full_sync": False,
        })
        load_calls = []
        monkeypatch.setattr(
            emails_service, "load_stored_message_ids",
            lambda _aid: (load_calls.append(_aid), [])[1],
        )
        emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert load_calls == []

    def test_verification_error_skips_gracefully(self, monkeypatch):
        """If verify_message_existence fails, reconciliation should skip."""
        _patch_common(monkeypatch, fake_client_kwargs={
            "is_full_sync": True,
            "verify_exc": RuntimeError("API down"),
        })
        monkeypatch.setattr(
            emails_service, "load_stored_message_ids",
            lambda _aid: ["m1", "m_ghost"],
        )
        # Should not raise
        result = emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        assert result.total_synced >= 0

    def test_no_ghosts_means_no_deletes(self, monkeypatch):
        """If all stored IDs are in bootstrap set, no deletes should happen."""
        _patch_common(monkeypatch, fake_client_kwargs={
            "is_full_sync": True,
            "existing_message_ids": ["m1"],
        })
        # DB has exactly the same IDs as bootstrap
        monkeypatch.setattr(
            emails_service, "load_stored_message_ids",
            lambda _aid: ["m1"],
        )
        delete_calls = []
        monkeypatch.setattr(
            emails_service, "delete_email_metadata_batch",
            lambda aid, ids: (delete_calls.append((aid, ids)), len(ids))[1],
        )
        emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        # No ghost deletes (only the normal deletes call with empty list)
        ghost_deletes = [ids for _, ids in delete_calls if ids and "m1" not in ids]
        assert ghost_deletes == []

    def test_all_suspects_are_ghosts(self, monkeypatch):
        """When none of the suspect IDs exist at provider, all are deleted."""
        _patch_common(monkeypatch, fake_client_kwargs={
            "is_full_sync": True,
            "existing_message_ids": [],  # nothing exists at provider
        })
        monkeypatch.setattr(
            emails_service, "load_stored_message_ids",
            lambda _aid: ["m1", "ghost1", "ghost2"],
        )
        delete_calls = []
        monkeypatch.setattr(
            emails_service, "delete_email_metadata_batch",
            lambda aid, ids: (delete_calls.append((aid, ids)), len(ids))[1],
        )
        emails_service.sync_email_metadata(_MAILBOX_ID, _USER_ID)
        all_deleted = [mid for _, ids in delete_calls for mid in ids]
        assert "ghost1" in all_deleted
        assert "ghost2" in all_deleted


# ==================================================================
# manage_trash
# ==================================================================


class TestManageTrash:

    def _make_payload(self, action="delete", items=None):
        from api.schemas.email import TrashActionRequest, TrashItem
        if items is None:
            items = [TrashItem(provider_message_id="m1", account_id=_ACCOUNT_ID)]
        return TrashActionRequest(action=action, items=items)

    def _patch_trash_common(self, monkeypatch, *, fake_client_kwargs=None, previous_box="ALL_MAIL"):
        _patch_common(monkeypatch, fake_client_kwargs=fake_client_kwargs)
        monkeypatch.setattr(
            emails_service, "get_trash_emails_by_ids",
            lambda _aid, _ids: [
                {"provider_message_id": mid, "box": "TRASH", "previous_box": previous_box}
                for mid in _ids
            ],
        )
        monkeypatch.setattr(
            emails_service, "mark_as_deleted_batch",
            lambda _aid, _ids: len(_ids),
        )
        monkeypatch.setattr(
            emails_service, "restore_from_trash_batch",
            lambda _aid, _rows: len(_rows),
        )
        monkeypatch.setattr(
            emails_service, "restore_from_trash_discovered_batch",
            lambda _aid, _rows: len(_rows),
        )

    def test_delete_happy_path(self, monkeypatch):
        self._patch_trash_common(monkeypatch)
        result = emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("delete"), _USER_ID,
        )
        assert result.affected == 1

    def test_restore_happy_path(self, monkeypatch):
        self._patch_trash_common(monkeypatch)
        result = emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("restore"), _USER_ID,
        )
        assert result.affected == 1

    def test_delete_marks_deleted_in_db(self, monkeypatch):
        self._patch_trash_common(monkeypatch)
        mark_calls = []
        monkeypatch.setattr(
            emails_service, "mark_as_deleted_batch",
            lambda aid, ids: (mark_calls.append((aid, ids)), len(ids))[1],
        )
        emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("delete"), _USER_ID,
        )
        assert len(mark_calls) == 1
        assert mark_calls[0][0] == _ACCOUNT_ID
        assert "m1" in mark_calls[0][1]

    def test_restore_calls_restore_batch(self, monkeypatch):
        self._patch_trash_common(monkeypatch)
        restore_calls = []
        monkeypatch.setattr(
            emails_service, "restore_from_trash_batch",
            lambda aid, rows: (restore_calls.append((aid, rows)), len(rows))[1],
        )
        emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("restore"), _USER_ID,
        )
        assert len(restore_calls) == 1

    def test_partial_provider_failure_only_updates_succeeded(self, monkeypatch):
        """Provider-first: if provider only deletes 1 of 2, DB only marks 1."""
        from api.schemas.email import TrashItem
        self._patch_trash_common(monkeypatch, fake_client_kwargs={
            "delete_return": ["m1"],  # only m1 succeeds
        })
        payload = self._make_payload("delete", items=[
            TrashItem(provider_message_id="m1", account_id=_ACCOUNT_ID),
            TrashItem(provider_message_id="m2", account_id=_ACCOUNT_ID),
        ])
        result = emails_service.manage_trash(_MAILBOX_ID, payload, _USER_ID)
        assert result.affected == 1

    def test_account_not_in_mailbox_raises(self, monkeypatch):
        self._patch_trash_common(monkeypatch)
        from api.schemas.email import TrashItem
        payload = self._make_payload("delete", items=[
            TrashItem(provider_message_id="m1", account_id="nonexistent"),
        ])
        with pytest.raises(AccountNotFound):
            emails_service.manage_trash(_MAILBOX_ID, payload, _USER_ID)

    def test_email_not_in_trash_raises(self, monkeypatch):
        self._patch_trash_common(monkeypatch)
        monkeypatch.setattr(
            emails_service, "get_trash_emails_by_ids",
            lambda _aid, _ids: [],  # no emails found in trash
        )
        with pytest.raises(EmailNotInTrash):
            emails_service.manage_trash(
                _MAILBOX_ID, self._make_payload("delete"), _USER_ID,
            )

    def test_auth_error_raises_account_not_connected(self, monkeypatch):
        self._patch_trash_common(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        with pytest.raises(AccountNotConnected):
            emails_service.manage_trash(
                _MAILBOX_ID, self._make_payload("delete"), _USER_ID,
            )

    def test_core_error_translated(self, monkeypatch):
        self._patch_trash_common(monkeypatch, fake_client_kwargs={
            "delete_exc": EmailExternalAPIError("API fail"),
        })
        with pytest.raises(ExternalAPIError):
            emails_service.manage_trash(
                _MAILBOX_ID, self._make_payload("delete"), _USER_ID,
            )

    def test_generic_exception_raises_external_api_error(self, monkeypatch):
        self._patch_trash_common(monkeypatch, fake_client_kwargs={
            "delete_exc": RuntimeError("unexpected"),
        })
        with pytest.raises(ExternalAPIError):
            emails_service.manage_trash(
                _MAILBOX_ID, self._make_payload("delete"), _USER_ID,
            )

    def test_restore_null_previous_box_calls_discovered_batch(self, monkeypatch):
        """When previous_box is None, restore uses fetch_messages_metadata + discovered batch."""
        discovered_meta = build_metadata(provider_message_id="m1", box="SENT")
        self._patch_trash_common(
            monkeypatch,
            fake_client_kwargs={"fetch_messages_metadata_return": [discovered_meta]},
            previous_box=None,
        )
        discovered_calls = []
        monkeypatch.setattr(
            emails_service, "restore_from_trash_discovered_batch",
            lambda aid, rows: (discovered_calls.append((aid, rows)), len(rows))[1],
        )
        restore_calls = []
        monkeypatch.setattr(
            emails_service, "restore_from_trash_batch",
            lambda aid, rows: (restore_calls.append((aid, rows)), len(rows))[1],
        )
        result = emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("restore"), _USER_ID,
        )
        assert result.affected == 1
        assert len(discovered_calls) == 1
        assert discovered_calls[0][1][0][3] == "SENT"
        assert len(restore_calls) == 0

    def test_restore_known_previous_box_uses_normal_batch(self, monkeypatch):
        """When previous_box is known, normal restore_from_trash_batch is used."""
        self._patch_trash_common(monkeypatch, previous_box="SPAM")
        restore_calls = []
        monkeypatch.setattr(
            emails_service, "restore_from_trash_batch",
            lambda aid, rows: (restore_calls.append((aid, rows)), len(rows))[1],
        )
        discovered_calls = []
        monkeypatch.setattr(
            emails_service, "restore_from_trash_discovered_batch",
            lambda aid, rows: (discovered_calls.append((aid, rows)), len(rows))[1],
        )
        result = emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("restore"), _USER_ID,
        )
        assert result.affected == 1
        assert len(restore_calls) == 1
        assert len(discovered_calls) == 0

    def test_restore_null_previous_box_defaults_to_all_mail_on_fetch_miss(self, monkeypatch):
        """When fetch_messages_metadata returns nothing, discovered box defaults to ALL_MAIL."""
        self._patch_trash_common(
            monkeypatch,
            fake_client_kwargs={"fetch_messages_metadata_return": []},
            previous_box=None,
        )
        discovered_calls = []
        monkeypatch.setattr(
            emails_service, "restore_from_trash_discovered_batch",
            lambda aid, rows: (discovered_calls.append((aid, rows)), len(rows))[1],
        )
        emails_service.manage_trash(
            _MAILBOX_ID, self._make_payload("restore"), _USER_ID,
        )
        assert len(discovered_calls) == 1
        assert discovered_calls[0][1][0][3] == "ALL_MAIL"


# ==================================================================
# move_to_trash
# ==================================================================


class TestMoveToTrash:

    def _make_payload(self, items=None):
        from api.schemas.email import MoveToTrashRequest, TrashItem
        if items is None:
            items = [TrashItem(provider_message_id="m1", account_id=_ACCOUNT_ID)]
        return MoveToTrashRequest(items=items)

    def _patch_move_common(self, monkeypatch, *, fake_client_kwargs=None):
        _patch_common(monkeypatch, fake_client_kwargs=fake_client_kwargs)
        monkeypatch.setattr(
            emails_service, "move_to_trash_batch",
            lambda _aid, _rows: len(_rows),
        )

    def test_happy_path(self, monkeypatch):
        self._patch_move_common(monkeypatch)
        result = emails_service.move_to_trash(
            _MAILBOX_ID, self._make_payload(), _USER_ID,
        )
        assert result.affected == 1

    def test_provider_partial_failure_only_updates_succeeded(self, monkeypatch):
        """Provider-first: if provider only trashes 1 of 2, DB only updates 1."""
        from api.schemas.email import TrashItem
        self._patch_move_common(monkeypatch, fake_client_kwargs={
            "move_to_trash_return": {"m1": "m1"},  # only m1 succeeds
        })
        payload = self._make_payload(items=[
            TrashItem(provider_message_id="m1", account_id=_ACCOUNT_ID),
            TrashItem(provider_message_id="m2", account_id=_ACCOUNT_ID),
        ])
        result = emails_service.move_to_trash(_MAILBOX_ID, payload, _USER_ID)
        assert result.affected == 1

    def test_all_provider_failure_returns_zero(self, monkeypatch):
        self._patch_move_common(monkeypatch, fake_client_kwargs={
            "move_to_trash_return": {},
        })
        result = emails_service.move_to_trash(
            _MAILBOX_ID, self._make_payload(), _USER_ID,
        )
        assert result.affected == 0

    def test_account_not_in_mailbox_raises(self, monkeypatch):
        self._patch_move_common(monkeypatch)
        from api.schemas.email import TrashItem
        payload = self._make_payload(items=[
            TrashItem(provider_message_id="m1", account_id="nonexistent"),
        ])
        with pytest.raises(AccountNotFound):
            emails_service.move_to_trash(_MAILBOX_ID, payload, _USER_ID)

    def test_auth_error_raises_account_not_connected(self, monkeypatch):
        self._patch_move_common(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        with pytest.raises(AccountNotConnected):
            emails_service.move_to_trash(
                _MAILBOX_ID, self._make_payload(), _USER_ID,
            )

    def test_core_error_translated(self, monkeypatch):
        self._patch_move_common(monkeypatch, fake_client_kwargs={
            "move_to_trash_exc": EmailExternalAPIError("API fail"),
        })
        with pytest.raises(ExternalAPIError):
            emails_service.move_to_trash(
                _MAILBOX_ID, self._make_payload(), _USER_ID,
            )

    def test_generic_exception_raises_external_api_error(self, monkeypatch):
        self._patch_move_common(monkeypatch, fake_client_kwargs={
            "move_to_trash_exc": RuntimeError("unexpected"),
        })
        with pytest.raises(ExternalAPIError):
            emails_service.move_to_trash(
                _MAILBOX_ID, self._make_payload(), _USER_ID,
            )


# ==================================================================
# update_read_status
# ==================================================================

_ACCOUNT_ID_2 = "acc2"
_LABEL_2 = f"{_MAILBOX_ID}__{_ACCOUNT_ID_2}"


def _patch_read_status(monkeypatch, *, accounts=None, fake_client_kwargs=None):
    """Apply monkeypatches specific to update_read_status tests."""
    if accounts is None:
        accounts = [_fake_account()]

    monkeypatch.setattr(
        emails_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    monkeypatch.setattr(
        emails_service.account_store, "list_by_mailbox",
        lambda _mb: accounts,
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
    monkeypatch.setattr(
        emails_service, "update_email_read_status_batch",
        lambda _aid, _ids, _read: len(_ids),
    )

    kwargs = fake_client_kwargs or {}

    def _build(accs):
        manager = EmailManager()
        for acc in accs:
            mid = str(acc.get("mailbox_id", ""))
            aid = str(acc.get("account_id", ""))
            label = f"{mid}__{aid}"
            manager.add_client(FakeEmailClient(
                label,
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                **kwargs,
            ))
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build)


class TestUpdateReadStatus:

    @staticmethod
    def _make_payload(items, is_read=True):
        return ReadStatusRequest(
            is_read=is_read,
            items=[ReadStatusItem(account_id=aid, provider_message_id=mid)
                   for aid, mid in items],
        )

    def test_happy_path_single_account(self, monkeypatch):
        _patch_read_status(monkeypatch)
        payload = self._make_payload([
            (_ACCOUNT_ID, "m1"),
            (_ACCOUNT_ID, "m2"),
        ], is_read=True)
        result = emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)
        assert result.updated_count == 2
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == _ACCOUNT_ID
        assert result.accounts[0].updated == 2

    def test_happy_path_multi_account(self, monkeypatch):
        accounts = [
            _fake_account(_ACCOUNT_ID),
            _fake_account(_ACCOUNT_ID_2),
        ]
        _patch_read_status(monkeypatch, accounts=accounts)
        payload = self._make_payload([
            (_ACCOUNT_ID, "m1"),
            (_ACCOUNT_ID_2, "m2"),
        ], is_read=False)
        result = emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)
        assert result.updated_count == 2
        assert len(result.accounts) == 2
        returned_aids = {d.account_id for d in result.accounts}
        assert _ACCOUNT_ID in returned_aids
        assert _ACCOUNT_ID_2 in returned_aids

    def test_account_not_in_mailbox_raises_not_found(self, monkeypatch):
        _patch_read_status(monkeypatch)
        payload = self._make_payload([("nonexistent", "m1")])
        with pytest.raises(AccountNotFound):
            emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)

    def test_auth_error_raises_not_connected(self, monkeypatch):
        _patch_read_status(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        payload = self._make_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(AccountNotConnected):
            emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)

    def test_core_error_translates_via_mapping(self, monkeypatch):
        _patch_read_status(monkeypatch, fake_client_kwargs={
            "update_read_status_exc": EmailExternalAPIError("API fail"),
        })
        payload = self._make_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(ExternalAPIError):
            emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)

    def test_unexpected_error_raises_external_api_error(self, monkeypatch):
        _patch_read_status(monkeypatch, fake_client_kwargs={
            "update_read_status_exc": RuntimeError("unexpected"),
        })
        payload = self._make_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(ExternalAPIError):
            emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)

    def test_db_helper_called_only_for_updated_ids(self, monkeypatch):
        """FakeEmailClient returns all IDs by default; override to return subset."""
        accounts = [_fake_account()]
        monkeypatch.setattr(
            emails_service, "ensure_mailbox_access",
            lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
        )
        monkeypatch.setattr(
            emails_service.account_store, "list_by_mailbox",
            lambda _mb: accounts,
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

        # Build a manager whose FakeEmailClient returns only "m1" (not "m2")
        def _build_partial(accs):
            manager = EmailManager()
            for acc in accs:
                mid = str(acc.get("mailbox_id", ""))
                aid = str(acc.get("account_id", ""))
                label = f"{mid}__{aid}"

                class _PartialFake(FakeEmailClient):
                    def update_read_status(self, message_ids, is_read):
                        return ["m1"]  # only m1 succeeded

                manager.add_client(_PartialFake(
                    label,
                    auth_return={"access_token": "tok", "refresh_token": "ref"},
                ))
            return manager

        monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_partial)

        db_calls = []
        monkeypatch.setattr(
            emails_service, "update_email_read_status_batch",
            lambda aid, ids, is_read: (db_calls.append((aid, list(ids), is_read)), len(ids))[1],
        )

        payload = self._make_payload([
            (_ACCOUNT_ID, "m1"),
            (_ACCOUNT_ID, "m2"),
        ], is_read=True)
        result = emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)
        assert result.updated_count == 1
        assert len(db_calls) == 1
        assert db_calls[0][1] == ["m1"]

    def test_persists_refreshed_tokens(self, monkeypatch):
        accounts = [_fake_account()]
        monkeypatch.setattr(
            emails_service, "ensure_mailbox_access",
            lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
        )
        monkeypatch.setattr(
            emails_service.account_store, "list_by_mailbox",
            lambda _mb: accounts,
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
            emails_service, "update_email_read_status_batch",
            lambda _aid, _ids, _read: len(_ids),
        )

        upsert_calls = []
        monkeypatch.setattr(
            emails_service.account_store, "upsert_tokens",
            lambda *args, **kwargs: upsert_calls.append(args),
        )

        def _build_refreshing(accs):
            manager = EmailManager()
            for acc in accs:
                mid = str(acc.get("mailbox_id", ""))
                aid = str(acc.get("account_id", ""))
                label = f"{mid}__{aid}"
                manager.add_client(FakeEmailClient(
                    label,
                    auth_silent_return={"access_token": "new_tok", "refresh_token": "new_ref"},
                ))
            return manager

        monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_refreshing)

        payload = self._make_payload([(_ACCOUNT_ID, "m1")])
        emails_service.update_read_status(_MAILBOX_ID, payload, _USER_ID)
        assert len(upsert_calls) >= 1


# ==================================================================
# move_to_spam / restore_from_spam
# ==================================================================


def _patch_spam(monkeypatch, *, accounts=None, fake_client_kwargs=None):
    """Apply monkeypatches specific to spam move/restore tests."""
    if accounts is None:
        accounts = [_fake_account()]

    monkeypatch.setattr(
        emails_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    monkeypatch.setattr(
        emails_service.account_store, "list_by_mailbox",
        lambda _mb: accounts,
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
    monkeypatch.setattr(
        emails_service, "update_email_spam_status_batch",
        lambda _aid, _results, _box: len(_results),
    )

    kwargs = fake_client_kwargs or {}

    def _build(accs):
        manager = EmailManager()
        for acc in accs:
            mid = str(acc.get("mailbox_id", ""))
            aid = str(acc.get("account_id", ""))
            label = f"{mid}__{aid}"
            manager.add_client(FakeEmailClient(
                label,
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                **kwargs,
            ))
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build)


def _spam_payload(items):
    return SpamRequest(
        items=[SpamItem(account_id=aid, provider_message_id=mid)
               for aid, mid in items],
    )


class TestMoveToSpam:

    def test_happy_path_single_account(self, monkeypatch):
        _patch_spam(monkeypatch)
        payload = _spam_payload([(_ACCOUNT_ID, "m1"), (_ACCOUNT_ID, "m2")])
        result = emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)
        assert result.moved_count == 2
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == _ACCOUNT_ID
        assert result.accounts[0].moved == 2

    def test_happy_path_multi_account(self, monkeypatch):
        accounts = [_fake_account(_ACCOUNT_ID), _fake_account(_ACCOUNT_ID_2)]
        _patch_spam(monkeypatch, accounts=accounts)
        payload = _spam_payload([(_ACCOUNT_ID, "m1"), (_ACCOUNT_ID_2, "m2")])
        result = emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)
        assert result.moved_count == 2
        assert len(result.accounts) == 2

    def test_account_not_in_mailbox_raises_not_found(self, monkeypatch):
        _patch_spam(monkeypatch)
        payload = _spam_payload([("nonexistent", "m1")])
        with pytest.raises(AccountNotFound):
            emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_auth_error_raises_not_connected(self, monkeypatch):
        _patch_spam(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(AccountNotConnected):
            emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_core_error_translates_via_mapping(self, monkeypatch):
        _patch_spam(monkeypatch, fake_client_kwargs={
            "move_to_spam_exc": EmailExternalAPIError("API fail"),
        })
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(ExternalAPIError):
            emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_unexpected_error_raises_external_api_error(self, monkeypatch):
        _patch_spam(monkeypatch, fake_client_kwargs={
            "move_to_spam_exc": RuntimeError("unexpected"),
        })
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(ExternalAPIError):
            emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_db_helper_called_with_spam_box(self, monkeypatch):
        _patch_spam(monkeypatch)
        db_calls: list[tuple] = []
        monkeypatch.setattr(
            emails_service, "update_email_spam_status_batch",
            lambda aid, results, box: (db_calls.append((aid, results, box)), len(results))[1],
        )
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        emails_service.move_to_spam(_MAILBOX_ID, payload, _USER_ID)
        assert len(db_calls) == 1
        assert db_calls[0][2] == "SPAM"


class TestRestoreFromSpam:

    def test_happy_path_single_account(self, monkeypatch):
        _patch_spam(monkeypatch)
        payload = _spam_payload([(_ACCOUNT_ID, "m1"), (_ACCOUNT_ID, "m2")])
        result = emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)
        assert result.moved_count == 2
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == _ACCOUNT_ID
        assert result.accounts[0].moved == 2

    def test_happy_path_multi_account(self, monkeypatch):
        accounts = [_fake_account(_ACCOUNT_ID), _fake_account(_ACCOUNT_ID_2)]
        _patch_spam(monkeypatch, accounts=accounts)
        payload = _spam_payload([(_ACCOUNT_ID, "m1"), (_ACCOUNT_ID_2, "m2")])
        result = emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)
        assert result.moved_count == 2
        assert len(result.accounts) == 2

    def test_account_not_in_mailbox_raises_not_found(self, monkeypatch):
        _patch_spam(monkeypatch)
        payload = _spam_payload([("nonexistent", "m1")])
        with pytest.raises(AccountNotFound):
            emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_auth_error_raises_not_connected(self, monkeypatch):
        _patch_spam(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(AccountNotConnected):
            emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_core_error_translates_via_mapping(self, monkeypatch):
        _patch_spam(monkeypatch, fake_client_kwargs={
            "restore_from_spam_exc": EmailExternalAPIError("API fail"),
        })
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(ExternalAPIError):
            emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_unexpected_error_raises_external_api_error(self, monkeypatch):
        _patch_spam(monkeypatch, fake_client_kwargs={
            "restore_from_spam_exc": RuntimeError("unexpected"),
        })
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        with pytest.raises(ExternalAPIError):
            emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)

    def test_db_helper_called_with_all_mail_box(self, monkeypatch):
        _patch_spam(monkeypatch)
        db_calls: list[tuple] = []
        monkeypatch.setattr(
            emails_service, "update_email_spam_status_batch",
            lambda aid, results, box: (db_calls.append((aid, results, box)), len(results))[1],
        )
        payload = _spam_payload([(_ACCOUNT_ID, "m1")])
        emails_service.restore_from_spam(_MAILBOX_ID, payload, _USER_ID)
        assert len(db_calls) == 1
        assert db_calls[0][2] == "ALL_MAIL"


# ==================================================================
# list_emails
# ==================================================================


_SAMPLE_ROW = {
    "provider_message_id": "m1",
    "account_id": _ACCOUNT_ID,
    "thread_id": "t1",
    "from_email": "sender@test.com",
    "from_name": "Sender",
    "subject": "Hello",
    "received_at": "2025-01-15T10:00:00+00:00",
    "is_read": False,
    "box": "ALL_MAIL",
}


def _patch_list_emails(monkeypatch, *, rows=None, account_get_return="default"):
    """Apply monkeypatches for list_emails tests."""
    monkeypatch.setattr(
        emails_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    if account_get_return == "default":
        monkeypatch.setattr(
            emails_service.account_store, "get",
            lambda _mb, _aid: _fake_account() if _aid == _ACCOUNT_ID else None,
        )
    else:
        monkeypatch.setattr(
            emails_service.account_store, "get",
            account_get_return,
        )
    result_rows = rows if rows is not None else [_SAMPLE_ROW]
    monkeypatch.setattr(
        emails_service.email_metadata_store, "list_by_account_and_box",
        lambda _aid, _box: result_rows,
    )
    monkeypatch.setattr(
        emails_service.email_metadata_store, "list_by_mailbox_and_box",
        lambda _mbid, _box: result_rows,
    )


class TestListEmails:

    def test_single_account_happy_path(self, monkeypatch):
        _patch_list_emails(monkeypatch)
        result = emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID, _ACCOUNT_ID)
        assert len(result) == 1
        assert result[0].provider_message_id == "m1"
        assert result[0].account_id == _ACCOUNT_ID

    def test_unified_view_happy_path(self, monkeypatch):
        _patch_list_emails(monkeypatch)
        result = emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID)
        assert len(result) == 1
        assert result[0].provider_message_id == "m1"

    def test_account_not_found_raises(self, monkeypatch):
        _patch_list_emails(monkeypatch)
        with pytest.raises(AccountNotFound, match="during email listing"):
            emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID, "nonexistent")

    def test_db_error_on_account_lookup_raises(self, monkeypatch):
        from database.errors.exceptions import QueryError as DbQueryError
        _patch_list_emails(monkeypatch)

        def _raise(_mb, _aid):
            raise DbQueryError("db fail")

        monkeypatch.setattr(emails_service.account_store, "get", _raise)
        with pytest.raises(Exception):
            emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID, _ACCOUNT_ID)

    def test_db_error_on_single_account_query_raises(self, monkeypatch):
        from database.errors.exceptions import QueryError as DbQueryError
        _patch_list_emails(monkeypatch)

        def _raise(_aid, _box):
            raise DbQueryError("db fail")

        monkeypatch.setattr(
            emails_service.email_metadata_store, "list_by_account_and_box", _raise,
        )
        with pytest.raises(Exception):
            emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID, _ACCOUNT_ID)

    def test_db_error_on_unified_query_raises(self, monkeypatch):
        from database.errors.exceptions import QueryError as DbQueryError
        _patch_list_emails(monkeypatch)

        def _raise(_mbid, _box):
            raise DbQueryError("db fail")

        monkeypatch.setattr(
            emails_service.email_metadata_store, "list_by_mailbox_and_box", _raise,
        )
        with pytest.raises(Exception):
            emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID)

    def test_unexpected_error_raises_email_list_error(self, monkeypatch):
        _patch_list_emails(monkeypatch)

        def _raise(_mbid, _box):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(
            emails_service.email_metadata_store, "list_by_mailbox_and_box", _raise,
        )
        with pytest.raises(EmailListError, match="Failed to list email metadata for mailbox"):
            emails_service.list_emails(_MAILBOX_ID, "ALL_MAIL", _USER_ID)

    def test_empty_result_returns_empty_list(self, monkeypatch):
        _patch_list_emails(monkeypatch, rows=[])
        result = emails_service.list_emails(_MAILBOX_ID, "SPAM", _USER_ID)
        assert result == []


# ==================================================================
# get_email_full_content
# ==================================================================


def _patch_get_content_common(monkeypatch, *, fake_client_kwargs=None):
    """Apply common monkeypatches for get_email_full_content tests."""
    monkeypatch.setattr(
        emails_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
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
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                **kwargs,
            ))
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build)

    # Default: metadata row exists — tests that need a missing metadata row
    # override this patch explicitly.
    monkeypatch.setattr(
        emails_service.email_metadata_store, "exists",
        lambda _aid, _mid: True,
    )

    # Stub persist helper (best-effort, no-op by default)
    monkeypatch.setattr(emails_service, "persist_email_content", lambda *_a: None)


class TestGetEmailFullContent:

    def test_db_hit(self, monkeypatch):
        """When DB already has content, return it without calling core."""
        _patch_get_content_common(monkeypatch)
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid, **_kw: {"html_body": "<p>cached</p>", "text_body": "cached"},
        )

        result = emails_service.get_email_full_content(
            _MAILBOX_ID, "m1", _ACCOUNT_ID, _USER_ID,
        )
        assert result.html_body == "<p>cached</p>"
        assert result.text_body == "cached"

    def test_db_miss_fetches_from_provider(self, monkeypatch):
        """When DB returns None, fetch from provider and persist."""
        _patch_get_content_common(monkeypatch, fake_client_kwargs={
            "email_content": EmailContent(
                html_body="<p>from provider</p>", text_body="from provider",
            ),
        })
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid, **_kw: None,
        )

        persist_calls = []
        monkeypatch.setattr(
            emails_service, "persist_email_content",
            lambda aid, mid, html, txt, **_kw: persist_calls.append((aid, mid, html, txt)),
        )

        result = emails_service.get_email_full_content(
            _MAILBOX_ID, "m1", _ACCOUNT_ID, _USER_ID,
        )
        assert result.text_body == "from provider"
        assert len(persist_calls) == 1
        # Verify persist was called with the account_id and message id
        assert persist_calls[0][0] == _ACCOUNT_ID
        assert persist_calls[0][1] == "m1"

    def test_sanitizes_html(self, monkeypatch):
        """HTML body from provider is sanitized before being persisted and returned."""
        _patch_get_content_common(monkeypatch, fake_client_kwargs={
            "email_content": EmailContent(
                html_body="<p>safe</p><script>alert(1)</script>", text_body="safe",
            ),
        })
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid, **_kw: None,
        )

        persist_calls = []
        monkeypatch.setattr(
            emails_service, "persist_email_content",
            lambda aid, mid, html, txt, **_kw: persist_calls.append((aid, mid, html, txt)),
        )

        result = emails_service.get_email_full_content(
            _MAILBOX_ID, "m1", _ACCOUNT_ID, _USER_ID,
        )
        assert "<script>" not in (result.html_body or "")
        assert "<p>safe</p>" in (result.html_body or "")
        # Verify persisted html is also sanitized
        assert "<script>" not in (persist_calls[0][2] or "")

    def test_account_not_found(self, monkeypatch):
        """Non-existent account_id raises AccountNotFound."""
        _patch_get_content_common(monkeypatch)
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid, **_kw: None,
        )

        with pytest.raises(AccountNotFound):
            emails_service.get_email_full_content(
                _MAILBOX_ID, "m1", "nonexistent", _USER_ID,
            )

    def test_core_error_translated(self, monkeypatch):
        """CoreError from manager.fetch_email_content is translated to EmailContentFetchError."""
        _patch_get_content_common(monkeypatch, fake_client_kwargs={
            "fetch_content_exc": EmailExternalAPIError("provider down"),
        })
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid, **_kw: None,
        )

        with pytest.raises(ExternalAPIError):
            emails_service.get_email_full_content(
                _MAILBOX_ID, "m1", _ACCOUNT_ID, _USER_ID,
            )

    def test_persist_failure_best_effort(self, monkeypatch):
        """If persist_email_content raises, the content is still returned."""
        _patch_get_content_common(monkeypatch, fake_client_kwargs={
            "email_content": EmailContent(
                html_body="<p>ok</p>", text_body="ok",
            ),
        })
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid, **_kw: None,
        )
        monkeypatch.setattr(
            emails_service, "persist_email_content",
            MagicMock(side_effect=RuntimeError("db write failed")),
        )

        result = emails_service.get_email_full_content(
            _MAILBOX_ID, "m1", _ACCOUNT_ID, _USER_ID,
        )
        assert result.text_body == "ok"
        assert result.html_body is not None

    def test_email_not_found_when_metadata_absent(self, monkeypatch):
        """Missing metadata row raises EmailNotFound before touching cache."""
        _patch_get_content_common(monkeypatch)
        monkeypatch.setattr(
            emails_service.email_metadata_store, "exists",
            lambda _aid, _mid: False,
        )

        get_content_calls = []
        monkeypatch.setattr(
            emails_service, "get_email_content",
            lambda _aid, _mid: get_content_calls.append((_aid, _mid)) or None,
        )

        with pytest.raises(EmailNotFound):
            emails_service.get_email_full_content(
                _MAILBOX_ID, "never-existed", _ACCOUNT_ID, _USER_ID,
            )
        # exists must short-circuit before cache read
        assert get_content_calls == []

    def test_metadata_exists_database_error_translated(self, monkeypatch):
        """DatabaseError during exists() is translated via translate_database_error."""
        from database.errors.exceptions import QueryError as DbQueryError
        from api.errors.exceptions import DatabaseQueryError

        _patch_get_content_common(monkeypatch)

        def _raise(_aid, _mid):
            raise DbQueryError("exists fail")

        monkeypatch.setattr(emails_service.email_metadata_store, "exists", _raise)

        with pytest.raises(DatabaseQueryError):
            emails_service.get_email_full_content(
                _MAILBOX_ID, "m1", _ACCOUNT_ID, _USER_ID,
            )
