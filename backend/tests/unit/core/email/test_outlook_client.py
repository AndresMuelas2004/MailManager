"""Unit tests for OutlookClient — provider-specific logic, guard clauses, and refresh path.

Shared helper tests (parse_expiry, unwrap/wrap) live in ``test_helpers.py``.
"""

from __future__ import annotations

import base64
import io
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from core.email.errors import (
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from core.email.outlook_client import GRAPH_BASE_URL, OUTLOOK_SCOPES, OutlookClient


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
        # Clamped to 0 seconds, so expiry should be ~now
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
        creds = {"tenant": "t"}  # missing client_id and client_secret
        tokens = {
            "access_token": "at",
            "refresh_token": "rt",
            "expiry": "2020-01-01T00:00:00",
        }
        with pytest.raises(EmailMissingAppCredentialsError, match="Missing required"):
            client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

    def test_fetch_unread_emails_not_authenticated_raises_error(self, client: OutlookClient):
        assert client._access_token is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.fetch_unread_emails()

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
        mock_response = {"refresh_token": "new_rt"}  # no access_token
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
            # no refresh_token in response
        }
        with patch.object(client, "_token_request", return_value=mock_response):
            result = client.authenticate_silent(app_credentials=creds, user_tokens=tokens)

        assert result["refresh_token"].get_secret_value() == "old_rt"


# ── _graph_raw_request ──────────────────────────────────────────────


class TestGraphRawRequest:
    """Test the raw MIME download helper by mocking urllib.request.urlopen."""

    def test_returns_raw_bytes(self, client: OutlookClient):
        client._access_token = "token"
        fake_body = b"MIME-Version: 1.0\r\nSubject: hi\r\n\r\nbody"
        mock_response = MagicMock()
        mock_response.read.return_value = fake_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("core.email.outlook_client.urllib.request.urlopen", return_value=mock_response):
            result = client._graph_raw_request("https://graph.microsoft.com/v1.0/me/messages/abc/$value")

        assert result == fake_body

    def test_http_error_raises_external_api_error(self, client: OutlookClient):
        client._access_token = "token"
        exc = urllib.error.HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b'{"error":{"code":"ResourceNotFound","message":"msg"}}'),
        )

        with patch("core.email.outlook_client.urllib.request.urlopen", side_effect=exc):
            with pytest.raises(EmailExternalAPIError, match="Graph API call"):
                client._graph_raw_request("https://example.com")

    def test_url_error_raises_external_api_error(self, client: OutlookClient):
        client._access_token = "token"
        exc = urllib.error.URLError(reason="DNS failure")

        with patch("core.email.outlook_client.urllib.request.urlopen", side_effect=exc):
            with pytest.raises(EmailExternalAPIError, match="reach Graph API"):
                client._graph_raw_request("https://example.com")

    def test_generic_exception_raises_external_api_error(self, client: OutlookClient):
        client._access_token = "token"

        with patch("core.email.outlook_client.urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with pytest.raises(EmailExternalAPIError, match="RuntimeError"):
                client._graph_raw_request("https://example.com")


# ── fetch_unread_emails (with raw MIME) ─────────────────────────────


class TestFetchUnreadEmails:
    """Test the full fetch flow by mocking _graph_request and _graph_raw_request."""

    @staticmethod
    def _make_raw_message(msg_id: str = "msg-1") -> dict:
        return {
            "id": msg_id,
            "conversationId": "conv-1",
            "subject": "Hello",
            "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "bob@example.com"}}],
            "bodyPreview": "Preview text",
            "receivedDateTime": "2024-06-01T10:00:00Z",
            "isRead": False,
        }

    def test_populates_raw_rfc822_b64url(self, client: OutlookClient):
        client._access_token = "token"
        raw_msg = self._make_raw_message("msg-1")
        graph_response = {"value": [raw_msg]}
        mime_bytes = b"MIME-Version: 1.0\r\nSubject: Hello\r\n\r\nPreview text"

        with patch.object(client, "_graph_request", return_value=graph_response), \
             patch.object(client, "_graph_raw_request", return_value=mime_bytes) as mock_raw:
            emails = client.fetch_unread_emails()

        assert len(emails) == 1
        expected_b64 = base64.urlsafe_b64encode(mime_bytes).decode("utf-8")
        assert emails[0].raw_rfc822_b64url == expected_b64
        assert emails[0].message_id == "msg-1"
        assert emails[0].provider == "outlook"
        mock_raw.assert_called_once_with(f"{GRAPH_BASE_URL}/me/messages/msg-1/$value")

    def test_empty_inbox_returns_empty_list(self, client: OutlookClient):
        client._access_token = "token"
        graph_response = {"value": []}

        with patch.object(client, "_graph_request", return_value=graph_response) as mock_graph, \
             patch.object(client, "_graph_raw_request") as mock_raw:
            emails = client.fetch_unread_emails()

        assert emails == []
        mock_raw.assert_not_called()

    def test_raw_request_failure_propagates_error(self, client: OutlookClient):
        client._access_token = "token"
        raw_msg = self._make_raw_message("msg-fail")
        graph_response = {"value": [raw_msg]}

        with patch.object(client, "_graph_request", return_value=graph_response), \
             patch.object(client, "_graph_raw_request", side_effect=EmailExternalAPIError("boom")):
            with pytest.raises(EmailExternalAPIError, match="boom"):
                client.fetch_unread_emails()
