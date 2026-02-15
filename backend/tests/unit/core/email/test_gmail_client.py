"""Unit tests for GmailClient — build config and guard clauses.

Shared helper tests (parse_expiry, unwrap/wrap) live in ``test_helpers.py``.
"""

from __future__ import annotations

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

    def test_fetch_unread_emails_not_authenticated_raises_error(self, client: GmailClient):
        assert client.service is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.fetch_unread_emails()

    def test_send_email_not_authenticated_raises_error(self, client: GmailClient):
        assert client.service is None
        with pytest.raises(EmailNotAuthenticatedError):
            client.send_email("subj", "body", ["a@b.com"])

    def test_send_email_empty_recipients_raises_error(self, client: GmailClient):
        # Need to bypass the auth check by setting service to a truthy value
        client.service = object()
        with pytest.raises(EmailRecipientsMissingError):
            client.send_email("subj", "body", [])
