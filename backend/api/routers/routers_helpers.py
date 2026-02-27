"""
Shared helpers used across all routers.
"""

from __future__ import annotations

from fastapi import Cookie

from api.services import auth_service


def require_session(session_id: str | None = Cookie(default=None)) -> str:
    """
    Validate the session cookie and return the authenticated user_id.
    """
    return auth_service.validate_session(session_id)
