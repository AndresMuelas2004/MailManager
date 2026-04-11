"""
Unit tests for drafts_service (create_draft + list_drafts + sync_drafts).

All external dependencies are monkeypatched so tests run without DB or provider APIs.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.errors.exceptions import (
    AccountNotConnected,
    AccountNotFound,
    DatabaseQueryError,
    DraftCreationError,
    DraftListError,
    DraftSyncError,
    ExternalAPIError,
    Forbidden,
)
from api.schemas.draft import DraftCreate
from api.services import drafts_service
from core.email import DraftMetadata, EmailManager
from core.email.errors import EmailAuthError, EmailExternalAPIError
from database.errors import QueryError as DbQueryError
from tests.shared.email_fakes import FakeEmailClient


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


def _persisted_row(
    *,
    provider_draft_id: str = "fake_draft_1",
    to_recipients: list[str] | None = None,
    cc_recipients: list[str] | None = None,
    bcc_recipients: list[str] | None = None,
    subject: str = "Hello draft",
    body_html: str = "<p>body</p>",
) -> dict:
    return {
        "provider_draft_id": provider_draft_id,
        "account_id": _ACCOUNT_ID,
        "to_recipients": to_recipients if to_recipients is not None else ["to@example.com"],
        "cc_recipients": cc_recipients if cc_recipients is not None else [],
        "bcc_recipients": bcc_recipients if bcc_recipients is not None else [],
        "subject": subject,
        "body_html": body_html,
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0),
    }


def _patch_common(monkeypatch, *, fake_client_kwargs=None):
    """Apply common monkeypatches for drafts_service tests."""
    monkeypatch.setattr(
        drafts_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    monkeypatch.setattr(
        drafts_service.account_store, "get",
        lambda _mb, _aid: _fake_account() if _aid == _ACCOUNT_ID else None,
    )
    monkeypatch.setattr(
        drafts_service, "load_wrapped_app_credentials",
        lambda _prov: {"client_id": "cid", "client_secret": "cs"},
    )
    monkeypatch.setattr(
        drafts_service, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: {"access_token": "at", "refresh_token": "rt"},
    )
    monkeypatch.setattr(
        drafts_service.account_store, "upsert_tokens",
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

    monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)

    # Default draft_store.create returns a deterministic row
    monkeypatch.setattr(
        drafts_service.draft_store, "create",
        lambda row: _persisted_row(
            provider_draft_id=row.get("provider_draft_id", "fake_draft_1"),
            to_recipients=row.get("to_recipients", []),
            cc_recipients=row.get("cc_recipients", []),
            bcc_recipients=row.get("bcc_recipients", []),
            subject=row.get("subject", ""),
            body_html=row.get("body_html", ""),
        ),
    )


class TestCreateDraft:

    def _make_payload(self) -> DraftCreate:
        return DraftCreate(
            to_recipients=["to@example.com"],
            cc_recipients=[],
            bcc_recipients=[],
            subject="Hello draft",
            body_html="<p>body</p>",
        )

    def test_happy_path_returns_draft_out(self, monkeypatch):
        _patch_common(monkeypatch)
        result = drafts_service.create_draft(
            _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
        )
        assert result.provider_draft_id == "fake_draft_1"
        assert result.account_id == _ACCOUNT_ID
        assert result.to_recipients == ["to@example.com"]
        assert result.subject == "Hello draft"
        assert result.body_html == "<p>body</p>"
        assert result.created_at == datetime(2024, 1, 1, 12, 0, 0)
        assert result.updated_at == datetime(2024, 1, 1, 12, 0, 0)

    def test_empty_draft_allowed(self, monkeypatch):
        _patch_common(monkeypatch)
        result = drafts_service.create_draft(
            _MAILBOX_ID, _ACCOUNT_ID, DraftCreate(), _USER_ID,
        )
        assert result.subject == ""
        assert result.body_html == ""
        assert result.to_recipients == []
        assert result.cc_recipients == []
        assert result.bcc_recipients == []

    def test_account_not_found_raises(self, monkeypatch):
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.account_store, "get",
            lambda _mb, _aid: None,
        )
        with pytest.raises(AccountNotFound):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_mailbox_access_denied_raises(self, monkeypatch):
        _patch_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise Forbidden("You do not have access to this mailbox.")

        monkeypatch.setattr(drafts_service, "ensure_mailbox_access", _raise)
        with pytest.raises(Forbidden):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_provider_external_api_error_translated(self, monkeypatch):
        # EmailExternalAPIError maps to ExternalAPIError via _CORE_TO_API_MAP.
        _patch_common(monkeypatch, fake_client_kwargs={
            "create_draft_exc": EmailExternalAPIError("Graph 400"),
        })
        with pytest.raises(ExternalAPIError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_provider_generic_exception_raises_external_api_error(self, monkeypatch):
        # EmailManager wraps RuntimeError into EmailExternalAPIError,
        # which then translates to ExternalAPIError via _CORE_TO_API_MAP.
        _patch_common(monkeypatch, fake_client_kwargs={
            "create_draft_exc": RuntimeError("boom"),
        })
        with pytest.raises(ExternalAPIError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_silent_auth_error_raises_account_not_connected(self, monkeypatch):
        _patch_common(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("expired"),
        })
        with pytest.raises(AccountNotConnected):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_db_persist_error_translated(self, monkeypatch):
        _patch_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("db down")

        monkeypatch.setattr(drafts_service.draft_store, "create", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_account_db_lookup_error_translated(self, monkeypatch):
        _patch_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("lookup failed")

        monkeypatch.setattr(drafts_service.account_store, "get", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_provider_call_passes_payload_fields(self, monkeypatch):
        """Verify the FakeEmailClient receives the exact payload fields."""
        _patch_common(monkeypatch)
        captured_clients: list[FakeEmailClient] = []

        def _build(accounts):
            manager = EmailManager()
            for acc in accounts:
                mid = str(acc.get("mailbox_id", ""))
                aid = str(acc.get("account_id", ""))
                label = f"{mid}__{aid}"
                client = FakeEmailClient(
                    label,
                    auth_return={"access_token": "tok", "refresh_token": "ref"},
                )
                captured_clients.append(client)
                manager.add_client(client)
            return manager

        monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)
        payload = DraftCreate(
            to_recipients=["a@b.com", "c@d.com"],
            cc_recipients=["cc@e.com"],
            bcc_recipients=["bcc@f.com"],
            subject="My subject",
            body_html="<b>html</b>",
        )
        drafts_service.create_draft(_MAILBOX_ID, _ACCOUNT_ID, payload, _USER_ID)
        assert len(captured_clients) == 1
        assert len(captured_clients[0].create_draft_calls) == 1
        call = captured_clients[0].create_draft_calls[0]
        assert call == (
            ["a@b.com", "c@d.com"],
            ["cc@e.com"],
            ["bcc@f.com"],
            "My subject",
            "<b>html</b>",
        )

    def test_persist_refreshed_tokens_happy_path(self, monkeypatch):
        # When authenticate_silent returns refreshed tokens, _persist_refreshed_tokens
        # must call account_store.upsert_tokens with the unwrapped values.
        _patch_common(monkeypatch, fake_client_kwargs={
            "auth_silent_return": {
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "expiry": "2030-01-01T00:00:00Z",
            },
        })
        upsert_calls: list[tuple] = []
        monkeypatch.setattr(
            drafts_service.account_store, "upsert_tokens",
            lambda mb, acc, prov, payload: upsert_calls.append((mb, acc, prov, payload)),
        )
        drafts_service.create_draft(
            _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
        )
        assert len(upsert_calls) == 1
        mb, acc, prov, payload = upsert_calls[0]
        assert mb == _MAILBOX_ID
        assert acc == _ACCOUNT_ID
        assert prov == _PROVIDER
        assert payload["access_token"] == "new-at"
        assert payload["refresh_token"] == "new-rt"

    def test_persist_refreshed_tokens_db_error_raises_draft_creation_error(
        self, monkeypatch,
    ):
        _patch_common(monkeypatch, fake_client_kwargs={
            "auth_silent_return": {"access_token": "new-at", "refresh_token": "new-rt"},
        })

        def _raise_db(*_a, **_kw):
            raise DbQueryError("tokens table down")

        monkeypatch.setattr(drafts_service.account_store, "upsert_tokens", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_persist_refreshed_tokens_unexpected_exception_raises_draft_creation_error(
        self, monkeypatch,
    ):
        _patch_common(monkeypatch, fake_client_kwargs={
            "auth_silent_return": {"access_token": "new-at", "refresh_token": "new-rt"},
        })

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.account_store, "upsert_tokens", _raise)
        with pytest.raises(DraftCreationError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_outer_exception_safety_net_raises_draft_creation_error(self, monkeypatch):
        # Patch a helper called inside the outer try to raise a plain exception.
        # It must bubble up as DraftCreationError via the outer safety net.
        _patch_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service, "load_wrapped_app_credentials", _raise)
        with pytest.raises(DraftCreationError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_inner_draft_store_exception_raises_draft_creation_error(self, monkeypatch):
        # RuntimeError from draft_store.create must be wrapped by the inner
        # except Exception into DraftCreationError (not caught only by the outer net).
        _patch_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.draft_store, "create", _raise)
        with pytest.raises(DraftCreationError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_inner_account_store_exception_raises_draft_creation_error(
        self, monkeypatch,
    ):
        # RuntimeError from account_store.get must be wrapped into DraftCreationError.
        _patch_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.account_store, "get", _raise)
        with pytest.raises(DraftCreationError):
            drafts_service.create_draft(
                _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
            )

    def test_none_fields_coalesced_to_defaults(self, monkeypatch):
        # When the persisted row has None for recipients/subject/body_html,
        # DraftOut must expose [] / "" via the `or []`/`or ""` coalescing.
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.draft_store, "create",
            lambda row: {
                "provider_draft_id": "fake_draft_1",
                "account_id": _ACCOUNT_ID,
                "to_recipients": None,
                "cc_recipients": None,
                "bcc_recipients": None,
                "subject": None,
                "body_html": None,
                "created_at": datetime(2024, 1, 1, 12, 0, 0),
                "updated_at": datetime(2024, 1, 1, 12, 0, 0),
            },
        )
        result = drafts_service.create_draft(
            _MAILBOX_ID, _ACCOUNT_ID, self._make_payload(), _USER_ID,
        )
        assert result.to_recipients == []
        assert result.cc_recipients == []
        assert result.bcc_recipients == []
        assert result.subject == ""
        assert result.body_html == ""


def _patch_list_common(monkeypatch):
    """Common monkeypatches for list_drafts tests."""
    monkeypatch.setattr(
        drafts_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    monkeypatch.setattr(
        drafts_service.account_store, "get",
        lambda _mb, _aid: _fake_account() if _aid == _ACCOUNT_ID else None,
    )
    # Default: list_by_account and list_by_mailbox return a single row.
    monkeypatch.setattr(
        drafts_service.draft_store, "list_by_account",
        lambda _aid: [_persisted_row(provider_draft_id="draft_a")],
    )
    monkeypatch.setattr(
        drafts_service.draft_store, "list_by_mailbox",
        lambda _mid: [
            _persisted_row(provider_draft_id="draft_a"),
            _persisted_row(provider_draft_id="draft_b"),
        ],
    )


class TestListDrafts:

    def test_list_single_account_happy_path(self, monkeypatch):
        _patch_list_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.draft_store, "list_by_account",
            lambda _aid: [
                _persisted_row(provider_draft_id="d1", subject="first"),
                _persisted_row(provider_draft_id="d2", subject="second"),
            ],
        )
        result = drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)
        assert len(result) == 2
        assert result[0].provider_draft_id == "d1"
        assert result[0].subject == "first"
        assert result[0].account_id == _ACCOUNT_ID
        assert result[1].provider_draft_id == "d2"
        assert result[1].subject == "second"

    def test_list_unified_view_happy_path(self, monkeypatch):
        _patch_list_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.draft_store, "list_by_mailbox",
            lambda _mid: [
                _persisted_row(provider_draft_id="d1"),
                _persisted_row(provider_draft_id="d2"),
                _persisted_row(provider_draft_id="d3"),
            ],
        )
        result = drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, None)
        assert len(result) == 3
        ids = [r.provider_draft_id for r in result]
        assert ids == ["d1", "d2", "d3"]

    def test_list_account_not_found_raises(self, monkeypatch):
        _patch_list_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.account_store, "get",
            lambda _mb, _aid: None,
        )
        with pytest.raises(AccountNotFound):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_list_mailbox_access_denied_raises(self, monkeypatch):
        _patch_list_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise Forbidden("You do not have access to this mailbox.")

        monkeypatch.setattr(drafts_service, "ensure_mailbox_access", _raise)
        with pytest.raises(Forbidden):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, None)

    def test_list_db_error_on_account_lookup_raises(self, monkeypatch):
        _patch_list_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("lookup failed")

        monkeypatch.setattr(drafts_service.account_store, "get", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_list_db_error_on_list_by_account_raises(self, monkeypatch):
        _patch_list_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("query failed")

        monkeypatch.setattr(drafts_service.draft_store, "list_by_account", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_list_db_error_on_list_by_mailbox_raises(self, monkeypatch):
        _patch_list_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("query failed")

        monkeypatch.setattr(drafts_service.draft_store, "list_by_mailbox", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, None)

    def test_list_unexpected_error_on_list_by_account_raises_draft_list_error(
        self, monkeypatch,
    ):
        _patch_list_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.draft_store, "list_by_account", _raise)
        with pytest.raises(DraftListError):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_list_unexpected_error_on_list_by_mailbox_raises_draft_list_error(
        self, monkeypatch,
    ):
        _patch_list_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.draft_store, "list_by_mailbox", _raise)
        with pytest.raises(DraftListError):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, None)

    def test_list_unexpected_error_on_account_lookup_raises_draft_list_error(
        self, monkeypatch,
    ):
        _patch_list_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.account_store, "get", _raise)
        with pytest.raises(DraftListError):
            drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_list_empty_result_returns_empty_list(self, monkeypatch):
        _patch_list_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.draft_store, "list_by_mailbox",
            lambda _mid: [],
        )
        result = drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, None)
        assert result == []

    def test_list_none_fields_coalesced_to_defaults(self, monkeypatch):
        _patch_list_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.draft_store, "list_by_mailbox",
            lambda _mid: [
                {
                    "provider_draft_id": "d1",
                    "account_id": _ACCOUNT_ID,
                    "to_recipients": None,
                    "cc_recipients": None,
                    "bcc_recipients": None,
                    "subject": None,
                    "body_html": None,
                    "created_at": datetime(2024, 1, 1, 12, 0, 0),
                    "updated_at": datetime(2024, 1, 1, 12, 0, 0),
                },
            ],
        )
        result = drafts_service.list_drafts(_MAILBOX_ID, _USER_ID, None)
        assert len(result) == 1
        assert result[0].to_recipients == []
        assert result[0].cc_recipients == []
        assert result[0].bcc_recipients == []
        assert result[0].subject == ""
        assert result[0].body_html == ""


# =====================================================================
# TestSyncDrafts — unit tests for drafts_service.sync_drafts
# =====================================================================

_DRAFT_TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _sample_draft(provider_draft_id: str = "d1", subject: str = "S") -> DraftMetadata:
    return DraftMetadata(
        provider_draft_id=provider_draft_id,
        to_recipients=["to@example.com"],
        cc_recipients=[],
        bcc_recipients=[],
        subject=subject,
        body_html="<p>hi</p>",
        created_at=_DRAFT_TS,
        updated_at=_DRAFT_TS,
    )


def _patch_sync_common(
    monkeypatch,
    *,
    fake_client_kwargs=None,
    accounts=None,
):
    """Common monkeypatches for sync_drafts tests.

    Builds an EmailManager with one FakeEmailClient per account. Captures
    replace_all_for_account invocations in a list returned at the end.
    """
    if accounts is None:
        accounts = [_fake_account()]

    monkeypatch.setattr(
        drafts_service, "ensure_mailbox_access",
        lambda _mb, _uid: {"mailbox_id": _MAILBOX_ID, "owner_user_id": _USER_ID},
    )
    monkeypatch.setattr(
        drafts_service.account_store, "get",
        lambda _mb, _aid: next(
            (a for a in accounts if a["account_id"] == _aid), None,
        ),
    )
    monkeypatch.setattr(
        drafts_service.account_store, "list_by_mailbox",
        lambda _mb: list(accounts),
    )
    monkeypatch.setattr(
        drafts_service, "load_wrapped_app_credentials",
        lambda _prov: {"client_id": "cid", "client_secret": "cs"},
    )
    monkeypatch.setattr(
        drafts_service, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: {"access_token": "at", "refresh_token": "rt"},
    )
    monkeypatch.setattr(
        drafts_service.account_store, "upsert_tokens",
        lambda *_a, **_kw: None,
    )

    kwargs = fake_client_kwargs or {}

    def _build(accounts_list):
        manager = EmailManager()
        for acc in accounts_list:
            mid = str(acc.get("mailbox_id", ""))
            aid = str(acc.get("account_id", ""))
            label = f"{mid}__{aid}"
            default_return = [_sample_draft(provider_draft_id=f"d_{aid}")]
            call_kwargs = {
                "auth_return": {"access_token": "tok", "refresh_token": "ref"},
                "fetch_drafts_return": default_return,
                **kwargs,
            }
            manager.add_client(FakeEmailClient(label, **call_kwargs))
        return manager

    monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)

    replace_calls: list[tuple[str, list[dict]]] = []

    def _replace(account_id, drafts_list):
        replace_calls.append((account_id, list(drafts_list)))
        return len(drafts_list)

    monkeypatch.setattr(
        drafts_service.draft_store, "replace_all_for_account", _replace,
    )
    return replace_calls


class TestSyncDrafts:

    def test_sync_single_account_happy_path(self, monkeypatch):
        calls = _patch_sync_common(monkeypatch)
        result = drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)
        assert isinstance(result.total_synced, int)
        assert result.total_synced == 1
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == _ACCOUNT_ID
        assert result.accounts[0].provider == _PROVIDER
        assert result.accounts[0].drafts_synced == 1
        assert len(calls) == 1
        assert calls[0][0] == _ACCOUNT_ID

    def test_sync_mailbox_happy_path(self, monkeypatch):
        accounts = [
            _fake_account(account_id="acc-gmail", provider="gmail"),
            _fake_account(account_id="acc-outlook", provider="outlook"),
        ]
        calls = _patch_sync_common(monkeypatch, accounts=accounts)
        result = drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, None)
        assert result.total_synced == 2
        assert len(result.accounts) == 2
        account_ids = {a.account_id for a in result.accounts}
        assert account_ids == {"acc-gmail", "acc-outlook"}
        providers = {a.provider for a in result.accounts}
        assert providers == {"gmail", "outlook"}
        assert len(calls) == 2

    def test_sync_account_not_found_raises(self, monkeypatch):
        _patch_sync_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.account_store, "get",
            lambda _mb, _aid: None,
        )
        with pytest.raises(AccountNotFound):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_mailbox_access_denied_raises(self, monkeypatch):
        _patch_sync_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise Forbidden("You do not have access to this mailbox.")

        monkeypatch.setattr(drafts_service, "ensure_mailbox_access", _raise)
        with pytest.raises(Forbidden):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, None)

    def test_sync_db_error_on_account_lookup_raises(self, monkeypatch):
        _patch_sync_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("lookup failed")

        monkeypatch.setattr(drafts_service.account_store, "get", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_db_error_on_list_by_mailbox_raises(self, monkeypatch):
        _patch_sync_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("list failed")

        monkeypatch.setattr(drafts_service.account_store, "list_by_mailbox", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, None)

    def test_sync_provider_external_api_error_translated(self, monkeypatch):
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "fetch_drafts_exc": EmailExternalAPIError("Provider down"),
        })
        with pytest.raises(ExternalAPIError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_silent_auth_error_raises_account_not_connected(self, monkeypatch):
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "auth_silent_exc": EmailAuthError("Token expired"),
        })
        with pytest.raises(AccountNotConnected):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_db_error_on_replace_raises(self, monkeypatch):
        _patch_sync_common(monkeypatch)

        def _raise_db(*_a, **_kw):
            raise DbQueryError("persist failed")

        monkeypatch.setattr(
            drafts_service.draft_store, "replace_all_for_account", _raise_db,
        )
        with pytest.raises(DatabaseQueryError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_unexpected_error_on_replace_raises_draft_sync_error(
        self, monkeypatch,
    ):
        _patch_sync_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            drafts_service.draft_store, "replace_all_for_account", _raise,
        )
        with pytest.raises(DraftSyncError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_empty_accounts_returns_zero(self, monkeypatch):
        _patch_sync_common(monkeypatch)
        monkeypatch.setattr(
            drafts_service.account_store, "list_by_mailbox",
            lambda _mb: [],
        )
        result = drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, None)
        assert result.total_synced == 0
        assert result.accounts == []

    def test_sync_rows_include_all_draft_fields(self, monkeypatch):
        """The rows passed to replace_all_for_account carry every DraftMetadata field."""
        calls = _patch_sync_common(monkeypatch)
        drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)
        assert len(calls) == 1
        _, rows = calls[0]
        assert len(rows) == 1
        row = rows[0]
        assert row["provider_draft_id"] == f"d_{_ACCOUNT_ID}"
        assert row["to_recipients"] == ["to@example.com"]
        assert row["cc_recipients"] == []
        assert row["bcc_recipients"] == []
        assert row["subject"] == "S"
        assert row["body_html"] == "<p>hi</p>"
        assert row["created_at"] == _DRAFT_TS
        assert row["updated_at"] == _DRAFT_TS

    def test_sync_persist_refreshed_tokens_happy_path(self, monkeypatch):
        # When authenticate_silent returns refreshed tokens, _persist_refreshed_tokens
        # must call account_store.upsert_tokens with the unwrapped values.
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "auth_silent_return": {
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "expiry": "2030-01-01T00:00:00Z",
            },
        })
        upsert_calls: list[tuple] = []
        monkeypatch.setattr(
            drafts_service.account_store, "upsert_tokens",
            lambda mb, acc, prov, payload: upsert_calls.append((mb, acc, prov, payload)),
        )
        drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)
        assert len(upsert_calls) == 1
        mb, acc, prov, payload = upsert_calls[0]
        assert mb == _MAILBOX_ID
        assert acc == _ACCOUNT_ID
        assert prov == _PROVIDER
        assert payload["access_token"] == "new-at"
        assert payload["refresh_token"] == "new-rt"

    def test_sync_persist_refreshed_tokens_db_error_raises(self, monkeypatch):
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "auth_silent_return": {"access_token": "new-at", "refresh_token": "new-rt"},
        })

        def _raise_db(*_a, **_kw):
            raise DbQueryError("tokens table down")

        monkeypatch.setattr(drafts_service.account_store, "upsert_tokens", _raise_db)
        with pytest.raises(DatabaseQueryError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_persist_refreshed_tokens_unexpected_raises_draft_sync_error(
        self, monkeypatch,
    ):
        # After Bloque 3 refactor, _persist_refreshed_tokens accepts a `fallback`
        # parameter and sync_drafts passes DraftSyncError — so a plain RuntimeError
        # from upsert_tokens must surface as DraftSyncError (not DraftCreationError).
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "auth_silent_return": {"access_token": "new-at", "refresh_token": "new-rt"},
        })

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service.account_store, "upsert_tokens", _raise)
        with pytest.raises(DraftSyncError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_fetch_all_drafts_core_error_translated(self, monkeypatch):
        # fetch_all_drafts captures the error in _last_errors; the downstream
        # raise_on_silent_auth_errors call translates it to ExternalAPIError.
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "fetch_drafts_exc": EmailExternalAPIError("Provider 502"),
        })
        with pytest.raises(ExternalAPIError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_fetch_all_drafts_generic_exception_raises_draft_sync_error(
        self, monkeypatch,
    ):
        # A non-CoreError captured in _last_errors is surfaced by
        # translate_core_error via the fallback (DraftSyncError for sync_drafts).
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "fetch_drafts_exc": RuntimeError("unexpected"),
        })
        with pytest.raises(DraftSyncError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_provider_runtime_error_raises_draft_sync_error(self, monkeypatch):
        # Documents the asymmetric behavior vs. create_draft: a plain RuntimeError
        # from FakeEmailClient.fetch_drafts is captured in _last_errors by
        # EmailManager.fetch_all_drafts (not wrapped into EmailExternalAPIError
        # like send_email does) and surfaces as DraftSyncError via the fallback.
        _patch_sync_common(monkeypatch, fake_client_kwargs={
            "fetch_drafts_exc": RuntimeError("boom"),
        })
        with pytest.raises(DraftSyncError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)

    def test_sync_build_auth_context_error_raises_draft_sync_error(self, monkeypatch):
        # Validates Bloque 1.3 fix: _build_draft_auth_context + build_manager_for_accounts
        # must be inside the outer try block so plain exceptions from those helpers
        # are caught and re-raised as DraftSyncError.
        _patch_sync_common(monkeypatch)

        def _raise(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(drafts_service, "load_wrapped_app_credentials", _raise)
        with pytest.raises(DraftSyncError):
            drafts_service.sync_drafts(_MAILBOX_ID, _USER_ID, _ACCOUNT_ID)
