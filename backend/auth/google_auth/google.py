"""
Pure Google OIDC token verification — no framework coupling.
"""

from __future__ import annotations

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


def verify_google_token(raw_id_token: str, google_client_id: str) -> dict:
    """
    Verify a Google ``id_token`` and return the decoded claims.

    Raises ``ValueError`` on any verification failure.
    """
    try:
        return id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience=google_client_id,
            clock_skew_in_seconds=10,
        )
    except Exception as exc:
        raise ValueError(f"Google token verification failed: {exc}") from exc
