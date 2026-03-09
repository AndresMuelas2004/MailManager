"""
Service layer for authentication operations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Response

from auth import (
    AuthError,
    AuthSettings,
    get_auth_settings,
    verify_google_token,
)

from database import DatabaseError, session_store, user_store
from api.errors.exceptions import ApiError, EnvVarError, Unauthorized, UserNotFound
from api.schemas.auth import AuthResponse, UserOut
from api.services.services_helpers import translate_auth_error, translate_database_error

logger = logging.getLogger(__name__)


def _load_auth_settings() -> AuthSettings:
    """Load auth settings, translating auth errors to API errors."""
    try:
        return get_auth_settings()
    except AuthError as exc:
        raise translate_auth_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected auth settings error (%s): %s", type(exc).__name__, exc)
        raise EnvVarError("Failed to load auth settings.") from exc


def _set_session_cookie(response: Response, session_id: str, settings: AuthSettings) -> None:
    """Set the HttpOnly session cookie on *response*."""
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_lifetime_days * 86400,
    )


def _clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    """Clear the session cookie on *response*."""
    response.delete_cookie(
        key="session_id",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def google_login(raw_id_token: str, response: Response) -> AuthResponse:
    """
    Verify a Google id_token, upsert the user, create a session,
    and set the session cookie on *response*.

    Returns an ``AuthResponse`` containing the user and a message.
    """
    settings = _load_auth_settings()
    try:
        id_info = verify_google_token(raw_id_token, settings.google_client_id)
    except AuthError as exc:
        logger.debug("Google token verification failed: %s", exc)
        raise translate_auth_error(exc) from exc
    except Exception as exc:
        logger.warning("Google token verification unexpected error (%s): %s", type(exc).__name__, exc)
        raise Unauthorized("Token verification failed.") from exc

    google_sub = id_info.get("sub")
    if not google_sub:
        raise Unauthorized("Token missing 'sub' claim.")

    email = id_info.get("email", "")
    if not email:
        raise Unauthorized("Token missing 'email' claim.")

    # Only used for new users; the UPSERT returns the existing user_id for returning users.
    user_id = str(uuid4())
    try:
        user = user_store.upsert({
            "user_id": user_id,
            "google_sub": google_sub,
            "email": email,
            "name": id_info.get("name"),
            "avatar_url": id_info.get("picture"),
        })
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected user upsert error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to upsert user.") from exc

    session_id = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_lifetime_days)
    try:
        session_store.create({
            "session_id": session_id,
            "user_id": user["user_id"],
            "expires_at": expires_at.isoformat(),
        })
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected session creation error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to create session.") from exc

    _set_session_cookie(response, session_id, settings)
    _cleanup_expired_sessions()
    return AuthResponse(user=UserOut(**user), message="Login successful.")


def validate_session(session_id: str | None) -> str:
    """
    Validate a session cookie and return the user_id.

    Raises ``Unauthorized`` when session_id is absent, invalid, or expired.
    """
    if not session_id:
        raise Unauthorized("Authentication required.")
    try:
        session = session_store.get(session_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected session validation error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to validate session.") from exc
    if session is None:
        raise Unauthorized("Session expired or invalid.")
    return session["user_id"]


def logout(session_id: str | None, response: Response) -> dict[str, str]:
    """
    Delete the session identified by *session_id* and clear the cookie.
    """
    if session_id:
        try:
            session_store.delete(session_id)
        except DatabaseError as exc:
            raise translate_database_error(exc) from exc
        except Exception as exc:
            logger.warning("Unexpected session deletion error (%s): %s", type(exc).__name__, exc)
            raise ApiError("Failed to delete session.") from exc
    settings = _load_auth_settings()
    _clear_session_cookie(response, settings)
    return {"status": "logged_out"}


def delete_account(user_id: str, response: Response) -> dict[str, str]:
    """
    Delete the user and all associated data (CASCADE handles mailboxes,
    accounts, tokens, and sessions), then clear the session cookie.

    Raises ``UserNotFound`` when the user does not exist.
    """
    try:
        deleted = user_store.delete(user_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected user deletion error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to delete user.") from exc
    if not deleted:
        raise UserNotFound("User not found.", {"user_id": user_id})
    settings = _load_auth_settings()
    _clear_session_cookie(response, settings)
    return {"status": "account_deleted"}


def _cleanup_expired_sessions() -> None:
    """Best-effort removal of expired sessions. Failures are logged, not raised."""
    try:
        session_store.delete_expired()
    except Exception:
        logger.warning("Expired session cleanup failed.", exc_info=True)


def get_current_user(user_id: str) -> UserOut:
    """
    Fetch the user record for *user_id*.

    Raises ``UserNotFound`` when the user no longer exists.
    """
    try:
        user = user_store.get_by_id(user_id)
    except DatabaseError as exc:
        raise translate_database_error(exc) from exc
    except Exception as exc:
        logger.warning("Unexpected user lookup error (%s): %s", type(exc).__name__, exc)
        raise ApiError("Failed to look up user.") from exc
    if user is None:
        raise UserNotFound("User not found.", {"user_id": user_id})
    return UserOut(**user)
