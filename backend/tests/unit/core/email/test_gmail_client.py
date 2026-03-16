"""Unit tests for GmailClient — build config, guard clauses, and metadata fetch.

Shared helper tests (parse_expiry, unwrap/wrap) live in ``test_helpers.py``.
"""

from __future__ import annotations

import base64
from datetime import datetime
from unittest.mock import MagicMock, call, patch

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
from core.email.gmail_client import GmailClient, _is_retryable, _INCREMENTAL_EVENT_THRESHOLD


@pytest.fixture
def client() -> GmailClient:
    return GmailClient(account_label="mb__acct")


# ── _is_retryable ───────────────────────────────────────────────────


class TestIsRetryable:
    def _make_http_error(self, status: int) -> Exception:
        from googleapiclient.errors import HttpError
        resp = MagicMock()
        type(resp).status = status
        return HttpError(resp=resp, content=b"err")

    def test_404_not_retryable(self):
        assert _is_retryable(self._make_http_error(404)) is False

    def test_400_not_retryable(self):
        assert _is_retryable(self._make_http_error(400)) is False

    def test_403_not_retryable(self):
        assert _is_retryable(self._make_http_error(403)) is False

    def test_410_not_retryable(self):
        assert _is_retryable(self._make_http_error(410)) is False

    def test_429_retryable(self):
        assert _is_retryable(self._make_http_error(429)) is True

    def test_500_retryable(self):
        assert _is_retryable(self._make_http_error(500)) is True

    def test_502_retryable(self):
        assert _is_retryable(self._make_http_error(502)) is True

    def test_503_retryable(self):
        assert _is_retryable(self._make_http_error(503)) is True

    def test_504_retryable(self):
        assert _is_retryable(self._make_http_error(504)) is True

    def test_non_http_error_retryable(self):
        assert _is_retryable(RuntimeError("timeout")) is True

    def test_generic_exception_retryable(self):
        assert _is_retryable(Exception("network error")) is True


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

    def test_sent(self):
        is_read, box = GmailClient._resolve_labels(["SENT"])
        assert is_read is True
        assert box == "SENT"

    def test_sent_with_inbox(self):
        is_read, box = GmailClient._resolve_labels(["SENT", "INBOX"])
        assert is_read is True
        assert box == "SENT"

    def test_trash_beats_spam(self):
        _, box = GmailClient._resolve_labels(["TRASH", "SPAM"])
        assert box == "TRASH"

    def test_trash_beats_sent(self):
        _, box = GmailClient._resolve_labels(["TRASH", "SENT"])
        assert box == "TRASH"

    def test_spam_beats_sent(self):
        _, box = GmailClient._resolve_labels(["SPAM", "SENT"])
        assert box == "SPAM"


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
        """When batch probe returns empty, the message is confirmed as delete."""
        mock_service = MagicMock()
        history = [{"messagesDeleted": [{"message": {"id": "d1"}}]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        client.service = mock_service
        with patch.object(client, "_execute_batch_get", return_value={}), \
             patch.object(client, "_batch_fetch_metadata", return_value=[]):
            result = client._incremental_email_metadata("100")
        assert "d1" in result.deletes
        assert result.upserts == []

    def test_messages_deleted_still_exists_goes_to_upserts(self, client: GmailClient):
        """When batch probe returns the message, it moves to need_get."""
        mock_service = MagicMock()
        history = [{"messagesDeleted": [{"message": {"id": "d1"}}]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="200")
        )
        client.service = mock_service
        with patch.object(client, "_execute_batch_get", return_value={"d1": {"id": "d1"}}), \
             patch.object(client, "_batch_fetch_metadata", return_value=["meta_d1"]) as mock_batch:
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

    @patch("core.email.gmail_client.time.sleep")
    def test_skips_failed_messages(self, mock_sleep, client: GmailClient):
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


# ── _execute_batch_get retry logic ──────────────────────────────────


class TestExecuteBatchGetSequentialFallback:
    """Tests for the sequential fallback when _credentials is None."""

    def test_no_failures_no_retry(self, client: GmailClient):
        """All messages succeed on the first attempt — batch.execute() called once."""
        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
            cb("m2", {"id": "m2"}, None)
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        assert client._credentials is None
        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert set(result.keys()) == {"m1", "m2"}
        assert batch_instance.execute.call_count == 1

    @patch("core.email.gmail_client.time.sleep")
    def test_partial_failure_retries_only_failed(self, mock_sleep, client: GmailClient):
        """2 of 5 fail, retry succeeds — second batch only contains the 2 failed."""
        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        call_count = 0

        def fake_execute():
            nonlocal call_count
            call_count += 1
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            if call_count == 1:
                cb("m1", {"id": "m1"}, None)
                cb("m2", {"id": "m2"}, None)
                cb("m3", {"id": "m3"}, None)
                cb("m4", None, Exception("rate limited"))
                cb("m5", None, Exception("rate limited"))
            else:
                cb("m4", {"id": "m4"}, None)
                cb("m5", {"id": "m5"}, None)
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        result = client._execute_batch_get(
            ["m1", "m2", "m3", "m4", "m5"], fmt="metadata", error_context="test",
        )
        assert set(result.keys()) == {"m1", "m2", "m3", "m4", "m5"}
        assert batch_instance.execute.call_count == 2
        mock_sleep.assert_called_once()

    @patch("core.email.gmail_client.time.sleep")
    def test_all_retries_exhausted_messages_lost(self, mock_sleep, client: GmailClient):
        """A message fails on every attempt and is not in the final result."""
        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            added_ids = [c.kwargs["request_id"] for c in batch_instance.add.call_args_list]
            batch_instance.add.call_args_list.clear()
            for rid in added_ids:
                if rid == "m2":
                    cb(rid, None, Exception("always fails"))
                else:
                    cb(rid, {"id": rid}, None)
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert "m1" in result
        assert "m2" not in result
        assert batch_instance.execute.call_count == 5
        assert mock_sleep.call_count == 4

    @patch("core.email.gmail_client.time.sleep")
    def test_retry_with_fixed_delay(self, mock_sleep, client: GmailClient):
        """Verify sleep delays are all 1.0s (fixed delay)."""
        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", None, Exception("fail"))
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        client._execute_batch_get(["m1"], fmt="metadata", error_context="test")
        assert mock_sleep.call_args_list == [call(1.0), call(1.0), call(1.0), call(1.0)]

    def test_batch_execute_exception_raises(self, client: GmailClient):
        """HttpError from batch.execute() raises EmailExternalAPIError."""
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance
        resp = MagicMock()
        type(resp).status = 500
        batch_instance.execute.side_effect = HttpError(resp=resp, content=b"fail")

        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="test failed"):
            client._execute_batch_get(["m1"], fmt="metadata", error_context="test")

    def test_empty_message_ids_returns_empty(self, client: GmailClient):
        """Empty input returns empty dict without calling the service."""
        client.service = MagicMock()
        result = client._execute_batch_get([], fmt="metadata", error_context="test")
        assert result == {}


class TestExecuteBatchGetParallel:
    """Tests for the parallel path (when _credentials is set)."""

    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_success_all_chunks(self, mock_auth_http, mock_build, client: GmailClient):
        """All messages succeed on first attempt via parallel path."""
        client.service = MagicMock()
        client._credentials = MagicMock()

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
            cb("m2", {"id": "m2"}, None)
        batch_instance.execute.side_effect = fake_execute

        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert set(result.keys()) == {"m1", "m2"}

    @patch("core.email.gmail_client.time.sleep")
    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_partial_failure_retries(self, mock_auth_http, mock_build, mock_sleep, client: GmailClient):
        """Failed IDs are retried in subsequent attempts."""
        client.service = MagicMock()
        client._credentials = MagicMock()

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        call_count = 0

        def fake_execute():
            nonlocal call_count
            call_count += 1
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            if call_count == 1:
                cb("m1", {"id": "m1"}, None)
                cb("m2", None, Exception("rate limited"))
            else:
                cb("m2", {"id": "m2"}, None)
        batch_instance.execute.side_effect = fake_execute

        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert set(result.keys()) == {"m1", "m2"}
        mock_sleep.assert_called_once_with(1.0)

    @patch("core.email.gmail_client.time.sleep")
    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_all_retries_exhausted(self, mock_auth_http, mock_build, mock_sleep, client: GmailClient):
        """A message that always fails is lost after all retries."""
        client.service = MagicMock()
        client._credentials = MagicMock()

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            added_ids = [c.kwargs["request_id"] for c in batch_instance.add.call_args_list]
            batch_instance.add.call_args_list.clear()
            for rid in added_ids:
                if rid == "m2":
                    cb(rid, None, Exception("always fails"))
                else:
                    cb(rid, {"id": rid}, None)
        batch_instance.execute.side_effect = fake_execute

        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert "m1" in result
        assert "m2" not in result
        assert mock_sleep.call_count == 4

    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_chunk_level_exception_marks_all_failed(self, mock_auth_http, mock_build, client: GmailClient):
        """An exception in batch.execute() marks all chunk IDs as failed (no raise)."""
        client.service = MagicMock()
        client._credentials = MagicMock()

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance
        batch_instance.execute.side_effect = RuntimeError("connection reset")

        result = client._execute_batch_get(
            ["m1"], fmt="metadata", error_context="test",
        )
        assert "m1" not in result


class TestExecuteSingleChunk:
    """Tests for _execute_single_chunk."""

    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_success(self, mock_auth_http, mock_build, client: GmailClient):
        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
        batch_instance.execute.side_effect = fake_execute

        successes, failed, permanent_failed, elapsed = client._execute_single_chunk(
            ["m1"], 0, fmt="metadata",
            credentials=MagicMock(),
        )
        assert successes == {"m1": {"id": "m1"}}
        assert failed == []
        assert permanent_failed == []
        assert elapsed >= 0

    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_partial_failure(self, mock_auth_http, mock_build, client: GmailClient):
        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        def fake_execute():
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
            cb("m2", None, Exception("fail"))
        batch_instance.execute.side_effect = fake_execute

        successes, failed, permanent_failed, elapsed = client._execute_single_chunk(
            ["m1", "m2"], 0, fmt="metadata",
            credentials=MagicMock(),
        )
        assert successes == {"m1": {"id": "m1"}}
        assert failed == ["m2"]
        assert permanent_failed == []

    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_total_exception(self, mock_auth_http, mock_build, client: GmailClient):
        """batch.execute() raises — all IDs marked failed, no exception propagated."""
        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance
        batch_instance.execute.side_effect = RuntimeError("connection reset")

        successes, failed, permanent_failed, elapsed = client._execute_single_chunk(
            ["m1", "m2"], 0, fmt="metadata",
            credentials=MagicMock(),
        )
        assert successes == {}
        assert set(failed) == {"m1", "m2"}
        assert permanent_failed == []


    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_non_retryable_callback_goes_to_permanent_failed(self, mock_auth_http, mock_build, client: GmailClient):
        """HttpError 404 in callback → permanent_failed, not retryable failed."""
        from googleapiclient.errors import HttpError

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        resp_404 = MagicMock()
        type(resp_404).status = 404

        def fake_execute():
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
            cb("m2", None, HttpError(resp=resp_404, content=b"not found"))
        batch_instance.execute.side_effect = fake_execute

        successes, failed, permanent_failed, elapsed = client._execute_single_chunk(
            ["m1", "m2"], 0, fmt="metadata",
            credentials=MagicMock(),
        )
        assert successes == {"m1": {"id": "m1"}}
        assert failed == []
        assert permanent_failed == ["m2"]

    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_chunk_level_non_retryable_http_error(self, mock_auth_http, mock_build, client: GmailClient):
        """Non-retryable HttpError from batch.execute() → all IDs permanently failed."""
        from googleapiclient.errors import HttpError

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        resp_400 = MagicMock()
        type(resp_400).status = 400
        batch_instance.execute.side_effect = HttpError(resp=resp_400, content=b"bad request")

        successes, failed, permanent_failed, elapsed = client._execute_single_chunk(
            ["m1", "m2"], 0, fmt="metadata",
            credentials=MagicMock(),
        )
        assert successes == {}
        assert failed == []
        assert set(permanent_failed) == {"m1", "m2"}


# ── Non-retryable errors skip retry in batch paths ──────────────


class TestNonRetryableSkipsRetry:
    """Non-retryable errors (e.g. 404) must not trigger retry loops."""

    @patch("core.email.gmail_client.time.sleep")
    def test_sequential_path_no_retry_for_404(self, mock_sleep, client: GmailClient):
        """HttpError 404 in sequential callback → no retry, message simply missing."""
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        batch_instance = MagicMock()
        mock_service.new_batch_http_request.return_value = batch_instance

        resp_404 = MagicMock()
        type(resp_404).status = 404

        def fake_execute():
            cb = mock_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
            cb("m2", None, HttpError(resp=resp_404, content=b"not found"))
        batch_instance.execute.side_effect = fake_execute

        client.service = mock_service
        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert "m1" in result
        assert "m2" not in result
        assert batch_instance.execute.call_count == 1
        mock_sleep.assert_not_called()

    @patch("core.email.gmail_client.time.sleep")
    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.google_auth_httplib2.AuthorizedHttp")
    def test_parallel_path_no_retry_for_404(self, mock_auth_http, mock_build, mock_sleep, client: GmailClient):
        """HttpError 404 in parallel callback → no retry, message simply missing."""
        from googleapiclient.errors import HttpError

        client.service = MagicMock()
        client._credentials = MagicMock()

        thread_service = MagicMock()
        mock_build.return_value = thread_service
        batch_instance = MagicMock()
        thread_service.new_batch_http_request.return_value = batch_instance

        resp_404 = MagicMock()
        type(resp_404).status = 404

        def fake_execute():
            cb = thread_service.new_batch_http_request.call_args[1]["callback"]
            cb("m1", {"id": "m1"}, None)
            cb("m2", None, HttpError(resp=resp_404, content=b"not found"))
        batch_instance.execute.side_effect = fake_execute

        result = client._execute_batch_get(
            ["m1", "m2"], fmt="metadata", error_context="test",
        )
        assert "m1" in result
        assert "m2" not in result
        assert batch_instance.execute.call_count == 1
        mock_sleep.assert_not_called()


# ── authenticate ─────────────────────────────────────────────────


class TestAuthenticate:
    @patch("core.email.gmail_client.build")
    @patch("core.email.gmail_client.InstalledAppFlow")
    def test_builds_flow_and_returns_wrapped_tokens(self, mock_flow_cls, mock_build, client: GmailClient):
        """Happy path: flow runs, service is set, and wrapped tokens are returned."""
        mock_creds = MagicMock()
        mock_creds.token = "access-tok"
        mock_creds.refresh_token = "refresh-tok"
        mock_creds.expiry = None
        mock_creds.scopes = ["https://mail.google.com/"]

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_config.return_value = mock_flow

        result = client.authenticate(app_credentials={"client_id": "id", "client_secret": "secret"})

        mock_flow_cls.from_client_config.assert_called_once()
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)
        assert client.service is not None
        assert result["access_token"].get_secret_value() == "access-tok"
        assert result["refresh_token"].get_secret_value() == "refresh-tok"

    @patch("core.email.gmail_client.InstalledAppFlow")
    def test_flow_build_failure_raises_missing_credentials(self, mock_flow_cls, client: GmailClient):
        mock_flow_cls.from_client_config.side_effect = ValueError("bad config")

        with pytest.raises(EmailMissingAppCredentialsError, match="failed to build OAuth flow"):
            client.authenticate(app_credentials={"client_id": "id", "client_secret": "secret"})

    @patch("core.email.gmail_client.InstalledAppFlow")
    def test_server_os_error_raises_external_api(self, mock_flow_cls, client: GmailClient):
        mock_flow = MagicMock()
        mock_flow.run_local_server.side_effect = OSError("port in use")
        mock_flow_cls.from_client_config.return_value = mock_flow

        with pytest.raises(EmailExternalAPIError, match="local OAuth callback server"):
            client.authenticate(app_credentials={"client_id": "id", "client_secret": "secret"})

    @patch("core.email.gmail_client.InstalledAppFlow")
    def test_server_unexpected_error_raises_external_api(self, mock_flow_cls, client: GmailClient):
        mock_flow = MagicMock()
        mock_flow.run_local_server.side_effect = RuntimeError("unexpected")
        mock_flow_cls.from_client_config.return_value = mock_flow

        with pytest.raises(EmailExternalAPIError, match="unexpected OAuth flow error"):
            client.authenticate(app_credentials={"client_id": "id", "client_secret": "secret"})


# ── send_email ───────────────────────────────────────────────────


class TestSendEmail:
    def _setup_send_mock(self, client: GmailClient, send_response: dict | None = None):
        """Set up mock service for send_email with proper MagicMock chaining."""
        mock_service = MagicMock()
        client.service = mock_service
        if send_response is None:
            send_response = {"id": "msg1", "threadId": "th1", "labelIds": ["SENT"]}
        # Chain: service.users().messages().send(userId=..., body=...).execute()
        mock_service.users.return_value.messages.return_value.send.return_value.execute.return_value = send_response
        return mock_service

    def test_constructs_mime_and_calls_api(self, client: GmailClient):
        """Verify MIME message structure and API call."""
        mock_service = self._setup_send_mock(client)
        with patch.object(client, "_batch_fetch_metadata", return_value=[]):
            client.send_email("Test Subject", "Test Body", ["a@b.com"])

        send_fn = mock_service.users.return_value.messages.return_value.send
        send_fn.assert_called_once()
        call_kwargs = send_fn.call_args
        body = call_kwargs[1]["body"]
        raw_bytes = base64.urlsafe_b64decode(body["raw"])
        raw_text = raw_bytes.decode("utf-8")
        assert "Test Subject" in raw_text
        assert "Test Body" in raw_text
        assert "a@b.com" in raw_text

    def test_returns_metadata_from_batch_fetch(self, client: GmailClient):
        """send_email returns EmailMetadata fetched via _batch_fetch_metadata."""
        from core.email.email_client import EmailMetadata
        self._setup_send_mock(client, {"id": "msg123", "threadId": "th456", "labelIds": ["SENT"]})
        expected = EmailMetadata(
            provider_message_id="msg123", thread_id="th456",
            from_email="me@gmail.com", from_name="Me",
            subject="Hello", received_at=datetime(2024, 1, 1),
            is_read=True, box="SENT",
        )
        with patch.object(client, "_batch_fetch_metadata", return_value=[expected]) as mock_fetch:
            result = client.send_email("Hello", "Body", ["a@b.com"])

        mock_fetch.assert_called_once_with(["msg123"])
        assert result is expected

    def test_returns_fallback_metadata_when_fetch_empty(self, client: GmailClient):
        """When _batch_fetch_metadata returns empty, fallback metadata is built."""
        self._setup_send_mock(client, {"id": "msg123", "threadId": "th456"})
        with patch.object(client, "_batch_fetch_metadata", return_value=[]):
            result = client.send_email("Subject", "Body", ["a@b.com"])

        assert result.provider_message_id == "msg123"
        assert result.thread_id == "th456"
        assert result.box == "SENT"
        assert result.is_read is True
        assert result.subject == "Subject"

    def test_http_error_raises_external_api(self, client: GmailClient):
        from googleapiclient.errors import HttpError

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.reason = "Forbidden"
        http_err = HttpError(resp=mock_resp, content=b"forbidden")

        mock_service = self._setup_send_mock(client)
        mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = http_err

        with pytest.raises(EmailExternalAPIError, match="Gmail failed to send email"):
            client.send_email("S", "B", ["a@b.com"])

    def test_unexpected_error_raises_external_api(self, client: GmailClient):
        mock_service = self._setup_send_mock(client)
        mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = RuntimeError("boom")

        with pytest.raises(EmailExternalAPIError, match="Gmail unexpected send email error"):
            client.send_email("S", "B", ["a@b.com"])

    def test_supplements_subject_when_batch_fetch_returns_empty(self, client: GmailClient):
        """Batch fetch returns EmailMetadata with empty subject — supplemented from parameter."""
        from core.email.email_client import EmailMetadata
        self._setup_send_mock(client, {"id": "msg1", "threadId": "th1"})
        fetched = EmailMetadata(
            provider_message_id="msg1", thread_id="th1",
            from_email="me@gmail.com", from_name="Me",
            subject="", received_at=datetime(2024, 1, 1),
            is_read=True, box="SENT",
        )
        with patch.object(client, "_batch_fetch_metadata", return_value=[fetched]):
            result = client.send_email("Real Subject", "Body", ["a@b.com"])
        assert result.subject == "Real Subject"

    def test_supplements_from_email_from_profile(self, client: GmailClient):
        """Batch fetch returns empty from_email — supplemented from getProfile."""
        from core.email.email_client import EmailMetadata
        self._setup_send_mock(client, {"id": "msg1", "threadId": "th1"})
        fetched = EmailMetadata(
            provider_message_id="msg1", thread_id="th1",
            from_email="", from_name="",
            subject="S", received_at=datetime(2024, 1, 1),
            is_read=True, box="SENT",
        )
        with patch.object(client, "_batch_fetch_metadata", return_value=[fetched]), \
             patch.object(client, "_fetch_sender_email", return_value="me@gmail.com"):
            result = client.send_email("S", "Body", ["a@b.com"])
        assert result.from_email == "me@gmail.com"

    def test_supplements_from_name_with_from_email(self, client: GmailClient):
        """Batch fetch returns from_email but empty from_name — from_name set to from_email."""
        from core.email.email_client import EmailMetadata
        self._setup_send_mock(client, {"id": "msg1", "threadId": "th1"})
        fetched = EmailMetadata(
            provider_message_id="msg1", thread_id="th1",
            from_email="me@gmail.com", from_name="",
            subject="S", received_at=datetime(2024, 1, 1),
            is_read=True, box="SENT",
        )
        with patch.object(client, "_batch_fetch_metadata", return_value=[fetched]):
            result = client.send_email("S", "Body", ["a@b.com"])
        assert result.from_name == "me@gmail.com"

    def test_fallback_metadata_uses_profile_email(self, client: GmailClient):
        """Fallback path (batch fetch empty) uses profile email for from fields."""
        self._setup_send_mock(client, {"id": "msg1", "threadId": "th1"})
        with patch.object(client, "_batch_fetch_metadata", return_value=[]), \
             patch.object(client, "_fetch_sender_email", return_value="me@gmail.com"):
            result = client.send_email("Subject", "Body", ["a@b.com"])
        assert result.from_email == "me@gmail.com"
        assert result.from_name == "me@gmail.com"
        assert result.subject == "Subject"


class TestFetchSenderEmail:
    def test_caches_result(self, client: GmailClient):
        """_fetch_sender_email calls getProfile only once, caches for subsequent calls."""
        mock_service = MagicMock()
        client.service = mock_service
        mock_service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "me@gmail.com",
        }
        first = client._fetch_sender_email()
        second = client._fetch_sender_email()
        assert first == "me@gmail.com"
        assert second == "me@gmail.com"
        mock_service.users.return_value.getProfile.return_value.execute.assert_called_once()

    def test_returns_empty_on_error(self, client: GmailClient):
        """_fetch_sender_email returns empty string when getProfile raises."""
        mock_service = MagicMock()
        client.service = mock_service
        mock_service.users.return_value.getProfile.return_value.execute.side_effect = RuntimeError("boom")
        result = client._fetch_sender_email()
        assert result == ""


# ── verify_message_existence ───────────────────────────────────────


class TestVerifyMessageExistence:
    def test_not_authenticated_raises(self, client: GmailClient):
        with pytest.raises(EmailNotAuthenticatedError):
            client.verify_message_existence(["m1"])

    def test_empty_list_returns_empty(self, client: GmailClient):
        client.service = MagicMock()
        assert client.verify_message_existence([]) == []

    def test_all_exist(self, client: GmailClient):
        client.service = MagicMock()
        with patch.object(
            client, "_execute_batch_get",
            return_value={"m1": {"id": "m1"}, "m2": {"id": "m2"}},
        ):
            result = client.verify_message_existence(["m1", "m2"])
        assert result == ["m1", "m2"]

    def test_some_missing(self, client: GmailClient):
        client.service = MagicMock()
        with patch.object(
            client, "_execute_batch_get",
            return_value={"m1": {"id": "m1"}},
        ):
            result = client.verify_message_existence(["m1", "m2", "m3"])
        assert result == ["m1"]

    def test_all_missing(self, client: GmailClient):
        client.service = MagicMock()
        with patch.object(client, "_execute_batch_get", return_value={}):
            result = client.verify_message_existence(["m1", "m2"])
        assert result == []


# ── is_full_sync flag ──────────────────────────────────────────────


class TestBootstrapIsFullSync:
    def test_bootstrap_sets_is_full_sync_true(self, client: GmailClient):
        client.service = MagicMock()
        with patch.object(client, "_list_message_ids", return_value=[]), \
             patch.object(client, "_batch_fetch_metadata", return_value=[]), \
             patch.object(client, "_get_current_history_id", return_value="hist1"):
            result = client._bootstrap_email_metadata(500)
        assert result.is_full_sync is True


class TestIncrementalIsFullSync:
    def test_incremental_sets_is_full_sync_false(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=[], history_id="200")
        )
        client.service = mock_service
        result = client._incremental_email_metadata("100")
        assert result.is_full_sync is False


# ── incremental threshold ─────────────────────────────────────────


class TestIncrementalThreshold:
    def test_threshold_triggers_fallback(self, client: GmailClient):
        mock_service = MagicMock()
        ids_count = _INCREMENTAL_EVENT_THRESHOLD + 1
        history = [{"messagesAdded": [
            {"message": {"id": f"m{i}"}} for i in range(ids_count)
        ]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="999")
        )
        client.service = mock_service
        with pytest.raises(EmailExternalAPIError, match="exceeding threshold"):
            client._incremental_email_metadata("50")

    def test_at_threshold_does_not_trigger(self, client: GmailClient):
        mock_service = MagicMock()
        history = [{"messagesAdded": [
            {"message": {"id": f"m{i}"}} for i in range(_INCREMENTAL_EVENT_THRESHOLD)
        ]}]
        mock_service.users().history().list().execute.return_value = (
            _make_history_response(history=history, history_id="999")
        )
        client.service = mock_service
        with patch.object(client, "_batch_fetch_metadata", return_value=[]):
            result = client._incremental_email_metadata("50")
        assert isinstance(result, SyncResult)
