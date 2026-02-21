"""
Token encryption helpers using Fernet.
"""

from __future__ import annotations

try:
    from cryptography.fernet import Fernet, InvalidToken
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    Fernet = None

    class InvalidToken(Exception):
        pass

from api.database.settings import get_token_encryption_key, get_token_encryption_key_id
from api.errors.exceptions import DatabaseError, EnvVarError


def _build_fernet(key: str) -> Fernet:
    if Fernet is None:
        raise EnvVarError("cryptography is required for Fernet token encryption.")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise EnvVarError("TOKEN_ENCRYPTION_KEY is invalid for Fernet.") from exc


def get_fernet(*, required: bool = True) -> Fernet | None:
    """
    Return a Fernet instance from TOKEN_ENCRYPTION_KEY.
    """
    key = get_token_encryption_key(required=required)
    if not key:
        return None
    return _build_fernet(key)


def get_active_key_id() -> str:
    """
    Return current encryption key identifier.
    """
    return get_token_encryption_key_id()


def encrypt_token(value: str | None) -> str | None:
    """
    Encrypt one token value.
    """
    if value is None:
        return None
    fernet = get_fernet(required=True)
    encrypted = fernet.encrypt(value.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_token(value: str | None) -> str | None:
    """
    Decrypt one token value.
    """
    if value is None:
        return None
    fernet = get_fernet(required=True)
    try:
        decrypted = fernet.decrypt(value.encode("utf-8"))
    except InvalidToken as exc:
        raise DatabaseError("Failed to decrypt account token.") from exc
    return decrypted.decode("utf-8")
