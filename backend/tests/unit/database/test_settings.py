from __future__ import annotations

import pytest

from database import settings
from database.errors.exceptions import SettingsError


def test_get_database_settings_uses_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mailmanager")
    monkeypatch.delenv("DB_POOL_MIN_CONN", raising=False)
    monkeypatch.delenv("DB_POOL_MAX_CONN", raising=False)
    monkeypatch.delenv("DB_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DB_APPLICATION_NAME", raising=False)

    cfg = settings.get_database_settings()

    assert cfg.pool_min_conn == 1
    assert cfg.pool_max_conn == 10
    assert cfg.connect_timeout_seconds == 10
    assert cfg.application_name == "mailmanager-api"


def test_get_database_settings_validates_pool_range(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mailmanager")
    monkeypatch.setenv("DB_POOL_MIN_CONN", "12")
    monkeypatch.setenv("DB_POOL_MAX_CONN", "5")

    with pytest.raises(SettingsError):
        settings.get_database_settings()


def test_token_plaintext_fallback_parses_boolean(monkeypatch):
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "false")
    assert settings.is_token_plaintext_fallback_enabled() is False


def test_token_plaintext_fallback_rejects_invalid_boolean(monkeypatch):
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "sometimes")

    with pytest.raises(SettingsError):
        settings.is_token_plaintext_fallback_enabled()
