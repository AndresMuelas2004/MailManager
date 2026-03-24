from __future__ import annotations

import pytest

from database.security import token_crypto
from database.errors.exceptions import SettingsError, TokenCryptoError

Fernet = pytest.importorskip("cryptography.fernet").Fernet


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    encrypted = token_crypto.encrypt_token("access-token-value")
    assert encrypted is not None
    assert encrypted != "access-token-value"
    assert token_crypto.decrypt_token(encrypted) == "access-token-value"


def test_encrypt_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)

    with pytest.raises(SettingsError):
        token_crypto.encrypt_token("token")


def test_invalid_key_raises_settings_error(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")

    with pytest.raises(SettingsError):
        token_crypto.get_fernet(required=True)


def test_decrypt_raises_token_crypto_error_on_invalid_data(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    with pytest.raises(TokenCryptoError, match="Failed to decrypt account token"):
        token_crypto.decrypt_token("not-valid-encrypted-data")


def test_decrypt_raises_token_crypto_error_on_unexpected_error(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    class _BrokenFernet:
        def decrypt(self, _data):
            raise RuntimeError("unexpected internal failure")

    monkeypatch.setattr(token_crypto, "get_fernet", lambda required=True: _BrokenFernet())

    with pytest.raises(TokenCryptoError, match="Unexpected token decryption error"):
        token_crypto.decrypt_token("some-encrypted-value")


# ===== get_active_key_id =====


def test_get_active_key_id_returns_configured(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "k42")
    assert token_crypto.get_active_key_id() == "k42"


def test_get_active_key_id_default_v1(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY_ID", raising=False)
    assert token_crypto.get_active_key_id() == "v1"


# ===== is_plaintext_fallback_enabled =====


def test_is_plaintext_fallback_enabled_true(monkeypatch):
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "true")
    assert token_crypto.is_plaintext_fallback_enabled() is True


def test_is_plaintext_fallback_enabled_false(monkeypatch):
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "false")
    assert token_crypto.is_plaintext_fallback_enabled() is False


# ===== None passthrough =====


def test_encrypt_token_none_returns_none(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    assert token_crypto.encrypt_token(None) is None


def test_decrypt_token_none_returns_none(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    assert token_crypto.decrypt_token(None) is None
