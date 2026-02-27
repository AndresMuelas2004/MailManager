"""
Centralized settings for authentication.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_DEFAULT_SESSION_LIFETIME_DAYS = 7
_DEFAULT_COOKIE_SECURE = False


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} has an invalid boolean value: {raw!r} "
        f"(accepted: {sorted(_TRUE_VALUES | _FALSE_VALUES)})"
    )


def _read_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}.") from None
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}.")
    return value


@dataclass(frozen=True)
class AuthSettings:
    google_client_id: str
    session_lifetime_days: int
    cookie_secure: bool


def get_auth_settings() -> AuthSettings:
    """
    Read and validate auth settings from the environment.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not set.")
    return AuthSettings(
        google_client_id=client_id,
        session_lifetime_days=_read_int(
            "AUTH_SESSION_LIFETIME_DAYS",
            _DEFAULT_SESSION_LIFETIME_DAYS,
            minimum=1,
        ),
        cookie_secure=_read_bool("AUTH_COOKIE_SECURE", _DEFAULT_COOKIE_SECURE),
    )
