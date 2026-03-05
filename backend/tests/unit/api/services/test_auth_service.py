"""
Unit tests for the auth service layer.

All database stores are monkeypatched to avoid real DB calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from auth import AuthError, AuthTokenInvalidError, AuthTokenNetworkError

from api.errors.exceptions import ApiError, EnvVarError, ExternalAPIError, Unauthorized, UserNotFound
from api.schemas.auth import AuthResponse, UserOut
from api.services import auth_service


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_FAKE_USER = {
    "user_id": str(uuid4()),
    "google_sub": "goog-sub-123",
    "email": "unit@example.com",
    "name": "Unit Tester",
    "avatar_url": None,
    "created_at": "2025-01-01T00:00:00+00:00",
}

_FAKE_SESSION = {
    "session_id": str(uuid4()),
    "user_id": _FAKE_USER["user_id"],
    "expires_at": "2099-01-01T00:00:00+00:00",
    "created_at": "2025-01-01T00:00:00+00:00",
}


class FakeUserStore:
    def __init__(self, *, user=None):
        self._user = user
        self.deleted_ids: list[str] = []

    def upsert(self, user):
        return {**user, "created_at": "2025-01-01T00:00:00+00:00"}

    def get_by_id(self, user_id):
        if self._user and self._user["user_id"] == user_id:
            return dict(self._user)
        return None

    def get_by_google_sub(self, google_sub):
        if self._user and self._user["google_sub"] == google_sub:
            return dict(self._user)
        return None

    def delete(self, user_id):
        self.deleted_ids.append(user_id)
        if self._user and self._user["user_id"] == user_id:
            return True
        return False


class FakeSessionStore:
    def __init__(self, *, session=None):
        self._session = session
        self.deleted_ids: list[str] = []

    def create(self, session):
        return dict(session)

    def get(self, session_id):
        if self._session and self._session["session_id"] == session_id:
            return dict(self._session)
        return None

    def delete(self, session_id):
        self.deleted_ids.append(session_id)

    def delete_expired(self):
        pass


@pytest.fixture
def mock_response():
    return MagicMock()


# ------------------------------------------------------------------
# validate_session
# ------------------------------------------------------------------

def test_validate_session_none():
    with pytest.raises(Unauthorized, match="Authentication required"):
        auth_service.validate_session(None)


def test_validate_session_not_found(monkeypatch):
    monkeypatch.setattr(auth_service, "session_store", FakeSessionStore())
    with pytest.raises(Unauthorized, match="expired or invalid"):
        auth_service.validate_session("nonexistent-id")


def test_validate_session_valid(monkeypatch):
    store = FakeSessionStore(session=_FAKE_SESSION)
    monkeypatch.setattr(auth_service, "session_store", store)
    user_id = auth_service.validate_session(_FAKE_SESSION["session_id"])
    assert user_id == _FAKE_USER["user_id"]


# ------------------------------------------------------------------
# google_login
# ------------------------------------------------------------------

def test_google_login_invalid_token(monkeypatch, mock_response):
    def _raise(*_a, **_kw):
        raise AuthTokenInvalidError("bad token")

    monkeypatch.setattr(auth_service, "verify_google_token", _raise)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    with pytest.raises(Unauthorized, match="bad token"):
        auth_service.google_login("bad-token", mock_response)


def test_google_login_network_error(monkeypatch, mock_response):
    def _raise(*_a, **_kw):
        raise AuthTokenNetworkError("connection refused")

    monkeypatch.setattr(auth_service, "verify_google_token", _raise)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    with pytest.raises(ExternalAPIError, match="connection refused"):
        auth_service.google_login("some-token", mock_response)


def test_google_login_missing_email(monkeypatch, mock_response):
    fake_id_info = {"sub": "some-sub", "name": "No Email"}
    monkeypatch.setattr(
        auth_service, "verify_google_token",
        lambda *_a, **_kw: fake_id_info,
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    with pytest.raises(Unauthorized, match="missing 'email' claim"):
        auth_service.google_login("valid-token", mock_response)


def test_google_login_new_user(monkeypatch, mock_response):
    fake_id_info = {"sub": "new-sub", "email": "new@example.com", "name": "New"}
    monkeypatch.setattr(
        auth_service, "verify_google_token",
        lambda *_a, **_kw: fake_id_info,
    )
    monkeypatch.setattr(auth_service, "user_store", FakeUserStore())
    monkeypatch.setattr(auth_service, "session_store", FakeSessionStore())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    result = auth_service.google_login("valid-token", mock_response)
    assert isinstance(result, AuthResponse)
    assert result.user.email == "new@example.com"
    mock_response.set_cookie.assert_called_once()


def test_google_login_existing_user(monkeypatch, mock_response):
    fake_id_info = {"sub": _FAKE_USER["google_sub"], "email": "updated@example.com", "name": "Updated"}
    monkeypatch.setattr(
        auth_service, "verify_google_token",
        lambda *_a, **_kw: fake_id_info,
    )
    monkeypatch.setattr(auth_service, "user_store", FakeUserStore(user=_FAKE_USER))
    monkeypatch.setattr(auth_service, "session_store", FakeSessionStore())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    result = auth_service.google_login("valid-token", mock_response)
    assert isinstance(result, AuthResponse)
    assert result.user.email == "updated@example.com"


# ------------------------------------------------------------------
# logout
# ------------------------------------------------------------------

def test_logout_deletes_session(monkeypatch, mock_response):
    store = FakeSessionStore(session=_FAKE_SESSION)
    monkeypatch.setattr(auth_service, "session_store", store)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    result = auth_service.logout(_FAKE_SESSION["session_id"], mock_response)
    assert _FAKE_SESSION["session_id"] in store.deleted_ids
    assert result == {"status": "logged_out"}
    mock_response.delete_cookie.assert_called_once()


def test_logout_none_is_noop(monkeypatch, mock_response):
    store = FakeSessionStore()
    monkeypatch.setattr(auth_service, "session_store", store)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    result = auth_service.logout(None, mock_response)
    assert store.deleted_ids == []
    assert result == {"status": "logged_out"}


# ------------------------------------------------------------------
# get_current_user
# ------------------------------------------------------------------

def test_get_current_user_not_found(monkeypatch):
    monkeypatch.setattr(auth_service, "user_store", FakeUserStore())
    with pytest.raises(UserNotFound, match="User not found"):
        auth_service.get_current_user("nonexistent")


def test_get_current_user_found(monkeypatch):
    monkeypatch.setattr(auth_service, "user_store", FakeUserStore(user=_FAKE_USER))
    user = auth_service.get_current_user(_FAKE_USER["user_id"])
    assert isinstance(user, UserOut)
    assert user.email == _FAKE_USER["email"]


# ------------------------------------------------------------------
# delete_account
# ------------------------------------------------------------------

def test_delete_account_success(monkeypatch, mock_response):
    store = FakeUserStore(user=_FAKE_USER)
    monkeypatch.setattr(auth_service, "user_store", store)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    result = auth_service.delete_account(_FAKE_USER["user_id"], mock_response)
    assert result == {"status": "account_deleted"}
    assert _FAKE_USER["user_id"] in store.deleted_ids
    mock_response.delete_cookie.assert_called_once()


def test_delete_account_not_found(monkeypatch, mock_response):
    store = FakeUserStore()
    monkeypatch.setattr(auth_service, "user_store", store)
    with pytest.raises(UserNotFound, match="User not found"):
        auth_service.delete_account("nonexistent", mock_response)


# ------------------------------------------------------------------
# Error handling hardening — except Exception fallbacks
# ------------------------------------------------------------------

def test_google_login_settings_unexpected_error(monkeypatch, mock_response):
    """_load_auth_settings except Exception → EnvVarError."""
    def _raise():
        raise RuntimeError("config file missing")

    monkeypatch.setattr(auth_service, "get_auth_settings", _raise)

    with pytest.raises(EnvVarError, match="Failed to load auth settings"):
        auth_service.google_login("some-token", mock_response)


def test_google_login_verify_unexpected_error(monkeypatch, mock_response):
    """verify_google_token except Exception → Unauthorized."""
    def _raise(*_a, **_kw):
        raise RuntimeError("TLS handshake failed")

    monkeypatch.setattr(auth_service, "verify_google_token", _raise)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    with pytest.raises(Unauthorized, match="Token verification failed"):
        auth_service.google_login("some-token", mock_response)


def test_google_login_auth_base_error(monkeypatch, mock_response):
    """AuthError base class from verify → translated via _AUTH_TO_API_MAP → ApiError."""
    def _raise(*_a, **_kw):
        raise AuthError("generic auth failure")

    monkeypatch.setattr(auth_service, "verify_google_token", _raise)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")

    with pytest.raises(ApiError, match="generic auth failure"):
        auth_service.google_login("some-token", mock_response)
