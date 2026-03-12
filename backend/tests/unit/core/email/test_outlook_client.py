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

from core.email.email_client import EmailMetadata, SyncResult
from core.email.errors import (
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
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
) -> dict:
    """Build a Graph message resource for testing."""
    return {
        "id": msg_id,
        "conversationId": conversation_id,
        "from": {"emailAddress": {"address": from_address, "name": from_name}},
        "subject": subject,
        "receivedDateTime": received,
        "isRead": is_read,
    }


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


class TestBootstrapEmailMetadata:
    def _folder_url(self, folder: str) -> str:
        return (
            f"{GRAPH_BASE_URL}/me/mailFolders/{folder}/messages/delta"
            f"?$select={_DELTA_SELECT_FIELDS}&$top={_DELTA_PAGE_SIZE}"
        )

    def _mock_graph_for_folders(self, folder_responses: dict[str, list[dict]]):
        """Return a side_effect function that responds based on the folder URL."""
        call_index: dict[str, int] = {}

        def mock_graph(method, url, body=None):
            for folder, pages in folder_responses.items():
                folder_url = self._folder_url(folder)
                if url == folder_url or url in [p.get("@odata.nextLink", "") for p in pages]:
                    idx = call_index.get(folder, 0)
                    call_index[folder] = idx + 1
                    return pages[idx]
            raise AssertionError(f"Unexpected URL: {url}")

        return mock_graph

    def test_single_page_all_folders(self):
        client = _make_authenticated_client()
        msg = _make_graph_message()

        def mock_graph(method, url, body=None):
            # Each folder returns one message and a deltaLink
            for folder in _DELTA_FOLDERS:
                if f"/mailFolders/{folder}/" in url:
                    return {
                        "value": [_make_graph_message(msg_id=f"msg-{folder}")],
                        "@odata.deltaLink": f"https://delta-{folder}",
                    }
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._bootstrap_email_metadata(max_total=500)

        assert len(result.upserts) == len(_DELTA_FOLDERS)
        cursor = json.loads(result.new_cursor)
        assert cursor["v"] == 1
        assert len(cursor["folders"]) == len(_DELTA_FOLDERS)

    def test_pagination_within_folder(self):
        client = _make_authenticated_client()
        next_url = "https://next-page-inbox"

        def mock_graph(method, url, body=None):
            if "/mailFolders/inbox/" in url and "next-page" not in url:
                return {
                    "value": [_make_graph_message(msg_id="m1")],
                    "@odata.nextLink": next_url,
                }
            if url == next_url:
                return {
                    "value": [_make_graph_message(msg_id="m2")],
                    "@odata.deltaLink": "https://delta-inbox-final",
                }
            # Other folders: empty
            return {"value": [], "@odata.deltaLink": f"https://delta-other"}

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._bootstrap_email_metadata(max_total=500)

        inbox_msgs = [u for u in result.upserts if u.provider_message_id in ("m1", "m2")]
        assert len(inbox_msgs) == 2

    def test_max_total_limit(self):
        client = _make_authenticated_client()

        def mock_graph(method, url, body=None):
            for folder in _DELTA_FOLDERS:
                if f"/mailFolders/{folder}/" in url:
                    return {
                        "value": [
                            _make_graph_message(msg_id=f"{folder}-m{i}")
                            for i in range(5)
                        ],
                        "@odata.deltaLink": f"https://delta-{folder}",
                    }
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._bootstrap_email_metadata(max_total=3)

        assert len(result.upserts) == 3

    def test_folder_failure_skips_and_continues(self):
        """If one folder fails, others should still be fetched."""
        client = _make_authenticated_client()

        def mock_graph(method, url, body=None):
            if "/mailFolders/inbox/" in url:
                raise EmailExternalAPIError("inbox failed")
            for folder in _DELTA_FOLDERS:
                if f"/mailFolders/{folder}/" in url:
                    return {
                        "value": [_make_graph_message(msg_id=f"msg-{folder}")],
                        "@odata.deltaLink": f"https://delta-{folder}",
                    }
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(client, "_graph_request", side_effect=mock_graph):
            result = client._bootstrap_email_metadata(max_total=500)

        assert len(result.upserts) == len(_DELTA_FOLDERS) - 1
        cursor = json.loads(result.new_cursor)
        assert "inbox" not in cursor["folders"]

    def test_api_error_propagates_only_if_within_folder(self):
        """Individual folder errors are caught; the method only raises if _graph_request
        raises outside a folder loop (which doesn't happen in current impl)."""
        client = _make_authenticated_client()
        # All folders fail → result has empty upserts and empty cursor folders
        with patch.object(
            client, "_graph_request", side_effect=EmailExternalAPIError("all down"),
        ):
            result = client._bootstrap_email_metadata(max_total=500)

        assert result.upserts == []
        cursor = json.loads(result.new_cursor)
        assert cursor["folders"] == {}


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


# ── _graph_raw_request ──────────────────────────────────────────────


class TestGraphRawRequest:
    def test_returns_raw_bytes(self):
        client = _make_authenticated_client()
        mock_response = MagicMock()
        mock_response.read.return_value = b"raw-data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = client._graph_raw_request("https://example.com/resource")
        assert result == b"raw-data"

    def test_http_error_raises_external_api_error(self):
        client = _make_authenticated_client()
        exc = urllib.error.HTTPError(
            url="https://example.com", code=403, msg="Forbidden",
            hdrs=None, fp=MagicMock(read=MagicMock(return_value=b"forbidden")),
        )

        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(EmailExternalAPIError, match="Outlook failed Graph API call"):
                client._graph_raw_request("https://example.com/resource")

    def test_url_error_raises_external_api_error(self):
        client = _make_authenticated_client()
        exc = urllib.error.URLError("DNS resolution failed")

        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(EmailExternalAPIError, match="Outlook failed to reach Graph API"):
                client._graph_raw_request("https://example.com/resource")

    def test_generic_exception_raises_external_api_error(self):
        client = _make_authenticated_client()

        with patch("urllib.request.urlopen", side_effect=OSError("connection reset")):
            with pytest.raises(EmailExternalAPIError, match="Outlook failed Graph API request"):
                client._graph_raw_request("https://example.com/resource")


# ── send_email ───────────────────────────────────────────────────


class TestSendEmail:
    def test_constructs_payload_and_calls_graph(self):
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request") as mock_graph:
            client.send_email("Subject", "Body", ["a@b.com"])
            mock_graph.assert_called_once()
            call_args, call_kwargs = mock_graph.call_args
            assert call_args[0] == "POST"
            assert "/me/sendMail" in call_args[1]
            payload = call_kwargs.get("body", call_args[2] if len(call_args) > 2 else None)
            assert payload["message"]["subject"] == "Subject"
            assert payload["message"]["body"]["content"] == "Body"
            assert len(payload["message"]["toRecipients"]) == 1
            assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == "a@b.com"

    def test_multiple_recipients_payload(self):
        client = _make_authenticated_client()
        with patch.object(client, "_graph_request") as mock_graph:
            client.send_email("S", "B", ["a@b.com", "c@d.com", "e@f.com"])
            call_args, call_kwargs = mock_graph.call_args
            payload = call_kwargs.get("body", call_args[2] if len(call_args) > 2 else None)
            addrs = [r["emailAddress"]["address"] for r in payload["message"]["toRecipients"]]
            assert addrs == ["a@b.com", "c@d.com", "e@f.com"]


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
