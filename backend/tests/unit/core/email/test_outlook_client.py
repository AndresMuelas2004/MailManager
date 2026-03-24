"""Unit tests for OutlookClient — provider-specific logic, guard clauses, and refresh path.

Shared helper tests (parse_expiry, unwrap/wrap) live in ``test_helpers.py``.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from pydantic import SecretStr

from core.email.email_client import EmailMetadata, LabelUpdate, SpamMoveResult, SyncResult
from core.email.errors import (
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from core.email.outlook_client import (
    GRAPH_BASE_URL,
    OUTLOOK_SCOPES,
    OutlookClient,
    _DELTA_FOLDERS,
    _DELTA_SELECT_FIELDS,
    _DELTA_PAGE_SIZE,
    _FOLDER_TO_BOX,
)


@pytest.fixture
def client() -> OutlookClient:
    return OutlookClient(account_label="mb__outlook")


# ── get_account_label ────────────────────────────────────────────────


def test_get_account_label_returns_constructor_value(client: OutlookClient):
    assert client.get_account_label() == "mb__outlook"


# ── _token_url ───────────────────────────────────────────────────────


def test_token_url_returns_correct_format():
    url = OutlookClient._token_url("my-tenant")
    assert url == "https://login.microsoftonline.com/my-tenant/oauth2/v2.0/token"


# ── _compute_expiry ──────────────────────────────────────────────────


class TestComputeExpiry:
    def test_valid_seconds(self):
        before = datetime.now(timezone.utc)
        result = OutlookClient._compute_expiry(3600)
        after = datetime.now(timezone.utc) + timedelta(seconds=3600)
        parsed = datetime.fromisoformat(result)
        assert before <= parsed <= after

    def test_none_returns_none(self):
        assert OutlookClient._compute_expiry(None) is None

    def test_negative_clamped_to_zero(self):
        before = datetime.now(timezone.utc)
        result = OutlookClient._compute_expiry(-10)
        parsed = datetime.fromisoformat(result)
        assert before <= parsed <= before + timedelta(seconds=2)

    def test_invalid_type_returns_none(self):
        assert OutlookClient._compute_expiry("not-a-number") is None


# ── _resolve_scopes ──────────────────────────────────────────────────


class TestResolveScopes:
    def test_from_credentials_list(self, client: OutlookClient):
        creds = {"scopes": ["scope1", "scope2"]}
        result = client._resolve_scopes(creds)
        assert result == ["scope1", "scope2"]

    def test_from_credentials_string_comma_separated(self, client: OutlookClient):
        creds = {"scopes": "scope1,scope2,scope3"}
        result = client._resolve_scopes(creds)
        assert result == ["scope1", "scope2", "scope3"]

    def test_from_credentials_string_space_separated(self, client: OutlookClient):
        creds = {"scopes": "scope1 scope2 scope3"}
        result = client._resolve_scopes(creds)
        assert result == ["scope1", "scope2", "scope3"]

    def test_from_token_payload_fallback(self, client: OutlookClient):
        creds = {}
        token_payload = {"scopes": ["tok_scope1"]}
        result = client._resolve_scopes(creds, token_payload)
        assert result == ["tok_scope1"]

    def test_defaults_to_outlook_scopes(self, client: OutlookClient):
        result = client._resolve_scopes({})
        assert result == list(OUTLOOK_SCOPES)


# ── Guard clauses ────────────────────────────────────────────────────


class TestGuardClauses:
    def test_authenticate_missing_credentials_raises_error(self, client: OutlookClient):
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate(app_credentials=None)

    def test_authenticate_missing_credentials_empty_dict_raises_error(self, client: OutlookClient):
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate(app_credentials={})

    def test_authenticate_silent_missing_credentials_raises_error(self, client: OutlookClient):
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate_silent(app_credentials=None)

    def test_authenticate_silent_missing_access_token_raises_error(self, client: OutlookClient):
        creds = {"client_id": "id", "client_secret": "s", "tenant": "t"}
        with pytest.raises(EmailMissingTokenError):
            client.authenticate_silent(app_credentials=creds, user_tokens={})

    def test_authenticate_silent_expired_no_refresh_token_raises_error(
        self, client: OutlookClient
    ):
        creds = {"client_id": "id", "client_secret": "secret", "tenant": "t"}
        tokens = {
            "access_token": "at",
            "refresh_token": None,
            "expiry": "2020-01-01T00:00:00",
        }
        with pytest.raises(EmailMissingRefreshTokenError):
            client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_authenticate_silent_not_expired_sets_access_token_returns_none(
        self, client: OutlookClient
    ):
        creds = {"client_id": "id", "client_secret": "secret", "tenant": "t"}
        future_expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        tokens = {
            "access_token": "valid_token",
            "refresh_token": "rt",
            "expiry": future_expiry,
        }
        result = client.authenticate_silent(app_credentials=creds, user_tokens=tokens)
        assert result is None
        assert client._access_token == "valid_token"

    def test_authenticate_silent_missing_client_id_or_secret_raises_error(
        self, client: OutlookClient
    ):
        creds = {"tenant": "t"}
        tokens = {
            "access_token": "at",
            "refresh_token": "rt",
            "expiry": "2020-01-01T00:00:00",
        }
        with pytest.raises(EmailMissingAppCredentialsError, match="Missing required"):
            client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_fetch_email_metadata_not_authenticated_raises_error(self, client: OutlookClient):
        """Unauthenticated fetch raises EmailNotAuthenticatedError."""
        assert client._access_token is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.fetch_email_metadata()

    def test_send_email_not_authenticated_raises_error(self, client: OutlookClient):
        assert client._access_token is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.send_email("subj", "body", ["a@b.com"])

    def test_send_email_empty_recipients_raises_error(self, client: OutlookClient):
        client._access_token = "token"
        with pytest.raises(EmailRecipientsMissingError):
            client.send_email("subj", "body", [])


# ── authenticate_silent refresh path (mock _token_request) ───────────


class TestAuthenticateSilentRefreshPath:
    """Test the refresh logic by mocking _token_request."""

    def _make_expired_setup(self):
        creds = {
            "client_id": "cid",
            "client_secret": "csecret",
            "tenant": "my-tenant",
        }
        tokens = {
            "access_token": "old_at",
            "refresh_token": "old_rt",
            "expiry": "2020-01-01T00:00:00",
        }
        return creds, tokens

    def test_expired_refreshes_and_returns_wrapped_tokens(self, client: OutlookClient):
        creds, tokens = self._make_expired_setup()
        mock_response = {
            "access_token": "new_at",
            "refresh_token": "new_rt",
            "expires_in": 3600,
        }
        with patch.object(client, "_token_request", return_value=mock_response):
            result = client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

        assert result is not None
        assert isinstance(result["access_token"], SecretStr)
        assert result["access_token"].get_secret_value() == "new_at"
        assert isinstance(result["refresh_token"], SecretStr)
        assert result["refresh_token"].get_secret_value() == "new_rt"
        assert client._access_token == "new_at"

    def test_refresh_failure_raises_refresh_failed(self, client: OutlookClient):
        creds, tokens = self._make_expired_setup()
        with patch.object(
            client, "_token_request", side_effect=Exception("network error")
        ):
            with pytest.raises(EmailRefreshFailedError, match="network error"):
                client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_refresh_missing_access_token_raises_refresh_failed(self, client: OutlookClient):
        creds, tokens = self._make_expired_setup()
        mock_response = {"refresh_token": "new_rt"}
        with patch.object(client, "_token_request", return_value=mock_response):
            with pytest.raises(EmailRefreshFailedError, match="missing access_token"):
                client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_refresh_preserves_rotated_refresh_token(self, client: OutlookClient):
        creds, tokens = self._make_expired_setup()
        mock_response = {
            "access_token": "new_at",
            "refresh_token": "rotated_rt",
            "expires_in": 3600,
        }
        with patch.object(client, "_token_request", return_value=mock_response):
            result = client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

        assert result["refresh_token"].get_secret_value() == "rotated_rt"

    def test_refresh_no_new_refresh_token_keeps_original(self, client: OutlookClient):
        """When Microsoft doesn't rotate the refresh token, the original is preserved."""
        creds, tokens = self._make_expired_setup()
        mock_response = {
            "access_token": "new_at",
            "expires_in": 3600,
        }
        with patch.object(client, "_token_request", return_value=mock_response):
            result = client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

        assert result["refresh_token"].get_secret_value() == "old_rt"


# ── Helpers for metadata sync tests ─────────────────────────────────


def _make_graph_message(
    msg_id: str = "msg1",
    *,
    conversation_id: str = "conv1",
    from_address: str = "alice@example.com",
    from_name: str = "Alice",
    subject: str = "Hello",
    received: str = "2025-06-01T12:00:00Z",
    is_read: bool = True,
    parent_folder_id: str = "",
) -> dict:
    """Build a Graph message resource for testing."""
    msg: dict = {
        "id": msg_id,
        "conversationId": conversation_id,
        "from": {"emailAddress": {"address": from_address, "name": from_name}},
        "subject": subject,
        "receivedDateTime": received,
        "isRead": is_read,
    }
    if parent_folder_id:
        msg["parentFolderId"] = parent_folder_id
    return msg


def _make_authenticated_client() -> OutlookClient:
    client = OutlookClient(account_label="mb__outlook")
    client._access_token = "token"
    return client


def _make_folder_cursor(**overrides: str) -> str:
    """Build a JSON cursor with per-folder deltaLinks."""
    folders = {}
    for folder in _DELTA_FOLDERS:
        folders[folder] = overrides.get(folder, f"https://delta-{folder}")
    return OutlookClient._encode_folder_cursors(folders)


# ── _encode_folder_cursors / _decode_folder_cursors ──────────────────


class TestEncodeFolderCursors:
    def test_roundtrip(self):
        original = {"inbox": "https://delta-inbox", "drafts": "https://delta-drafts"}
        encoded = OutlookClient._encode_folder_cursors(original)
        decoded = OutlookClient._decode_folder_cursors(encoded)
        assert decoded == original

    def test_encode_produces_valid_json(self):
        encoded = OutlookClient._encode_folder_cursors({"inbox": "link"})
        parsed = json.loads(encoded)
        assert parsed["v"] == 1
        assert parsed["folders"] == {"inbox": "link"}


class TestDecodeFolderCursors:
    def test_valid_cursor(self):
        cursor = json.dumps({"v": 1, "folders": {"inbox": "link"}})
        assert OutlookClient._decode_folder_cursors(cursor) == {"inbox": "link"}

    def test_legacy_url_cursor_returns_none(self):
        assert OutlookClient._decode_folder_cursors("https://old-delta-link") is None

    def test_malformed_json_returns_none(self):
        assert OutlookClient._decode_folder_cursors("not-json{") is None

    def test_missing_version_returns_none(self):
        cursor = json.dumps({"folders": {"inbox": "link"}})
        assert OutlookClient._decode_folder_cursors(cursor) is None

    def test_wrong_version_returns_none(self):
        cursor = json.dumps({"v": 2, "folders": {"inbox": "link"}})
        assert OutlookClient._decode_folder_cursors(cursor) is None

    def test_missing_folders_key_returns_none(self):
        cursor = json.dumps({"v": 1})
        assert OutlookClient._decode_folder_cursors(cursor) is None

    def test_folders_not_dict_returns_none(self):
        cursor = json.dumps({"v": 1, "folders": "not-a-dict"})
        assert OutlookClient._decode_folder_cursors(cursor) is None


# ── _parse_graph_message ────────────────────────────────────────────


class TestParseGraphMessage:
    def test_full_message(self):
        msg = _make_graph_message()
        result = OutlookClient._parse_graph_message(msg, "ALL_MAIL")
        assert result.provider_message_id == "msg1"
        assert result.thread_id == "conv1"
        assert result.from_email == "alice@example.com"
        assert result.from_name == "Alice"
        assert result.subject == "Hello"
        assert result.is_read is True
        assert result.box == "ALL_MAIL"
        assert result.received_at.year == 2025

    def test_missing_from_field(self):
        msg = _make_graph_message()
        del msg["from"]
        result = OutlookClient._parse_graph_message(msg, "ALL_MAIL")
        assert result.from_email == ""
        assert result.from_name == ""

    def test_invalid_date_falls_back_to_now(self):
        msg = _make_graph_message(received="not-a-date")
        result = OutlookClient._parse_graph_message(msg, "ALL_MAIL")
        assert (datetime.now(timezone.utc) - result.received_at).total_seconds() < 5

    def test_missing_conversation_id(self):
        msg = _make_graph_message()
        del msg["conversationId"]
        result = OutlookClient._parse_graph_message(msg, "SPAM")
        assert result.thread_id == ""

    def test_is_read_false(self):
        msg = _make_graph_message(is_read=False)
        result = OutlookClient._parse_graph_message(msg, "ALL_MAIL")
        assert result.is_read is False

    def test_box_passed_through(self):
        msg = _make_graph_message()
        assert OutlookClient._parse_graph_message(msg, "SPAM").box == "SPAM"
        assert OutlookClient._parse_graph_message(msg, "TRASH").box == "TRASH"
        assert OutlookClient._parse_graph_message(msg, "ALL_MAIL").box == "ALL_MAIL"
        assert OutlookClient._parse_graph_message(msg, "SENT").box == "SENT"


# ── fetch_email_metadata routing ────────────────────────────────────


class TestFetchEmailMetadata:
    def test_no_cursor_calls_bootstrap(self):
        client = _make_authenticated_client()
        expected = SyncResult(upserts=[], new_cursor="delta-link")
        with patch.object(client, "_bootstrap_email_metadata", return_value=expected) as mock:
            result = client.fetch_email_metadata(sync_cursor=None, max_total=100)
        mock.assert_called_once_with(100)
        assert result is expected

    def test_cursor_calls_incremental(self):
        client = _make_authenticated_client()
        expected = SyncResult(upserts=[], new_cursor="new-delta-link")
        with patch.object(client, "_incremental_email_metadata", return_value=expected) as mock:
            result = client.fetch_email_metadata(sync_cursor="old-delta-link")
        mock.assert_called_once_with("old-delta-link")
        assert result is expected

    def test_incremental_failure_falls_back_to_bootstrap(self):
        client = _make_authenticated_client()
        bootstrap_result = SyncResult(upserts=[], new_cursor="fresh-delta")
        with (
            patch.object(
                client,
                "_incremental_email_metadata",
                side_effect=EmailExternalAPIError("expired"),
            ),
            patch.object(
                client, "_bootstrap_email_metadata", return_value=bootstrap_result,
            ) as boot_mock,
        ):
            result = client.fetch_email_metadata(sync_cursor="expired-link", max_total=50)
        boot_mock.assert_called_once_with(50)
        assert result is bootstrap_result


# ── _bootstrap_email_metadata ───────────────────────────────────────


class TestResolveSpecialFolderIds:
    """Tests for _resolve_special_folder_ids — maps well-known folder names to Graph IDs."""

    def test_resolves_all_three_folders(self):
        client = _make_authenticated_client()

        def mock_graph(method, url, body=None):
            if "/mailFolders/sentitems?" in url:
                return {"id": "id-sent"}
            if "/mailFolders/deleteditems?" in url:
                return {"id": "id-trash"}
            if "/mailFolders/junkemail?" in url:
                return {"id": "id-spam"}
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._resolve_special_folder_ids()

        assert result == {"id-sent": "SENT", "id-trash": "TRASH", "id-spam": "SPAM"}

    def test_partial_failure_returns_resolved_only(self):
        client = _make_authenticated_client()

        def mock_graph(method, url, body=None):
            if "/mailFolders/sentitems?" in url:
                raise EmailExternalAPIError("not found")
            if "/mailFolders/deleteditems?" in url:
                return {"id": "id-trash"}
            if "/mailFolders/junkemail?" in url:
                return {"id": "id-spam"}
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._resolve_special_folder_ids()

        assert "SENT" not in result.values()
        assert result == {"id-trash": "TRASH", "id-spam": "SPAM"}

    def test_all_fail_returns_empty(self):
        client = _make_authenticated_client()
        with patch.object(
            client, "_graph_request", side_effect=EmailExternalAPIError("down"),
        ):
            result = client._resolve_special_folder_ids()
        assert result == {}


class TestFetchRecentMessages:
    """Tests for _fetch_recent_messages — GET /me/messages across all folders."""

    _FOLDER_MAP = {"id-sent": "SENT", "id-trash": "TRASH", "id-spam": "SPAM"}

    def test_classifies_by_parent_folder(self):
        client = _make_authenticated_client()
        messages = [
            _make_graph_message(msg_id="m-inbox", parent_folder_id="id-inbox"),
            _make_graph_message(msg_id="m-sent", parent_folder_id="id-sent"),
            _make_graph_message(msg_id="m-trash", parent_folder_id="id-trash"),
            _make_graph_message(msg_id="m-spam", parent_folder_id="id-spam"),
            _make_graph_message(msg_id="m-custom", parent_folder_id="id-custom"),
        ]
        with patch.object(client, "_graph_request", return_value={"value": messages}):
            result = client._fetch_recent_messages(500, self._FOLDER_MAP)

        by_id = {m.provider_message_id: m for m in result}
        assert by_id["m-inbox"].box == "ALL_MAIL"
        assert by_id["m-sent"].box == "SENT"
        assert by_id["m-trash"].box == "TRASH"
        assert by_id["m-spam"].box == "SPAM"
        assert by_id["m-custom"].box == "ALL_MAIL"

    def test_respects_max_total(self):
        client = _make_authenticated_client()
        messages = [
            _make_graph_message(msg_id=f"m{i}", parent_folder_id="id-inbox")
            for i in range(10)
        ]
        with patch.object(client, "_graph_request", return_value={"value": messages}):
            result = client._fetch_recent_messages(3, self._FOLDER_MAP)
        assert len(result) == 3

    def test_follows_pagination(self):
        client = _make_authenticated_client()
        page1 = {
            "value": [_make_graph_message(msg_id="m1", parent_folder_id="id-inbox")],
            "@odata.nextLink": "https://next-page",
        }
        page2 = {
            "value": [_make_graph_message(msg_id="m2", parent_folder_id="id-inbox")],
        }
        with patch.object(client, "_graph_request", side_effect=[page1, page2]):
            result = client._fetch_recent_messages(500, self._FOLDER_MAP)
        assert len(result) == 2

    def test_missing_parent_folder_defaults_to_all_mail(self):
        client = _make_authenticated_client()
        messages = [_make_graph_message(msg_id="m1")]  # no parentFolderId
        with patch.object(client, "_graph_request", return_value={"value": messages}):
            result = client._fetch_recent_messages(500, self._FOLDER_MAP)
        assert result[0].box == "ALL_MAIL"


class TestBootstrapEmailMetadata:
    """Integration tests for _bootstrap_email_metadata — the full Path 1 flow."""

    _SENT_ID = "folder-id-sent"
    _TRASH_ID = "folder-id-trash"
    _SPAM_ID = "folder-id-spam"

    def _make_bootstrap_mock(self, messages, *, fail_folders=None):
        """Return a side_effect for _graph_request that handles all bootstrap phases."""
        folder_ids = {
            "sentitems": self._SENT_ID,
            "deleteditems": self._TRASH_ID,
            "junkemail": self._SPAM_ID,
        }
        fail_folders = fail_folders or set()

        def mock_graph(method, url, body=None):
            # Phase 1: resolve special folder IDs
            for name, fid in folder_ids.items():
                if f"/mailFolders/{name}?" in url and "$select=id" in url:
                    if name in fail_folders:
                        raise EmailExternalAPIError(f"{name} not found")
                    return {"id": fid}

            # Phase 2: GET /me/messages (bootstrap data)
            if "/me/messages?" in url and "/mailFolders/" not in url:
                return {"value": messages}

            # Phase 3: per-folder delta cursor initialization
            for folder in _DELTA_FOLDERS:
                if f"/mailFolders/{folder}/messages/delta" in url:
                    if folder in fail_folders:
                        raise EmailExternalAPIError(f"delta {folder} failed")
                    return {
                        "value": [],
                        "@odata.deltaLink": f"https://delta-{folder}",
                    }

            raise AssertionError(f"Unexpected URL: {url}")

        return mock_graph

    def test_messages_classified_by_folder(self):
        client = _make_authenticated_client()
        messages = [
            _make_graph_message(msg_id="inbox-msg", parent_folder_id="folder-inbox"),
            _make_graph_message(msg_id="sent-msg", parent_folder_id=self._SENT_ID),
            _make_graph_message(msg_id="trash-msg", parent_folder_id=self._TRASH_ID),
            _make_graph_message(msg_id="spam-msg", parent_folder_id=self._SPAM_ID),
            _make_graph_message(msg_id="custom-msg", parent_folder_id="folder-custom"),
        ]
        mock = self._make_bootstrap_mock(messages)
        with patch.object(client, "_graph_request", side_effect=mock):
            result = client._bootstrap_email_metadata(max_total=500)

        by_id = {u.provider_message_id: u for u in result.upserts}
        assert by_id["inbox-msg"].box == "ALL_MAIL"
        assert by_id["sent-msg"].box == "SENT"
        assert by_id["trash-msg"].box == "TRASH"
        assert by_id["spam-msg"].box == "SPAM"
        assert by_id["custom-msg"].box == "ALL_MAIL"

    def test_max_total_limit(self):
        client = _make_authenticated_client()
        messages = [
            _make_graph_message(msg_id=f"msg-{i}", parent_folder_id="folder-inbox")
            for i in range(10)
        ]
        mock = self._make_bootstrap_mock(messages)
        with patch.object(client, "_graph_request", side_effect=mock):
            result = client._bootstrap_email_metadata(max_total=3)

        assert len(result.upserts) == 3

    def test_delta_cursors_initialized(self):
        client = _make_authenticated_client()
        messages = [_make_graph_message(parent_folder_id="folder-inbox")]
        mock = self._make_bootstrap_mock(messages)
        with patch.object(client, "_graph_request", side_effect=mock):
            result = client._bootstrap_email_metadata(max_total=500)

        cursor = json.loads(result.new_cursor)
        assert cursor["v"] == 1
        assert len(cursor["folders"]) == len(_DELTA_FOLDERS)

    def test_folder_resolution_failure_defaults_to_all_mail(self):
        """If sentitems ID can't be resolved, those messages default to ALL_MAIL."""
        client = _make_authenticated_client()
        messages = [
            _make_graph_message(msg_id="sent-msg", parent_folder_id=self._SENT_ID),
        ]
        mock = self._make_bootstrap_mock(messages, fail_folders={"sentitems"})
        with patch.object(client, "_graph_request", side_effect=mock):
            result = client._bootstrap_email_metadata(max_total=500)

        by_id = {u.provider_message_id: u for u in result.upserts}
        assert by_id["sent-msg"].box == "ALL_MAIL"

    def test_delta_init_failure_still_returns_messages(self):
        """If delta init fails for a folder, messages are still returned."""
        client = _make_authenticated_client()
        messages = [_make_graph_message(parent_folder_id="folder-inbox")]
        mock = self._make_bootstrap_mock(messages, fail_folders={"inbox"})
        with patch.object(client, "_graph_request", side_effect=mock):
            result = client._bootstrap_email_metadata(max_total=500)

        assert len(result.upserts) == 1
        cursor = json.loads(result.new_cursor)
        assert "inbox" not in cursor["folders"]

    def test_api_completely_down_raises_error(self):
        """If the Graph API is completely unreachable, the error propagates."""
        client = _make_authenticated_client()
        with patch.object(
            client, "_graph_request", side_effect=EmailExternalAPIError("all down"),
        ):
            with pytest.raises(EmailExternalAPIError):
                client._bootstrap_email_metadata(max_total=500)


# ── _incremental_email_metadata ─────────────────────────────────────


class TestIncrementalEmailMetadata:
    def test_new_messages_become_upserts(self):
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url:
                return {
                    "value": [_make_graph_message(msg_id="new1")],
                    "@odata.deltaLink": "https://new-delta-inbox",
                }
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        assert any(u.provider_message_id == "new1" for u in result.upserts)
        assert result.deletes == []
        new_cursors = json.loads(result.new_cursor)
        assert new_cursors["folders"]["inbox"] == "https://new-delta-inbox"

    def test_removed_messages_become_deletes(self):
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url:
                return {
                    "value": [{"id": "del1", "@removed": {"reason": "deleted"}}],
                    "@odata.deltaLink": "https://new-delta-inbox",
                }
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        assert result.deletes == ["del1"]

    def test_mixed_upserts_and_deletes(self):
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url:
                return {
                    "value": [
                        _make_graph_message(msg_id="new1"),
                        {"id": "del1", "@removed": {"reason": "deleted"}},
                    ],
                    "@odata.deltaLink": "https://new-delta-inbox",
                }
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        assert len(result.upserts) == 1
        assert result.deletes == ["del1"]

    def test_pagination(self):
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()
        next_url = "https://next-page"

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url and url != next_url:
                return {
                    "value": [_make_graph_message(msg_id="m1")],
                    "@odata.nextLink": next_url,
                }
            if url == next_url:
                return {
                    "value": [_make_graph_message(msg_id="m2")],
                    "@odata.deltaLink": "https://final-delta-inbox",
                }
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        inbox_msgs = [u for u in result.upserts if u.provider_message_id in ("m1", "m2")]
        assert len(inbox_msgs) == 2

    def test_empty_delta(self):
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        assert result.upserts == []
        assert result.deletes == []

    def test_legacy_cursor_raises_for_fallback(self):
        """A legacy (non-JSON) cursor triggers EmailExternalAPIError for fallback to bootstrap."""
        client = _make_authenticated_client()
        with pytest.raises(EmailExternalAPIError, match="legacy"):
            client._incremental_email_metadata("https://old-style-delta-link")

    def test_partial_folder_failure_keeps_previous_cursors(self):
        """If one folder fails, its previous cursor is preserved in the new cursor."""
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url:
                raise EmailExternalAPIError("inbox expired")
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        new_cursors = json.loads(result.new_cursor)
        # inbox keeps its old cursor
        assert new_cursors["folders"]["inbox"] == "https://delta-inbox"
        # other folders got updated
        assert new_cursors["folders"]["sentitems"] == "https://new-delta-sentitems"

    def test_all_folders_fail_raises_error(self):
        """If ALL folders fail, raise to trigger bootstrap fallback."""
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        with patch.object(
            client, "_graph_request", side_effect=EmailExternalAPIError("all down"),
        ):
            with pytest.raises(EmailExternalAPIError, match="all folder"):
                client._incremental_email_metadata(cursor)

    def test_box_mapping_from_folder_name(self):
        """Messages from deleteditems→TRASH, junkemail→SPAM, sentitems→SENT, others→ALL_MAIL."""
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            for folder in _DELTA_FOLDERS:
                if f"delta-{folder}" in url:
                    return {
                        "value": [_make_graph_message(msg_id=f"msg-{folder}")],
                        "@odata.deltaLink": f"https://new-delta-{folder}",
                    }
            return {"value": [], "@odata.deltaLink": url}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        by_id = {u.provider_message_id: u for u in result.upserts}
        assert by_id["msg-deleteditems"].box == "TRASH"
        assert by_id["msg-junkemail"].box == "SPAM"
        assert by_id["msg-inbox"].box == "ALL_MAIL"
        assert by_id["msg-sentitems"].box == "SENT"
        assert by_id["msg-drafts"].box == "ALL_MAIL"
        assert by_id["msg-archive"].box == "ALL_MAIL"

    def test_partial_delta_emits_label_update(self):
        """Delta returning a partial message (no 'from') populates label_updates, not upserts."""
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url:
                return {
                    "value": [{"id": "partial1", "isRead": True}],
                    "@odata.deltaLink": "https://new-delta-inbox",
                }
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        assert result.upserts == []
        assert len(result.label_updates) == 1
        assert result.label_updates[0].provider_message_id == "partial1"
        assert result.label_updates[0].is_read is True
        assert result.label_updates[0].box == "ALL_MAIL"

    def test_mixed_full_and_partial_messages(self):
        """Delta with both full and partial messages routes them correctly."""
        client = _make_authenticated_client()
        cursor = _make_folder_cursor()

        def mock_graph(method, url, body=None):
            if "delta-inbox" in url:
                return {
                    "value": [
                        _make_graph_message(msg_id="full1"),
                        {"id": "partial1", "isRead": False},
                    ],
                    "@odata.deltaLink": "https://new-delta-inbox",
                }
            return {"value": [], "@odata.deltaLink": url.replace("delta-", "new-delta-")}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._incremental_email_metadata(cursor)

        assert len(result.upserts) == 1
        assert result.upserts[0].provider_message_id == "full1"
        assert len(result.label_updates) == 1
        assert result.label_updates[0].provider_message_id == "partial1"
        assert result.label_updates[0].is_read is False


# ── send_email ───────────────────────────────────────────────────


class TestSendEmail:
    def _draft_response(self, draft_id="draft1"):
        return {
            "id": draft_id,
            "conversationId": "conv1",
            "from": {"emailAddress": {"address": "me@outlook.com", "name": "Me"}},
            "subject": "Subject",
            "receivedDateTime": "2024-06-01T12:00:00Z",
            "isRead": True,
        }

    def test_draft_then_send_two_calls(self):
        """send_email creates a draft then sends it (2 graph calls)."""
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request", side_effect=[
            self._draft_response(), {},
        ]) as mock_graph:
            result = client.send_email("Subject", "Body", ["a@b.com"])

        assert mock_graph.call_count == 2
        # First call: create draft
        first_args, first_kwargs = mock_graph.call_args_list[0]
        assert first_args[0] == "POST"
        assert "/me/messages" in first_args[1]
        assert "/send" not in first_args[1]
        draft_body = first_kwargs.get("body", first_args[2] if len(first_args) > 2 else None)
        assert draft_body["subject"] == "Subject"
        assert draft_body["body"]["content"] == "Body"
        # Second call: send
        second_args, _ = mock_graph.call_args_list[1]
        assert second_args[0] == "POST"
        assert "/me/messages/draft1/send" in second_args[1]

    def test_returns_email_metadata(self):
        """send_email returns EmailMetadata parsed from the draft response."""
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request", side_effect=[
            self._draft_response(), {},
        ]):
            result = client.send_email("Subject", "Body", ["a@b.com"])

        assert result.provider_message_id == "draft1"
        assert result.thread_id == "conv1"
        assert result.from_email == "me@outlook.com"
        assert result.subject == "Subject"
        assert result.box == "SENT"

    def test_multiple_recipients_payload(self):
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request", side_effect=[
            self._draft_response(), {},
        ]) as mock_graph:
            client.send_email("S", "B", ["a@b.com", "c@d.com", "e@f.com"])
            first_args, first_kwargs = mock_graph.call_args_list[0]
            payload = first_kwargs.get("body", first_args[2] if len(first_args) > 2 else None)
            addrs = [r["emailAddress"]["address"] for r in payload["toRecipients"]]
            assert addrs == ["a@b.com", "c@d.com", "e@f.com"]

    def test_supplements_sender_from_profile_when_draft_has_no_from(self):
        """Draft response without 'from' — sender fields supplemented after send."""
        client = _make_authenticated_client()
        draft_no_from = {
            "id": "draft1",
            "conversationId": "conv1",
            "subject": "Subject",
            "receivedDateTime": "2024-06-01T12:00:00Z",
            "isRead": True,
        }
        profile_response = {
            "displayName": "Test User",
            "mail": "me@outlook.com",
        }

        def mock_graph(method, url, body=None):
            if method == "POST" and "/me/messages" in url and "/send" not in url:
                return draft_no_from
            if method == "POST" and "/send" in url:
                return {}
            if method == "GET" and "/me?" in url and "mailFolders" not in url:
                return profile_response
            raise AssertionError(f"Unexpected call: {method} {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.send_email("Subject", "Body", ["a@b.com"])
        assert result.from_email == "me@outlook.com"
        assert result.from_name == "Test User"

    def test_supplements_sender_from_sentitems_fallback(self):
        """When /me and JWT fail, reads sender from a recently sent message."""
        client = _make_authenticated_client()
        draft_no_from = {
            "id": "draft1",
            "conversationId": "conv1",
            "subject": "Subject",
            "receivedDateTime": "2024-06-01T12:00:00Z",
            "isRead": True,
        }
        sentitems_response = {
            "value": [{
                "from": {"emailAddress": {"address": "me@outlook.com", "name": "Sent User"}},
            }],
        }

        call_index = 0

        def mock_graph(method, url, body=None):
            nonlocal call_index
            call_index += 1
            if method == "POST" and "/me/messages" in url and "/send" not in url:
                return draft_no_from
            if method == "POST" and "/send" in url:
                return {}
            if method == "GET" and "/me?" in url and "mailFolders" not in url:
                raise EmailExternalAPIError("no User.Read scope")
            if method == "GET" and "sentitems/messages" in url:
                return sentitems_response
            raise AssertionError(f"Unexpected call: {method} {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.send_email("Subject", "Body", ["a@b.com"])
        assert result.from_email == "me@outlook.com"
        assert result.from_name == "Sent User"

    def test_uses_draft_from_when_available(self):
        """Draft with 'from' — no profile call made (only 2 graph calls)."""
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request", side_effect=[
            self._draft_response(), {},
        ]) as mock_graph:
            result = client.send_email("Subject", "Body", ["a@b.com"])
        assert mock_graph.call_count == 2
        assert result.from_email == "me@outlook.com"
        assert result.from_name == "Me"


class TestFetchSenderProfile:
    def test_caches_result(self):
        """_fetch_sender_profile calls /me only once, caches for subsequent calls."""
        client = _make_authenticated_client()
        profile_response = {
            "displayName": "Test User",
            "mail": "me@outlook.com",
        }
        with patch.object(client, "_graph_request", return_value=profile_response) as mock_graph:
            first = client._fetch_sender_profile()
            second = client._fetch_sender_profile()
        assert first == ("me@outlook.com", "Test User")
        assert second == ("me@outlook.com", "Test User")
        mock_graph.assert_called_once()

    def test_falls_back_to_jwt_when_graph_fails(self):
        """When /me fails (e.g. missing User.Read scope), falls back to JWT claims."""
        import base64 as b64
        claims = json.dumps({
            "preferred_username": "user@outlook.com",
            "name": "JWT User",
        }).encode()
        payload_b64 = b64.urlsafe_b64encode(claims).rstrip(b"=").decode()
        fake_token = f"header.{payload_b64}.signature"

        client = OutlookClient(account_label="mb__outlook")
        client._access_token = fake_token
        with patch.object(client, "_graph_request", side_effect=RuntimeError("403")):
            result = client._fetch_sender_profile()
        assert result == ("user@outlook.com", "JWT User")

    def test_falls_back_to_sentitems_when_jwt_also_fails(self):
        """When /me and JWT fail, reads sender from sentitems."""
        client = OutlookClient(account_label="mb__outlook")
        client._access_token = "EwB-opaque-token"  # not a JWT

        sentitems_response = {
            "value": [{
                "from": {"emailAddress": {"address": "me@outlook.com", "name": "Sent User"}},
            }],
        }

        def mock_graph(method, url, body=None):
            if "mailFolders" not in url and "/me?" in url:
                raise RuntimeError("no User.Read scope")
            if "sentitems/messages" in url:
                return sentitems_response
            raise AssertionError(f"Unexpected: {method} {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._fetch_sender_profile()
        assert result == ("me@outlook.com", "Sent User")

    def test_returns_empty_when_all_paths_fail(self):
        """When /me, JWT, and sentitems all fail, returns empty strings."""
        client = OutlookClient(account_label="mb__outlook")
        client._access_token = "opaque"
        with patch.object(client, "_graph_request", side_effect=RuntimeError("boom")):
            result = client._fetch_sender_profile()
        assert result == ("", "")


# ── _token_request ───────────────────────────────────────────────


class TestTokenRequest:
    def _mock_response(self, body_bytes: bytes, status: int = 200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body_bytes
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_happy_path(self):
        client = _make_authenticated_client()
        resp = self._mock_response(b'{"access_token": "tok123"}')
        with patch("urllib.request.urlopen", return_value=resp):
            result = client._token_request("https://login.example.com/token", {"grant_type": "authorization_code"})
        assert result["access_token"] == "tok123"

    def test_http_error_raises_external_api(self):
        client = _make_authenticated_client()
        exc = urllib.error.HTTPError(
            "https://login.example.com/token", 400, "Bad Request",
            {}, MagicMock(read=lambda: b'{"error": "invalid_grant", "error_description": "bad"}'),
        )
        exc.read = lambda: b'{"error": "invalid_grant", "error_description": "bad"}'
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(EmailExternalAPIError, match="token endpoint"):
                client._token_request("https://login.example.com/token", {})

    def test_url_error_raises_external_api(self):
        client = _make_authenticated_client()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("DNS fail")):
            with pytest.raises(EmailExternalAPIError, match="reach token endpoint"):
                client._token_request("https://login.example.com/token", {})

    def test_malformed_json_raises_external_api(self):
        client = _make_authenticated_client()
        resp = self._mock_response(b"not-json")
        with patch("urllib.request.urlopen", return_value=resp):
            with pytest.raises(EmailExternalAPIError, match="invalid JSON"):
                client._token_request("https://login.example.com/token", {})

    def test_error_in_response_raises_external_api(self):
        client = _make_authenticated_client()
        resp = self._mock_response(b'{"error": "invalid_grant", "error_description": "token expired"}')
        with patch("urllib.request.urlopen", return_value=resp):
            with pytest.raises(EmailExternalAPIError, match="invalid_grant"):
                client._token_request("https://login.example.com/token", {})


# ── _graph_request ───────────────────────────────────────────────


class TestGraphRequest:
    def _mock_response(self, body_bytes: bytes, status: int = 200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = body_bytes
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_happy_path(self):
        client = _make_authenticated_client()
        resp = self._mock_response(b'{"value": []}')
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            result = client._graph_request("GET", "https://graph.microsoft.com/v1.0/me")
        assert result == {"value": []}
        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer token"

    def test_204_returns_empty_dict(self):
        client = _make_authenticated_client()
        resp = self._mock_response(b"", status=204)
        with patch("urllib.request.urlopen", return_value=resp):
            result = client._graph_request("POST", "https://graph.microsoft.com/v1.0/me/sendMail")
        assert result == {}

    def test_http_error_raises_external_api(self):
        client = _make_authenticated_client()
        exc = urllib.error.HTTPError(
            "https://graph.microsoft.com", 403, "Forbidden",
            {}, MagicMock(read=lambda: b'{"error": {"code": "Forbidden", "message": "no access"}}'),
        )
        exc.read = lambda: b'{"error": {"code": "Forbidden", "message": "no access"}}'
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(EmailExternalAPIError, match="Graph API call"):
                client._graph_request("GET", "https://graph.microsoft.com/v1.0/me")

    def test_post_sends_json_body(self):
        client = _make_authenticated_client()
        resp = self._mock_response(b'{}')
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            client._graph_request("POST", "https://graph.microsoft.com/v1.0/me/sendMail", body={"key": "val"})
        req = mock_open.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"
        assert json.loads(req.data) == {"key": "val"}


# ── _fetch_folder_delta ──────────────────────────────────────────


class TestFetchFolderDelta:
    def test_single_page_returns_delta_link(self):
        client = _make_authenticated_client()
        msg = {
            "id": "msg1",
            "subject": "Hello",
            "from": {"emailAddress": {"address": "a@b.com", "name": "A"}},
            "receivedDateTime": "2025-01-01T10:00:00Z",
            "isRead": False,
            "conversationId": "conv1",
        }
        response = {"value": [msg], "@odata.deltaLink": "https://delta-link"}
        with patch.object(client, "_graph_request", return_value=response):
            upserts = []
            deletes = []
            delta = client._fetch_folder_delta("inbox", "https://start-url", upserts, deletes)
        assert delta == "https://delta-link"
        assert len(upserts) == 1
        assert upserts[0].provider_message_id == "msg1"
        assert deletes == []

    def test_pagination(self):
        client = _make_authenticated_client()
        msg1 = {
            "id": "msg1", "subject": "S1",
            "from": {"emailAddress": {"address": "a@b.com", "name": "A"}},
            "receivedDateTime": "2025-01-01T10:00:00Z", "isRead": False, "conversationId": "c1",
        }
        msg2 = {
            "id": "msg2", "subject": "S2",
            "from": {"emailAddress": {"address": "b@c.com", "name": "B"}},
            "receivedDateTime": "2025-01-02T10:00:00Z", "isRead": True, "conversationId": "c2",
        }
        page1 = {"value": [msg1], "@odata.nextLink": "https://next"}
        page2 = {"value": [msg2], "@odata.deltaLink": "https://delta-final"}
        with patch.object(client, "_graph_request", side_effect=[page1, page2]):
            upserts = []
            deletes = []
            delta = client._fetch_folder_delta("inbox", "https://start", upserts, deletes)
        assert delta == "https://delta-final"
        assert len(upserts) == 2

    def test_max_collect_stops_collecting(self):
        client = _make_authenticated_client()
        msgs = [
            {
                "id": f"msg{i}", "subject": f"S{i}",
                "from": {"emailAddress": {"address": f"{i}@b.com", "name": f"U{i}"}},
                "receivedDateTime": "2025-01-01T10:00:00Z", "isRead": False, "conversationId": f"c{i}",
            }
            for i in range(3)
        ]
        page1 = {"value": msgs[:2], "@odata.nextLink": "https://next"}
        page2 = {"value": [msgs[2]], "@odata.deltaLink": "https://delta"}
        with patch.object(client, "_graph_request", side_effect=[page1, page2]):
            upserts = []
            deletes = []
            delta = client._fetch_folder_delta("inbox", "https://start", upserts, deletes, max_collect=1)
        assert delta == "https://delta"
        assert len(upserts) == 1

    def test_removed_message_added_to_deletes(self):
        client = _make_authenticated_client()
        msg = {"id": "removed1", "@removed": {"reason": "deleted"}}
        response = {"value": [msg], "@odata.deltaLink": "https://delta"}
        with patch.object(client, "_graph_request", return_value=response):
            upserts = []
            deletes = []
            client._fetch_folder_delta("inbox", "https://start", upserts, deletes)
        assert upserts == []
        assert deletes == ["removed1"]

    def test_partial_message_becomes_label_update(self):
        """Message without 'from' key is appended to label_updates, not upserts."""
        client = _make_authenticated_client()
        partial_msg = {"id": "partial1", "isRead": True}
        response = {"value": [partial_msg], "@odata.deltaLink": "https://delta"}
        with patch.object(client, "_graph_request", return_value=response):
            upserts: list[EmailMetadata] = []
            deletes: list[str] = []
            label_updates: list[LabelUpdate] = []
            client._fetch_folder_delta("inbox", "https://start", upserts, deletes, label_updates=label_updates)
        assert upserts == []
        assert len(label_updates) == 1
        assert label_updates[0].provider_message_id == "partial1"
        assert label_updates[0].is_read is True
        assert label_updates[0].box == "ALL_MAIL"

    def test_full_message_remains_upsert_when_label_updates_provided(self):
        """Message with 'from' still goes to upserts even when label_updates list is provided."""
        client = _make_authenticated_client()
        full_msg = _make_graph_message(msg_id="full1")
        response = {"value": [full_msg], "@odata.deltaLink": "https://delta"}
        with patch.object(client, "_graph_request", return_value=response):
            upserts: list[EmailMetadata] = []
            deletes: list[str] = []
            label_updates: list[LabelUpdate] = []
            client._fetch_folder_delta("inbox", "https://start", upserts, deletes, label_updates=label_updates)
        assert len(upserts) == 1
        assert upserts[0].provider_message_id == "full1"
        assert label_updates == []

    def test_label_updates_none_falls_through_to_upsert(self):
        """When label_updates is None (Path 1 default), partial messages are parsed as upserts."""
        client = _make_authenticated_client()
        partial_msg = {"id": "partial1", "isRead": False}
        response = {"value": [partial_msg], "@odata.deltaLink": "https://delta"}
        with patch.object(client, "_graph_request", return_value=response):
            upserts: list[EmailMetadata] = []
            deletes: list[str] = []
            client._fetch_folder_delta("inbox", "https://start", upserts, deletes)
        # Without label_updates list, partial messages go through normal upsert parsing.
        # This is fine because Path 1 (bootstrap) always receives full messages.
        assert len(upserts) == 1
        assert upserts[0].provider_message_id == "partial1"
        assert upserts[0].from_email == ""


# ── verify_message_existence ───────────────────────────────────────


class TestVerifyMessageExistence:
    def test_not_authenticated_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        with pytest.raises(EmailNotAuthenticatedError):
            client.verify_message_existence(["m1"])

    def test_empty_list_returns_empty(self):
        client = _make_authenticated_client()
        assert client.verify_message_existence([]) == []

    def test_all_exist(self):
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request", return_value={"id": "m1"}):
            result = client.verify_message_existence(["m1"])
        assert result == ["m1"]

    def test_some_missing(self):
        client = _make_authenticated_client()
        responses = [
            {"id": "m1"},
            EmailExternalAPIError("404"),
            {"id": "m3"},
        ]
        side_effects = []
        for r in responses:
            if isinstance(r, Exception):
                side_effects.append(r)
            else:
                side_effects.append(r)

        def mock_graph(method, url):
            resp = side_effects.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.verify_message_existence(["m1", "m2", "m3"])
        assert result == ["m1", "m3"]

    def test_all_missing(self):
        client = _make_authenticated_client()
        with patch.object(
            client, "_graph_request", side_effect=EmailExternalAPIError("404"),
        ):
            result = client.verify_message_existence(["m1", "m2"])
        assert result == []


# ── is_full_sync flag ──────────────────────────────────────────────


class TestBootstrapIsFullSync:
    def test_bootstrap_sets_is_full_sync_true(self):
        client = _make_authenticated_client()
        messages = [_make_graph_message(parent_folder_id="folder-inbox")]

        _SENT_ID = "folder-id-sent"
        _TRASH_ID = "folder-id-trash"
        _SPAM_ID = "folder-id-spam"
        folder_ids = {
            "sentitems": _SENT_ID,
            "deleteditems": _TRASH_ID,
            "junkemail": _SPAM_ID,
        }

        def mock_graph(method, url, body=None):
            for name, fid in folder_ids.items():
                if f"/mailFolders/{name}?" in url and "$select=id" in url:
                    return {"id": fid}
            if "/me/messages?" in url and "/mailFolders/" not in url:
                return {"value": messages}
            for folder in _DELTA_FOLDERS:
                if f"/mailFolders/{folder}/messages/delta" in url:
                    return {"value": [], "@odata.deltaLink": f"https://delta-{folder}"}
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._bootstrap_email_metadata(max_total=500)
        assert result.is_full_sync is True


# ── authenticate (interactive OAuth + PKCE) ─────────────────────


_VALID_OUTLOOK_APP_CREDS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "tenant": "test-tenant",
    "redirect_uri": "http://localhost:8400/callback",
    "scopes": OUTLOOK_SCOPES,
}


def _extract_callback_result(mock_server_cls):
    """Reach into the closure of _OAuthHandler.do_GET to get callback_result."""
    handler_cls = mock_server_cls.call_args[0][1]
    freevars = handler_cls.do_GET.__code__.co_freevars
    closure = handler_cls.do_GET.__closure__
    idx = freevars.index("callback_result")
    return closure[idx].cell_contents


class TestAuthenticate:

    def _make_creds(self, **overrides):
        creds = dict(_VALID_OUTLOOK_APP_CREDS)
        creds.update(overrides)
        return creds

    def test_happy_path_returns_wrapped_tokens(self):
        client = OutlookClient(account_label="mb__outlook")
        creds = self._make_creds()

        with (
            patch("http.server.ThreadingHTTPServer") as mock_server_cls,
            patch("threading.Thread") as mock_thread_cls,
            patch("threading.Event") as mock_event_cls,
            patch("webbrowser.open", return_value=True),
            patch("secrets.token_urlsafe", side_effect=["x" * 128, "state-value"]),
            patch.object(client, "_token_request", return_value={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
            }),
        ):
            mock_event = MagicMock()
            mock_event_cls.return_value = mock_event

            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            def _wait_and_fill(timeout=None):
                cb = _extract_callback_result(mock_server_cls)
                cb["code"] = "auth-code-123"
                cb["state"] = "state-value"
                return True

            mock_event.wait.side_effect = _wait_and_fill

            result = client.authenticate(app_credentials=creds)

        assert result["access_token"].get_secret_value() == "at"
        assert client._access_token == "at"

    def test_missing_app_credentials_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        with pytest.raises(EmailMissingAppCredentialsError):
            client.authenticate(app_credentials=None)

    def test_invalid_redirect_uri_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        creds = self._make_creds(redirect_uri="https://example.com/cb")
        with pytest.raises(EmailProviderConfigError, match="redirect_uri"):
            client.authenticate(app_credentials=creds)

    def test_server_start_os_error_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        creds = self._make_creds()
        with (
            patch("http.server.ThreadingHTTPServer", side_effect=OSError("port in use")),
            patch("secrets.token_urlsafe", return_value="x" * 128),
        ):
            with pytest.raises(EmailExternalAPIError, match="failed to start"):
                client.authenticate(app_credentials=creds)

    def test_timeout_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        creds = self._make_creds()
        with (
            patch("http.server.ThreadingHTTPServer") as mock_server_cls,
            patch("threading.Thread") as mock_thread_cls,
            patch("threading.Event") as mock_event_cls,
            patch("webbrowser.open", return_value=True),
            patch("secrets.token_urlsafe", return_value="x" * 128),
        ):
            mock_event = MagicMock()
            mock_event.wait.return_value = False
            mock_event_cls.return_value = mock_event

            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            with pytest.raises(EmailExternalAPIError, match="timeout"):
                client.authenticate(app_credentials=creds)

    def test_missing_access_token_in_response_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        creds = self._make_creds()

        with (
            patch("http.server.ThreadingHTTPServer") as mock_server_cls,
            patch("threading.Thread") as mock_thread_cls,
            patch("threading.Event") as mock_event_cls,
            patch("webbrowser.open", return_value=True),
            patch("secrets.token_urlsafe", side_effect=["x" * 128, "state-value"]),
            patch.object(client, "_token_request", return_value={}),
        ):
            mock_event = MagicMock()
            mock_event_cls.return_value = mock_event

            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            def _wait_and_fill(timeout=None):
                cb = _extract_callback_result(mock_server_cls)
                cb["code"] = "auth-code-123"
                cb["state"] = "state-value"
                return True

            mock_event.wait.side_effect = _wait_and_fill

            with pytest.raises(EmailExternalAPIError, match="missing access_token"):
                client.authenticate(app_credentials=creds)


# ── update_read_status ────────────────────────────────────────────


class TestUpdateReadStatus:
    def test_not_authenticated_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        with pytest.raises(EmailNotAuthenticatedError):
            client.update_read_status(["m1"], True)

    def test_empty_returns_empty(self):
        client = _make_authenticated_client()
        assert client.update_read_status([], True) == []

    def test_mark_as_read_sends_patch_is_read_true(self):
        client = _make_authenticated_client()
        graph_calls = []

        def mock_graph(method, url, body=None):
            graph_calls.append((method, url, body))
            return {}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.update_read_status(["m1"], True)

        assert result == ["m1"]
        assert len(graph_calls) == 1
        method, url, body = graph_calls[0]
        assert method == "PATCH"
        assert "/me/messages/m1" in url
        assert body == {"isRead": True}

    def test_mark_as_unread_sends_patch_is_read_false(self):
        client = _make_authenticated_client()
        graph_calls = []

        def mock_graph(method, url, body=None):
            graph_calls.append((method, url, body))
            return {}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.update_read_status(["m1"], False)

        assert result == ["m1"]
        assert len(graph_calls) == 1
        method, url, body = graph_calls[0]
        assert method == "PATCH"
        assert body == {"isRead": False}

    def test_missing_message_skipped(self):
        client = _make_authenticated_client()

        def mock_graph(method, url, body=None):
            if "m2" in url:
                raise EmailExternalAPIError("404 Not Found")
            return {}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.update_read_status(["m1", "m2", "m3"], True)

        assert result == ["m1", "m3"]


# ── move_to_spam ─────────────────────────────────────────────────


class TestMoveToSpam:
    def test_not_authenticated_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        with pytest.raises(EmailNotAuthenticatedError):
            client.move_to_spam(["m1"])

    def test_empty_returns_empty(self):
        client = _make_authenticated_client()
        assert client.move_to_spam([]) == []

    def test_happy_path_posts_move_to_junkemail(self):
        client = _make_authenticated_client()
        graph_calls: list[tuple[str, str, dict | None]] = []

        def mock_graph(method, url, body=None):
            graph_calls.append((method, url, body))
            return {"id": "new_m1"}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.move_to_spam(["m1"])

        assert len(graph_calls) == 1
        method, url, body = graph_calls[0]
        assert method == "POST"
        assert f"{GRAPH_BASE_URL}/me/messages/m1/move" == url
        assert body == {"destinationId": "junkemail"}
        assert result == [SpamMoveResult(old_id="m1", new_id="new_m1")]


# ── restore_from_spam ────────────────────────────────────────────


class TestRestoreFromSpam:
    def test_not_authenticated_raises(self):
        client = OutlookClient(account_label="mb__outlook")
        with pytest.raises(EmailNotAuthenticatedError):
            client.restore_from_spam(["m1"])

    def test_empty_returns_empty(self):
        client = _make_authenticated_client()
        assert client.restore_from_spam([]) == []

    def test_happy_path_posts_move_to_inbox(self):
        client = _make_authenticated_client()
        graph_calls: list[tuple[str, str, dict | None]] = []

        def mock_graph(method, url, body=None):
            graph_calls.append((method, url, body))
            return {"id": "new_m1"}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client.restore_from_spam(["m1"])

        assert len(graph_calls) == 1
        method, url, body = graph_calls[0]
        assert method == "POST"
        assert f"{GRAPH_BASE_URL}/me/messages/m1/move" == url
        assert body == {"destinationId": "inbox"}
        assert result == [SpamMoveResult(old_id="m1", new_id="new_m1")]
