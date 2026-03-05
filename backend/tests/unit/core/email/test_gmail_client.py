"""Unit tests for GmailClient — build config, guard clauses, and metadata fetch.

Shared helper tests (parse_expiry, unwrap/wrap) live in ``test_helpers.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.email.errors import (
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
        fake_result = ([], "hist123")
        with patch.object(client, "_bootstrap_email_metadata", return_value=fake_result) as mock_bs:
            result = client.fetch_email_metadata(sync_cursor=None)
        mock_bs.assert_called_once_with(500)
        assert result == fake_result

    def test_valid_cursor_falls_back_to_bootstrap(self, client: GmailClient):
        """With a valid cursor, Camino 2 is not yet implemented, falls back to bootstrap."""
        client.service = MagicMock()
        fake_result = ([], "hist456")
        with patch.object(client, "_is_sync_cursor_valid", return_value=True), \
             patch.object(client, "_bootstrap_email_metadata", return_value=fake_result) as mock_bs:
            result = client.fetch_email_metadata(sync_cursor="old_cursor")
        mock_bs.assert_called_once_with(500)
        assert result == fake_result

    def test_invalid_cursor_falls_back_to_bootstrap(self, client: GmailClient):
        """With an invalid cursor, falls back to bootstrap."""
        client.service = MagicMock()
        fake_result = ([], "hist789")
        with patch.object(client, "_is_sync_cursor_valid", return_value=False), \
             patch.object(client, "_bootstrap_email_metadata", return_value=fake_result) as mock_bs:
            result = client.fetch_email_metadata(sync_cursor="expired_cursor")
        mock_bs.assert_called_once_with(500)
        assert result == fake_result


# ── _is_sync_cursor_valid ────────────────────────────────────────────


class TestIsSyncCursorValid:
    def test_valid_history_id_returns_true(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().history().list().execute.return_value = {"history": []}
        client.service = mock_service
        assert client._is_sync_cursor_valid("12345") is True

    def test_http_error_returns_false(self, client: GmailClient):
        mock_service = MagicMock()
        from googleapiclient.errors import HttpError
        from unittest.mock import PropertyMock
        resp = MagicMock()
        type(resp).status = PropertyMock(return_value=404)
        mock_service.users().history().list().execute.side_effect = HttpError(
            resp=resp, content=b"not found"
        )
        client.service = mock_service
        assert client._is_sync_cursor_valid("99999") is False

    def test_generic_exception_returns_false(self, client: GmailClient):
        mock_service = MagicMock()
        mock_service.users().history().list().execute.side_effect = RuntimeError("boom")
        client.service = mock_service
        assert client._is_sync_cursor_valid("12345") is False


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
