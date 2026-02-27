"""Unit tests for shared email client helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from core.email.helpers import (
    parse_expiry,
    unwrap_app_credentials,
    unwrap_user_tokens,
    wrap_account_tokens,
)


# ── parse_expiry ────────────────────────────────────────────────────


class TestParseExpiry:
    def test_none_returns_none(self):
        assert parse_expiry(None) is None

    def test_datetime_naive_returned_as_is(self):
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = parse_expiry(dt)
        assert result == dt
        assert result.tzinfo is None

    def test_datetime_aware_converted_to_utc_naive(self):
        tz_plus5 = timezone(timedelta(hours=5))
        dt = datetime(2024, 6, 15, 15, 30, 0, tzinfo=tz_plus5)
        result = parse_expiry(dt)
        assert result == datetime(2024, 6, 15, 10, 30, 0)
        assert result.tzinfo is None

    def test_timestamp_int(self):
        ts = 1718444400  # 2024-06-15T11:00:00Z
        result = parse_expiry(ts)
        expected = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        assert result == expected
        assert result.tzinfo is None

    def test_timestamp_float(self):
        ts = 1718444400.5
        result = parse_expiry(ts)
        expected = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        assert result == expected

    def test_iso_string(self):
        result = parse_expiry("2024-06-15T10:30:00")
        assert result == datetime(2024, 6, 15, 10, 30, 0)

    def test_iso_string_with_z_suffix(self):
        result = parse_expiry("2024-06-15T10:30:00Z")
        assert result == datetime(2024, 6, 15, 10, 30, 0)
        assert result.tzinfo is None

    def test_empty_string_returns_none(self):
        assert parse_expiry("") is None

    def test_invalid_string_raises_email_invalid_expiry_error(self):
        from core.email.errors import EmailInvalidExpiryError

        with pytest.raises(EmailInvalidExpiryError, match="Invalid expiry ISO string"):
            parse_expiry("not-a-date")

    def test_unsupported_type_raises_email_invalid_expiry_error(self):
        from core.email.errors import EmailInvalidExpiryError

        with pytest.raises(EmailInvalidExpiryError, match="Unsupported expiry type"):
            parse_expiry([1, 2, 3])


# ── unwrap_app_credentials ─────────────────────────────────────────


class TestUnwrapAppCredentials:
    def test_plain_dict_unchanged(self):
        creds = {"client_id": "id", "client_secret": "secret"}
        result = unwrap_app_credentials(creds)
        assert result == {"client_id": "id", "client_secret": "secret"}

    def test_secret_str_unwrapped(self):
        creds = {"client_id": "id", "client_secret": SecretStr("secret")}
        result = unwrap_app_credentials(creds)
        assert result["client_secret"] == "secret"

    def test_none_returns_empty_dict(self):
        result = unwrap_app_credentials(None)
        assert result == {}


# ── unwrap_user_tokens ──────────────────────────────────────────────


class TestUnwrapUserTokens:
    def test_unwraps_both_fields(self):
        tokens = {
            "access_token": SecretStr("at"),
            "refresh_token": SecretStr("rt"),
        }
        result = unwrap_user_tokens(tokens)
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"

    def test_plain_strings_unchanged(self):
        tokens = {"access_token": "at", "refresh_token": "rt"}
        result = unwrap_user_tokens(tokens)
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"


# ── wrap_account_tokens ─────────────────────────────────────────────


class TestWrapAccountTokens:
    def test_wraps_access_and_refresh(self):
        token_data = {"access_token": "at", "refresh_token": "rt", "scopes": ["s"]}
        result = wrap_account_tokens(token_data)
        assert isinstance(result["access_token"], SecretStr)
        assert result["access_token"].get_secret_value() == "at"
        assert isinstance(result["refresh_token"], SecretStr)
        assert result["refresh_token"].get_secret_value() == "rt"
        assert result["scopes"] == ["s"]

    def test_none_refresh_not_wrapped(self):
        token_data = {"access_token": "at", "refresh_token": None}
        result = wrap_account_tokens(token_data)
        assert isinstance(result["access_token"], SecretStr)
        assert result["refresh_token"] is None
