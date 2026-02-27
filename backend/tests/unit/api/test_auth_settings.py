"""
Unit tests for auth.settings (auth settings).
"""

from __future__ import annotations

import pytest

from auth import settings


def test_get_auth_settings_defaults(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "my-client-id")
    monkeypatch.delenv("AUTH_SESSION_LIFETIME_DAYS", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)

    cfg = settings.get_auth_settings()

    assert cfg.google_client_id == "my-client-id"
    assert cfg.session_lifetime_days == 7
    assert cfg.cookie_secure is False


def test_get_auth_settings_missing_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
        settings.get_auth_settings()


def test_get_auth_settings_custom_values(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "custom-id")
    monkeypatch.setenv("AUTH_SESSION_LIFETIME_DAYS", "14")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")

    cfg = settings.get_auth_settings()

    assert cfg.google_client_id == "custom-id"
    assert cfg.session_lifetime_days == 14
    assert cfg.cookie_secure is True


def test_get_auth_settings_invalid_session_lifetime(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("AUTH_SESSION_LIFETIME_DAYS", "not-a-number")

    with pytest.raises(ValueError, match="AUTH_SESSION_LIFETIME_DAYS"):
        settings.get_auth_settings()


def test_get_auth_settings_invalid_cookie_secure(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "maybe")

    with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
        settings.get_auth_settings()
