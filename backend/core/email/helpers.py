"""
Shared helpers for email client implementations.

These pure functions handle token wrapping/unwrapping and expiry parsing
and are shared by all EmailClient subclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import SecretStr

from .errors import (
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
)


def http_error_detail(exc: Any) -> tuple[str, str]:
    """Extract (status, reason) from a googleapiclient HttpError."""
    return getattr(getattr(exc, "resp", None), "status", "unknown"), getattr(exc, "reason", "unknown")


def parse_expiry(value: Any) -> datetime | None:
    """Parse an expiry value (datetime, timestamp, or ISO string) into a naive UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError) as exc:
            raise EmailInvalidExpiryError(
                f"Invalid expiry timestamp ({type(exc).__name__}): {exc}"
            ) from exc
        except Exception as exc:
            raise EmailInvalidExpiryError(
                f"Unexpected expiry timestamp error ({type(exc).__name__}): {exc}"
            ) from exc
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise EmailInvalidExpiryError(
                f"Invalid expiry ISO string ({type(exc).__name__}): {exc}"
            ) from exc
        except Exception as exc:
            raise EmailInvalidExpiryError(
                f"Unexpected expiry parsing error ({type(exc).__name__}): {exc}"
            ) from exc
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    raise EmailInvalidExpiryError(
        f"Unsupported expiry type: {type(value).__name__}"
    )


def unwrap_app_credentials(app_credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Unwrap SecretStr values from an app credentials dict."""
    try:
        payload = dict(app_credentials or {})
    except (TypeError, ValueError) as exc:
        raise EmailInvalidCredentialsDataError(
            f"Invalid app credentials ({type(exc).__name__}): {exc}"
        ) from exc
    except Exception as exc:
        raise EmailInvalidCredentialsDataError(
            f"Unexpected error unwrapping app credentials ({type(exc).__name__}): {exc}"
        ) from exc
    secret = payload.get("client_secret")
    if isinstance(secret, SecretStr):
        payload["client_secret"] = secret.get_secret_value()
    return payload


def unwrap_user_tokens(user_tokens: dict[str, Any] | None) -> dict[str, Any]:
    """Unwrap SecretStr values from a user token dict."""
    try:
        payload = dict(user_tokens or {})
    except (TypeError, ValueError) as exc:
        raise EmailInvalidTokenDataError(
            f"Invalid user tokens ({type(exc).__name__}): {exc}"
        ) from exc
    except Exception as exc:
        raise EmailInvalidTokenDataError(
            f"Unexpected error unwrapping user tokens ({type(exc).__name__}): {exc}"
        ) from exc
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if isinstance(access_token, SecretStr):
        payload["access_token"] = access_token.get_secret_value()
    if isinstance(refresh_token, SecretStr):
        payload["refresh_token"] = refresh_token.get_secret_value()
    return payload


def wrap_account_tokens(token_data: dict[str, Any]) -> dict[str, Any]:
    """Wrap sensitive token fields as SecretStr."""
    try:
        payload = dict(token_data or {})
    except (TypeError, ValueError) as exc:
        raise EmailInvalidTokenDataError(
            f"Invalid token data ({type(exc).__name__}): {exc}"
        ) from exc
    except Exception as exc:
        raise EmailInvalidTokenDataError(
            f"Unexpected error wrapping tokens ({type(exc).__name__}): {exc}"
        ) from exc
    if "access_token" in payload:
        payload["access_token"] = SecretStr(str(payload.get("access_token")))
    if "refresh_token" in payload and payload["refresh_token"] is not None:
        payload["refresh_token"] = SecretStr(str(payload.get("refresh_token")))
    return payload
