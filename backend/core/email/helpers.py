"""
Shared helpers for email client implementations.

These pure functions handle token wrapping/unwrapping and expiry parsing
and are shared by all EmailClient subclasses.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import SecretStr

from .errors import (
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
)

logger = logging.getLogger(__name__)


def http_error_detail(exc: Any) -> tuple[str, str]:
    """Extract (status, reason) from a googleapiclient HttpError."""
    status = getattr(getattr(exc, "resp", None), "status", "unknown")
    reason = getattr(exc, "reason", "unknown")
    return status, reason


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


def decode_mime_body(data_b64url: str, charset_hint: str | None) -> str | None:
    """Decode a base64url-encoded MIME body into a Python str.

    Gmail returns each MIME part's body as ``base64url`` bytes plus a declared
    ``charset`` taken from the part's ``Content-Type`` header. That declaration
    is unreliable: senders frequently mislabel UTF-8 bytes as ``iso-8859-1`` or
    ``windows-1252`` (a common bug in older mail clients). Trusting the hint
    blindly produces mojibake — UTF-8 byte sequences like ``C3 A9`` (``é``)
    get re-interpreted as Latin-1 and rendered as ``Ã©``.

    Strategy (UTF-8-first with validated fallback):
    1. **Try UTF-8 strict.** Real UTF-8 bodies always decode without error.
       A legitimate Latin-1 body with any non-ASCII byte ≥ 0x80 will fail
       on UTF-8 continuation-byte validation, so we cannot misdecode it here.
    2. **Fallback to the declared charset** (if any, and if it isn't UTF-8
       itself). Covers correctly-labelled Latin-1 / Windows-1252 / Big5 / etc.
    3. **Last resort: UTF-8 with ``errors="replace"``.** Preserves the ASCII
       portion of the body even when both prior attempts fail.

    Returns ``None`` only if the base64 payload itself is invalid.
    """
    try:
        raw = base64.urlsafe_b64decode(data_b64url + "==")
    except binascii.Error:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    hint = (charset_hint or "").strip().lower()
    if hint and hint not in {"utf-8", "utf8"}:
        try:
            decoded = raw.decode(hint, errors="replace")
            logger.debug(
                "decode_mime_body: UTF-8 strict failed; decoded with declared charset=%s",
                hint,
            )
            return decoded
        except LookupError:
            pass
    return raw.decode("utf-8", errors="replace")


_CID_REF_PATTERN = re.compile(
    r"""(?P<attr>src|background)\s*=\s*(?P<quote>["']?)cid:<?(?P<cid>[^"'>\s]+?)>?(?P=quote)""",
    re.IGNORECASE,
)

# Matches ``url(cid:<id>)`` inside CSS values — e.g. ``style="background-image:url(cid:…)"``
# produced by premailer when it inlines CSS rules from <style> blocks.
_CID_URL_FUNC_PATTERN = re.compile(
    r"""url\(\s*(?P<quote>["']?)cid:<?(?P<cid>[^"'>)\s]+?)>?(?P=quote)\s*\)""",
    re.IGNORECASE,
)


def _cid_replacer(cid_map: dict[str, str], formatter):
    """Build a regex ``sub`` replacer that resolves ``cid:<id>`` references.

    ``formatter(match, data_url)`` receives the match and the resolved data URL
    and returns the replacement string. Unmapped CIDs fall through to the
    original match text (soft fallback — broken image beats lost email).
    """
    def _replace(match: re.Match[str]) -> str:
        cid = match.group("cid").strip()
        data_url = cid_map.get(cid)
        if data_url is None:
            return match.group(0)
        return formatter(match, data_url)
    return _replace


def inline_cid_images(html: str, cid_map: dict[str, str]) -> str:
    """Replace ``cid:<id>`` references with data URLs from ``cid_map``.

    Handles two forms:
    - HTML attributes: ``src="cid:…"`` / ``background="cid:…"``.
    - CSS ``url(cid:…)`` inside ``style="…"`` (after premailer CSS inlining).

    Tolerant to single/double/no quotes and optional angle brackets around
    the CID. Unmapped CIDs are left untouched (soft fallback).
    """
    if not html or not cid_map:
        return html

    html = _CID_REF_PATTERN.sub(
        _cid_replacer(cid_map, lambda m, url: f'{m.group("attr")}="{url}"'),
        html,
    )
    html = _CID_URL_FUNC_PATTERN.sub(
        _cid_replacer(cid_map, lambda _m, url: f'url("{url}")'),
        html,
    )
    return html
