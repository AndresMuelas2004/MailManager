"""Unit tests for OutlookClient helper methods, guard clauses, and refresh path."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from core.email.errors import (
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from core.email.outlook_client import OUTLOOK_SCOPES, OutlookClient


@pytest.fixture
def client() -> OutlookClient:
    return OutlookClient(account_label="mb__outlook")


# ── get_account_label ────────────────────────────────────────────────


def test_get_account_label_returns_constructor_value(client: OutlookClient):
    assert client.get_account_label() == "mb__outlook"


# ── _unwrap_app_credentials ─────────────────────────────────────────


class TestUnwrapAppCredentials:
    def test_plain_dict_unchanged(self, client: OutlookClient):
        creds = {"client_id": "id", "client_secret": "secret"}
        result = client._unwrap_app_credentials(creds)
        assert result == {"client_id": "id", "client_secret": "secret"}

    def test_secret_str_unwrapped(self, client: OutlookClient):
        creds = {"client_id": "id", "client_secret": SecretStr("secret")}
        result = client._unwrap_app_credentials(creds)
        assert result["client_secret"] == "secret"

    def test_none_returns_empty_dict(self, client: OutlookClient):
        result = client._unwrap_app_credentials(None)
        assert result == {}


# ── _unwrap_user_tokens ──────────────────────────────────────────────


class TestUnwrapUserTokens:
    def test_unwraps_both_fields(self, client: OutlookClient):
        tokens = {
            "access_token": SecretStr("at"),
            "refresh_token": SecretStr("rt"),
        }
        result = client._unwrap_user_tokens(tokens)
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"

    def test_plain_strings_unchanged(self, client: OutlookClient):
        tokens = {"access_token": "at", "refresh_token": "rt"}
        result = client._unwrap_user_tokens(tokens)
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"


# ── _wrap_account_tokens ─────────────────────────────────────────────


class TestWrapAccountTokens:
    def test_wraps_access_and_refresh(self, client: OutlookClient):
        token_data = {"access_token": "at", "refresh_token": "rt", "scopes": ["s"]}
        result = client._wrap_account_tokens(token_data)
        assert isinstance(result["access_token"], SecretStr)
        assert result["access_token"].get_secret_value() == "at"
        assert isinstance(result["refresh_token"], SecretStr)
        assert result["refresh_token"].get_secret_value() == "rt"

    def test_none_refresh_not_wrapped(self, client: OutlookClient):
        token_data = {"access_token": "at", "refresh_token": None}
        result = client._wrap_account_tokens(token_data)
        assert isinstance(result["access_token"], SecretStr)
        assert result["refresh_token"] is None


# ── _parse_expiry ────────────────────────────────────────────────────


class TestParseExpiry:
    def test_none_returns_none(self, client: OutlookClient):
        assert client._parse_expiry(None) is None

    def test_datetime_naive_returned_as_is(self, client: OutlookClient):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = client._parse_expiry(dt)
        assert result == dt
        assert result.tzinfo is None

    def test_datetime_aware_converted_to_utc_naive(self, client: OutlookClient):
        tz_plus5 = timezone(timedelta(hours=5))
        dt = datetime(2024, 6, 15, 15, 30, 0, tzinfo=tz_plus5)
        result = client._parse_expiry(dt)
        assert result == datetime(2024, 6, 15, 10, 30, 0)
        assert result.tzinfo is None

    def test_timestamp_float(self, client: OutlookClient):
        ts = 1718444400.5
        result = client._parse_expiry(ts)
        expected = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        assert result == expected

    def test_iso_string(self, client: OutlookClient):
        result = client._parse_expiry("2024-06-15T10:30:00")
        assert result == datetime(2024, 6, 15, 10, 30, 0)

    def test_iso_string_with_z_suffix(self, client: OutlookClient):
        result = client._parse_expiry("2024-06-15T10:30:00Z")
        assert result == datetime(2024, 6, 15, 10, 30, 0)
        assert result.tzinfo is None

    def test_empty_string_returns_none(self, client: OutlookClient):
        assert client._parse_expiry("") is None

    def test_invalid_string_returns_none(self, client: OutlookClient):
        assert client._parse_expiry("not-a-date") is None


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
