"""Unit tests for GmailClient — build config, guard clauses, and metadata fetch.

Shared helper tests (parse_expiry, unwrap/wrap) live in ``test_helpers.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.email.email_client import SyncResult
from core.email.errors import (
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
)
from core.email.gmail_client import GmailClient


@pytest.fixture
def client() -> GmailClient:
    return GmailClient(account_label="mb__acct")


# ── get_account_label ────────────────────────────────────────────────


def test_get_account_label_returns_constructor_value(client: GmailClient):
    assert client.get_account_label() == "mb__acct"


# ── _build_client_config ─────────────────────────────────────────────


class TestBuildClientConfig:
    def test_wraps_flat_dict_in_installed(self, client: GmailClient):
        payload = {"client_id": "id", "client_secret": "secret"}
        result = client._build_client_config(payload)
        assert result == {"installed": payload}

    def test_preserves_installed_key(self, client: GmailClient):
        payload = {"installed": {"client_id": "id"}}
        result = client._build_client_config(payload)
        assert result is payload

    def test_preserves_web_key(self, client: GmailClient):
        payload = {"web": {"client_id": "id"}}
        result = client._build_client_config(payload)
        assert result is payload


# ── Guard clauses ────────────────────────────────────────────────────


class TestGuardClauses:
    def test_authenticate_missing_credentials_raises_error(self, client: GmailClient):
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate(app_credentials=None)

    def test_authenticate_missing_credentials_empty_dict_raises_error(self, client: GmailClient):
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate(app_credentials={})

    def test_authenticate_silent_missing_credentials_raises_error(self, client: GmailClient):
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate_silent(app_credentials=None)

    def test_authenticate_silent_missing_access_token_raises_error(self, client: GmailClient):
        creds = {"client_id": "id", "client_secret": "s", "token_uri": "uri"}
        with pytest.raises(EmailMissingTokenError):
            client.authenticate_silent(app_credentials=creds, user_tokens={})

    def test_authenticate_silent_missing_app_credential_fields_raises_error(
        self, client: GmailClient
    ):
        creds = {"some_field": "value"}
        tokens = {"access_token": "at"}
        with pytest.raises(EmailMissingAppCredentialsError, match="Missing required"):
            client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_authenticate_silent_expired_no_refresh_token_raises_error(
        self, client: GmailClient
    ):
        creds = {
            "client_id": "id",
            "client_secret": "secret",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        tokens = {
            "access_token": "at",
            "refresh_token": None,
            "expiry": "2020-01-01T00:00:00",
        }
        with pytest.raises(EmailMissingRefreshTokenError):
            client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_fetch_email_metadata_not_authenticated_raises_error(self, client: GmailClient):
        assert client.service is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.fetch_email_metadata()

    def test_send_email_not_authenticated_raises_error(self, client: GmailClient):
        assert client.service is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.send_email("subj", "body", ["a@b.com"])

    def test_send_email_empty_recipients_raises_error(self, client: GmailClient):
        client.service = object()
        with pytest.raises(EmailRecipientsMissingError):
            client.send_email("subj", "body", [])


# ── fetch_email_metadata paths ───────────────────────────────────────


class TestFetchEmailMetadata:
    """Test the routing logic of fetch_email_metadata (bootstrap vs incremental)."""

    def test_no_cursor_calls_bootstrap(self, client: GmailClient):
        client.service = MagicMock()
        fake_result = SyncResult(upserts=[], new_cursor="hist123")
        with patch.object(client, "_bootstrap_email_metadata", return_value=fake_result) as mock_bs:
            result = client.fetch_email_metadata(sync_cursor=None)
        mock_bs.assert_called_once_with(500)
        assert result is fake_result

    def test_valid_cursor_calls_incremental(self, client: GmailClient):
        """With a valid cursor, Path 2 incremental is called."""
        client.service = MagicMock()
        fake_result = SyncResult(upserts=[], new_cursor="hist456")
        with patch.object(client, "_incremental_email_metadata", return_value=fake_result) as mock_inc:
            result = client.fetch_email_metadata(sync_cursor="old_cursor")
        mock_inc.assert_called_once_with("old_cursor")
        assert result is fake_result

    def test_incremental_failure_falls_back_to_bootstrap(self, client: GmailClient):
        """If incremental raises EmailExternalAPIError, bootstrap is used as fallback."""
        client.service = MagicMock()
        fake_result = SyncResult(upserts=[], new_cursor="hist456")
        with patch.object(client, "_incremental_email_metadata", side_effect=EmailExternalAPIError("fail")), \
             patch.object(client, "_bootstrap_email_metadata", return_value=fake_result) as mock_bs:
            result = client.fetch_email_metadata(sync_cursor="old_cursor")
        mock_bs.assert_called_once_with(500)
        assert result is fake_result


# ── _parse_metadata_response ─────────────────────────────────────────


class TestParseMetadataResponse:
    def test_parses_full_message(self):
        msg = {
            "id": "msg1",
            "threadId": "thread1",
            "internalDate": "1700000000000",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "Alice <alice@example.com>"},
                    {"name": "Subject", "value": "Hello"},
                ],
            },
        }
        result = GmailClient._parse_metadata_response(msg)
        assert result.provider_message_id == "msg1"
        assert result.thread_id == "thread1"
        assert result.from_email == "alice@example.com"
        assert result.from_name == "Alice"
        assert result.subject == "Hello"
        assert result.is_read is True  # UNREAD not in labels
        assert result.box == "ALL_MAIL"

    def test_unread_label(self):
        msg = {
            "id": "msg2",
            "threadId": "t2",
            "internalDate": "1700000000000",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {"headers": []},
        }
        result = GmailClient._parse_metadata_response(msg)
        assert result.is_read is False

    def test_spam_box(self):
        msg = {
            "id": "msg3",
            "threadId": "t3",
            "internalDate": "1700000000000",
            "labelIds": ["SPAM"],
            "payload": {"headers": []},
        }
        result = GmailClient._parse_metadata_response(msg)
        assert result.box == "SPAM"

    def test_trash_box(self):
        msg = {
            "id": "msg4",
            "threadId": "t4",
            "internalDate": "1700000000000",
            "labelIds": ["TRASH"],
            "payload": {"headers": []},
        }
        result = GmailClient._parse_metadata_response(msg)
        assert result.box == "TRASH"

    def test_bare_email_address(self):
        msg = {
            "id": "msg5",
            "threadId": "t5",
            "internalDate": "1700000000000",
            "labelIds": [],
            "payload": {
                "headers": [
                    {"name": "From", "value": "bare@example.com"},
                ],
            },
        }
        result = GmailClient._parse_metadata_response(msg)
        assert result.from_email == "bare@example.com"
        assert result.from_name == ""


# ── _resolve_labels ──────────────────────────────────────────────────


class TestResolveLabels:
    def test_read_all_mail(self):
        is_read, box = GmailClient._resolve_labels(["INBOX"])
        assert is_read is True
        assert box == "ALL_MAIL"

    def test_unread(self):
        is_read, box = GmailClient._resolve_labels(["INBOX", "UNREAD"])
        assert is_read is False
        assert box == "ALL_MAIL"

    def test_spam(self):
        is_read, box = GmailClient._resolve_labels(["SPAM"])
        assert is_read is True
        assert box == "SPAM"

    def test_trash(self):
        is_read, box = GmailClient._resolve_labels(["TRASH", "UNREAD"])
        assert is_read is False
        assert box == "TRASH"

    def test_empty_labels(self):
        is_read, box = GmailClient._resolve_labels([])
        assert is_read is True
        assert box == "ALL_MAIL"


# ── _incremental_email_metadata ─────────────────────────────────────


def _make_history_response(history=None, history_id="999", next_page_token=None):
    """Helper to build a Gmail history.list response."""
    resp = {"historyId": history_id}
    if history is not None:
        resp["history"] = history
    if next_page_token:
        resp["nextPageToken"] = next_page_token
    return resp


class TestIncrementalEmailMetadata:
    def test_empty_history_returns_empty_result(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=[], history_id="100")
        )
        client.service = mock_service
        result = client._incremental_email_metadata("50")
        assert isinstance(result, SyncResult)
        assert result.upserts == []
        assert result.deletes == []
        assert result.label_updates == []
        assert result.new_cursor == "100"

    def test_messages_added_goes_to_upserts(self, client: GmailClient):
        mock_service = MagicMock()
        history = [{"messagesAdded": [
            {"message": {"id": "m1"}},
            {"message": {"id": "m2"}},
        ]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        # _batch_fetch_metadata returns metadata for the requested IDs
        client.service = mock_service
        with patch.object(client, "_batch_fetch_metadata", return_value=["meta1", "meta2"]) as mock_batch:
            result = client._incremental_email_metadata("100")
        assert set(mock_batch.call_args[0][0]) == {"m1", "m2"}
        assert result.upserts == ["meta1", "meta2"]
        assert result.deletes == []

    def test_messages_deleted_confirmed_goes_to_deletes(self, client: GmailClient):
        """When .get() fails for a deleted message, it is confirmed as delete."""
        mock_service = MagicMock()
        history = [{"messagesDeleted": [{"message": {"id": "d1"}}]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        from googleapiclient.errors import HttpError
        resp = MagicMock()
        type(resp).status = 404
        mock_service.users().messages().get().execute.side_effect = HttpError(
            resp=resp, content=b"not found"
        )
        client.service = mock_service
        with patch.object(client, "_batch_fetch_metadata", return_value=[]):
            result = client._incremental_email_metadata("100")
        assert "d1" in result.deletes
        assert result.upserts == []

    def test_messages_deleted_still_exists_goes_to_upserts(self, client: GmailClient):
        """When .get() succeeds for a 'deleted' message, it moves to need_get."""
        mock_service = MagicMock()
        history = [{"messagesDeleted": [{"message": {"id": "d1"}}]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        mock_service.users().messages().get().execute.return_value = {"id": "d1"}
        client.service = mock_service
        with patch.object(client, "_batch_fetch_metadata", return_value=["meta_d1"]) as mock_batch:
            result = client._incremental_email_metadata("100")
        assert "d1" in mock_batch.call_args[0][0]
        assert result.upserts == ["meta_d1"]
        assert result.deletes == []

    def test_label_changes_not_in_get_or_delete_go_to_label_updates(self, client: GmailClient):
        """labelsAdded/Removed for messages not already in need_get/deletes → label_updates."""
        mock_service = MagicMock()
        history = [{
            "labelsAdded": [{"message": {"id": "la1"}, "labelIds": ["INBOX"]}],
            "labelsRemoved": [{"message": {"id": "lr1"}, "labelIds": ["UNREAD"]}],
        }]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        client.service = mock_service
        fake_updates = [MagicMock(), MagicMock()]
        with patch.object(client, "_batch_fetch_metadata", return_value=[]), \
             patch.object(client, "_batch_fetch_label_updates", return_value=fake_updates) as mock_lu:
            result = client._incremental_email_metadata("100")
        called_ids = set(mock_lu.call_args[0][0])
        assert called_ids == {"la1", "lr1"}
        assert result.label_updates == fake_updates

    def test_label_change_deduped_if_in_need_get(self, client: GmailClient):
        """A message in both messagesAdded and labelsAdded only appears in upserts."""
        mock_service = MagicMock()
        history = [{
            "messagesAdded": [{"message": {"id": "m1"}}],
            "labelsAdded": [{"message": {"id": "m1"}, "labelIds": ["INBOX"]}],
        }]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        client.service = mock_service
        with patch.object(client, "_batch_fetch_metadata", return_value=["meta1"]), \
             patch.object(client, "_batch_fetch_label_updates", return_value=[]) as mock_lu:
            result = client._incremental_email_metadata("100")
        # _batch_fetch_label_updates called with empty list (m1 already in need_get)
        assert mock_lu.call_count == 0 or mock_lu.call_args[0][0] == []
        assert result.upserts == ["meta1"]

    def test_pagination_aggregates_all_pages(self, client: GmailClient):
        """Paginates through multiple history.list pages."""
        mock_service = MagicMock()
        page1 = _make_history_response(
            history=[{"messagesAdded": [{"message": {"id": "m1"}}]}],
            history_id="150",
            next_page_token="token2",
        )
        page2 = _make_history_response(
            history=[{"messagesAdded": [{"message": {"id": "m2"}}]}],
            history_id="200",
        )
        mock_service.users().history().list().execute.side_effect = [page1, page2]
        client.service = mock_service
        with patch.object(client, "_batch_fetch_metadata", return_value=["meta1", "meta2"]) as mock_batch:
            result = client._incremental_email_metadata("100")
        called_ids = set(mock_batch.call_args[0][0])
        assert called_ids == {"m1", "m2"}
        assert result.new_cursor == "200"

    def test_history_list_http_error_raises(self, client: GmailClient):
        mock_service = MagicMock()
        from googleapiclient.errors import HttpError
        resp = MagicMock()
        type(resp).status = 410
        mock_service.users().history().list().execute.side_effect = HttpError(
            resp=resp, content=b"gone"
        )
        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="history.list failed"):
            client._incremental_email_metadata("100")


# ── _batch_fetch_label_updates ──────────────────────────────────────


class TestBatchFetchLabelUpdates:
    def test_parses_labels_to_label_update(self, client: GmailClient):
        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1", "labelIds": ["INBOX", "UNREAD"]}, None)
            cb("m2", {"id": "m2", "labelIds": ["SPAM"]}, None)
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        result = client._batch_fetch_label_updates(["m1", "m2"])

        assert len(result) == 2
        lu1 = next(lu for lu in result if lu.provider_message_id == "m1")
        assert lu1.is_read is False
        assert lu1.box == "ALL_MAIL"
        lu2 = next(lu for lu in result if lu.provider_message_id == "m2")
        assert lu2.is_read is True
        assert lu2.box == "SPAM"

    def test_skips_failed_messages(self, client: GmailClient):
        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", None, Exception("not found"))
            cb("m2", {"id": "m2", "labelIds": ["TRASH"]}, None)
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        result = client._batch_fetch_label_updates(["m1", "m2"])

        assert len(result) == 1
        assert result[0].provider_message_id == "m2"
        assert result[0].box == "TRASH"


# ── _list_message_ids ─────────────────────────────────────────────


class TestListMessageIds:
    def test_single_page(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "m1"}, {"id": "m2"}],
        }
        client.service = mock_service
        ids = client._list_message_ids(500)
        assert ids == ["m1", "m2"]

    def test_pagination_with_max_total(self, client: GmailClient):
        mock_service = MagicMock()
        page1 = {
            "messages": [{"id": f"m{i}"} for i in range(3)],
            "nextPageToken": "tok2",
        }
        page2 = {
            "messages": [{"id": f"m{i}"} for i in range(3, 6)],
        }
        mock_service.users().messages().list().execute.side_effect = [page1, page2]
        client.service = mock_service
        ids = client._list_message_ids(4)
        assert len(ids) == 4

    def test_http_error_raises_external_api_error(self, client: GmailClient):
        from googleapiclient.errors import HttpError
        mock_service = MagicMock()
        resp = MagicMock()
        type(resp).status = 500
        mock_service.users().messages().list().execute.side_effect = HttpError(
            resp=resp, content=b"fail"
        )
        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="fetch message list"):
            client._list_message_ids(500)

    def test_generic_exception_raises_external_api_error(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().messages().list().execute.side_effect = RuntimeError("boom")
        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="RuntimeError"):
            client._list_message_ids(500)


# ── _get_current_history_id ───────────────────────────────────────


class TestGetCurrentHistoryId:
    def test_happy_path(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {"historyId": "12345"}
        client.service = mock_service
        assert client._get_current_history_id() == "12345"

    def test_http_error_raises_external_api_error(self, client: GmailClient):
        from googleapiclient.errors import HttpError
        mock_service = MagicMock()
        resp = MagicMock()
        type(resp).status = 500
        mock_service.users().getProfile().execute.side_effect = HttpError(
            resp=resp, content=b"fail"
        )
        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="historyId"):
            client._get_current_history_id()

    def test_generic_exception_raises_external_api_error(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.side_effect = RuntimeError("boom")
        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="RuntimeError"):
            client._get_current_history_id()


# ── _bootstrap_email_metadata ─────────────────────────────────────


class TestBootstrapEmailMetadata:
    def test_calls_list_batch_history_and_returns_sync_result(self, client: GmailClient):
        client.service = MagicMock()
        with patch.object(client, "_list_message_ids", return_value=["m1", "m2"]) as mock_list, \
             patch.object(client, "_batch_fetch_metadata", return_value=["meta1", "meta2"]) as mock_batch, \
             patch.object(client, "_get_current_history_id", return_value="hist99") as mock_hist:
            result = client._bootstrap_email_metadata(500)

        mock_list.assert_called_once_with(500)
        mock_batch.assert_called_once_with(["m1", "m2"])
        mock_hist.assert_called_once()
        assert isinstance(result, SyncResult)
        assert result.upserts == ["meta1", "meta2"]
        assert result.new_cursor == "hist99"
