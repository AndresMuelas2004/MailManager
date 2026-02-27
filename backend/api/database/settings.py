"""
Centralized settings for database connectivity, token encryption, and provider credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from api.errors.exceptions import EnvVarError


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_DEFAULT_DB_POOL_MIN = 1
_DEFAULT_DB_POOL_MAX = 10
_DEFAULT_DB_CONNECT_TIMEOUT_SECONDS = 10
_DEFAULT_DB_APPLICATION_NAME = "mailmanager-api"

_DEFAULT_TOKEN_KEY_ID = "v1"
_DEFAULT_TOKEN_PLAINTEXT_FALLBACK = True
_DEFAULT_DB_AUTO_MIGRATE = False


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    pool_min_conn: int
    pool_max_conn: int
    connect_timeout_seconds: int
    application_name: str


@dataclass(frozen=True)
class TokenSettings:
    encryption_key: str | None
    encryption_key_id: str
    plaintext_fallback_enabled: bool


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise EnvVarError(
        f"{name} has an invalid boolean value.",
        {"value": raw, "accepted": sorted(_TRUE_VALUES | _FALSE_VALUES)},
    )


def _read_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise EnvVarError(f"{name} must be an integer.", {"value": raw}) from exc
    if value < minimum:
        raise EnvVarError(f"{name} must be >= {minimum}.", {"value": value})
    return value


def get_database_url() -> str:
    """
    Return DATABASE_URL from environment.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise EnvVarError("DATABASE_URL is not set.")
    return url


def get_database_settings() -> DatabaseSettings:
    """
    Read and validate all DB pool/runtime settings.
    """
    pool_min = _read_int("DB_POOL_MIN_CONN", _DEFAULT_DB_POOL_MIN, minimum=1)
    pool_max = _read_int("DB_POOL_MAX_CONN", _DEFAULT_DB_POOL_MAX, minimum=1)
    if pool_min > pool_max:
        raise EnvVarError(
            "DB pool settings are invalid: DB_POOL_MIN_CONN cannot be greater than DB_POOL_MAX_CONN.",
            {"DB_POOL_MIN_CONN": pool_min, "DB_POOL_MAX_CONN": pool_max},
        )
    timeout = _read_int(
        "DB_CONNECT_TIMEOUT_SECONDS",
        _DEFAULT_DB_CONNECT_TIMEOUT_SECONDS,
        minimum=1,
    )
    app_name = os.getenv("DB_APPLICATION_NAME", _DEFAULT_DB_APPLICATION_NAME).strip()
    if not app_name:
        app_name = _DEFAULT_DB_APPLICATION_NAME

    return DatabaseSettings(
        database_url=get_database_url(),
        pool_min_conn=pool_min,
        pool_max_conn=pool_max,
        connect_timeout_seconds=timeout,
        application_name=app_name,
    )


def get_token_settings() -> TokenSettings:
    """
    Read token-encryption settings.
    """
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip() or None
    key_id = os.getenv("TOKEN_ENCRYPTION_KEY_ID", _DEFAULT_TOKEN_KEY_ID).strip()
    if not key_id:
        key_id = _DEFAULT_TOKEN_KEY_ID
    return TokenSettings(
        encryption_key=key,
        encryption_key_id=key_id,
        plaintext_fallback_enabled=_read_bool(
            "TOKEN_PLAINTEXT_FALLBACK_ENABLED",
            _DEFAULT_TOKEN_PLAINTEXT_FALLBACK,
        ),
    )


def get_token_encryption_key(*, required: bool = True) -> str | None:
    """
    Return token encryption key when configured.
    """
    key = get_token_settings().encryption_key
    if key:
        return key
    if required:
        raise EnvVarError("TOKEN_ENCRYPTION_KEY is not set.")
    return None


def get_token_encryption_key_id() -> str:
    """
    Return active key identifier for encrypted tokens.
    """
    return get_token_settings().encryption_key_id


def is_token_plaintext_fallback_enabled() -> bool:
    """
    Return whether legacy plaintext token reads are temporarily allowed.
    """
    return get_token_settings().plaintext_fallback_enabled


_PROVIDER_CREDENTIALS_ENV_VARS: dict[str, str] = {
    "gmail": "MIA_GMAIL_CREDENTIALS_PATH",
    "outlook": "MIA_OUTLOOK_CREDENTIALS_PATH",
}


def get_provider_credentials_path(provider: str) -> str | None:
    """
    Return file path for provider app credentials from environment.

    Returns None when the provider has no configured env var.
    """
    env_var = _PROVIDER_CREDENTIALS_ENV_VARS.get(provider)
    if not env_var:
        return None
    path = os.getenv(env_var, "").strip()
    if not path:
        raise EnvVarError(f"{env_var} is not set.")
    return path


def is_startup_auto_migrate_enabled() -> bool:
    """
    Return whether startup should attempt migrations automatically.
    """
    return _read_bool("DB_AUTO_MIGRATE", _DEFAULT_DB_AUTO_MIGRATE)


def get_alembic_ini_path() -> Path:
    """
    Return Alembic config path.
    """
    raw = os.getenv("DB_ALEMBIC_INI_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "alembic.ini"

