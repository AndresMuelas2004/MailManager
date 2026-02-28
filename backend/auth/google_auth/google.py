"""
Pure Google OIDC token verification — no framework coupling.
"""

from __future__ import annotations

from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from auth.errors.errors import (
    AuthTokenInvalidError,
    AuthTokenNetworkError,
    AuthTokenProviderError,
)


def verify_google_token(raw_id_token: str, google_client_id: str) -> dict:
    """
    Verify a Google ``id_token`` and return the decoded claims.

    Raises ``AuthTokenError`` subclasses on any verification failure.
    """
    try:
        return id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience=google_client_id,
            clock_skew_in_seconds=10,
        )
    except TransportError as exc:
        raise AuthTokenNetworkError(
            f"Google token verification network error: {exc}",
        ) from exc
    except GoogleAuthError as exc:
        raise AuthTokenProviderError(
            f"Google token rejected: {exc}",
        ) from exc
    except ValueError as exc:
        raise AuthTokenInvalidError(
            f"Google token malformed: {exc}",
        ) from exc
    except Exception as exc:
        raise AuthTokenInvalidError(
            f"Google token verification failed ({type(exc).__name__}): {exc}",
        ) from exc
