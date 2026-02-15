"""
Shared helpers for email client implementations.

These pure functions handle token wrapping/unwrapping and expiry parsing
and are shared by all EmailClient subclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import SecretStr


def parse_expiry(value: Any) -> datetime | None:
    """Parse an expiry value (datetime, timestamp, or ISO string) into a naive UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return None


def unwrap_app_credentials(app_credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Unwrap SecretStr values from an app credentials dict."""
    payload = dict(app_credentials or {})
    secret = payload.get("client_secret")
    if isinstance(secret, SecretStr):
        payload["client_secret"] = secret.get_secret_value()
    return payload


def unwrap_user_tokens(user_tokens: dict[str, Any] | None) -> dict[str, Any]:
    """Unwrap SecretStr values from a user token dict."""
    payload = dict(user_tokens or {})
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if isinstance(access_token, SecretStr):
        payload["access_token"] = access_token.get_secret_value()
    if isinstance(refresh_token, SecretStr):
        payload["refresh_token"] = refresh_token.get_secret_value()
    return payload


def wrap_account_tokens(token_data: dict[str, Any]) -> dict[str, Any]:
    """Wrap sensitive token fields as SecretStr."""
    payload = dict(token_data or {})
    if "access_token" in payload:
        payload["access_token"] = SecretStr(str(payload.get("access_token")))
    if "refresh_token" in payload and payload["refresh_token"] is not None:
        payload["refresh_token"] = SecretStr(str(payload.get("refresh_token")))
    return payload
