from __future__ import annotations

import pytest

from api.database.security import token_crypto
from api.errors.exceptions import EnvVarError, TokenDecryptionError

Fernet = pytest.importorskip("cryptography.fernet").Fernet


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    encrypted = token_crypto.encrypt_token("access-token-value")
    assert encrypted is not None
    assert encrypted != "access-token-value"
    assert token_crypto.decrypt_token(encrypted) == "access-token-value"


def test_encrypt_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)

    with pytest.raises(EnvVarError):
        token_crypto.encrypt_token("token")


def test_invalid_key_raises_env_error(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")

    with pytest.raises(EnvVarError):
        token_crypto.get_fernet(required=True)


def test_decrypt_raises_token_decryption_error_on_invalid_data(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    with pytest.raises(TokenDecryptionError, match="Failed to decrypt account token"):
        token_crypto.decrypt_token("not-valid-encrypted-data")
