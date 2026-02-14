"""Unit tests for GmailClient helper methods and guard clauses."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

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


# ── _unwrap_app_credentials ─────────────────────────────────────────


class TestUnwrapAppCredentials:
    def test_plain_dict_unchanged(self, client: GmailClient):
        creds = {"client_id": "id", "client_secret": "secret"}
        result = client._unwrap_app_credentials(creds)
        assert result == {"client_id": "id", "client_secret": "secret"}

    def test_secret_str_unwrapped(self, client: GmailClient):
        creds = {"client_id": "id", "client_secret": SecretStr("secret")}
        result = client._unwrap_app_credentials(creds)
        assert result["client_secret"] == "secret"

    def test_none_returns_empty_dict(self, client: GmailClient):
        result = client._unwrap_app_credentials(None)
        assert result == {}


# ── _unwrap_user_tokens ──────────────────────────────────────────────


class TestUnwrapUserTokens:
    def test_unwraps_both_fields(self, client: GmailClient):
        tokens = {
            "access_token": SecretStr("at"),
            "refresh_token": SecretStr("rt"),
        }
        result = client._unwrap_user_tokens(tokens)
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"

    def test_plain_strings_unchanged(self, client: GmailClient):
        tokens = {"access_token": "at", "refresh_token": "rt"}
        result = client._unwrap_user_tokens(tokens)
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"


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


# ── _wrap_account_tokens ─────────────────────────────────────────────


class TestWrapAccountTokens:
    def test_wraps_access_and_refresh(self, client: GmailClient):
        token_data = {"access_token": "at", "refresh_token": "rt", "scopes": ["s"]}
        result = client._wrap_account_tokens(token_data)
        assert isinstance(result["access_token"], SecretStr)
        assert result["access_token"].get_secret_value() == "at"
        assert isinstance(result["refresh_token"], SecretStr)
        assert result["refresh_token"].get_secret_value() == "rt"
        assert result["scopes"] == ["s"]


# ── _parse_expiry ────────────────────────────────────────────────────


class TestParseExpiry:
    def test_none_returns_none(self, client: GmailClient):
        assert client._parse_expiry(None) is None

    def test_datetime_naive_returned_as_is(self, client: GmailClient):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = client._parse_expiry(dt)
        assert result == dt
        assert result.tzinfo is None

    def test_datetime_aware_converted_to_utc_naive(self, client: GmailClient):
        from datetime import timedelta

        tz_plus5 = timezone(timedelta(hours=5))
        dt = datetime(2024, 6, 15, 15, 30, 0, tzinfo=tz_plus5)
        result = client._parse_expiry(dt)
        assert result == datetime(2024, 6, 15, 10, 30, 0)
        assert result.tzinfo is None

    def test_timestamp_int(self, client: GmailClient):
        ts = 1718444400  # 2024-06-15T11:00:00Z
        result = client._parse_expiry(ts)
        expected = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        assert result == expected
        assert result.tzinfo is None

    def test_iso_string(self, client: GmailClient):
        result = client._parse_expiry("2024-06-15T10:30:00")
        assert result == datetime(2024, 6, 15, 10, 30, 0)

    def test_iso_string_with_z_suffix(self, client: GmailClient):
        result = client._parse_expiry("2024-06-15T10:30:00Z")
        assert result == datetime(2024, 6, 15, 10, 30, 0)
        assert result.tzinfo is None

    def test_empty_string_returns_none(self, client: GmailClient):
        assert client._parse_expiry("") is None

    def test_invalid_string_returns_none(self, client: GmailClient):
        assert client._parse_expiry("not-a-date") is None

    def test_unsupported_type_returns_none(self, client: GmailClient):
        assert client._parse_expiry([1, 2, 3]) is None


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
