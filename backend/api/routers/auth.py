"""
Authentication router for Google OIDC login, session management.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Response

from api.routers.routers_helpers import require_session
from api.schemas.auth import AuthResponse, GoogleLoginRequest, UserOut
from api.services import auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=AuthResponse)
def google_login(payload: GoogleLoginRequest, response: Response) -> AuthResponse:
    """
    Verify a Google id_token and create a server-side session.
    """
    return auth_service.google_login(payload.id_token, response)


@router.get("/me", response_model=UserOut)
def get_me(user_id: str = Depends(require_session)) -> UserOut:
    """
    Return the currently authenticated user.
    """
    return auth_service.get_current_user(user_id)


@router.post("/logout")
def logout(
    response: Response,
    session_id: str | None = Cookie(default=None),
) -> dict[str, str]:
    """
    Delete the current session and clear the cookie.
    """
    return auth_service.logout(session_id, response)


@router.delete("/me")
def delete_account(
    response: Response,
    user_id: str = Depends(require_session),
) -> dict[str, str]:
    """
    Delete the authenticated user and all associated data, then clear the cookie.
    """
    return auth_service.delete_account(user_id, response)
