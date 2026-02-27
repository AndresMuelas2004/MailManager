"""
Integration tests for authentication endpoints and ownership enforcement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.routers.routers_helpers import require_session
from api.services import auth_service
from tests.integration.conftest import TEST_USER_ID


_MAILBOX_URL = "/mailboxes"


# ------------------------------------------------------------------
# POST /auth/google — happy path
# ------------------------------------------------------------------

def test_google_login_success(test_client_base, isolated_db, monkeypatch, app):
    """Monkeypatch Google verification, verify cookie set and user returned."""
    fake_id_info = {
        "sub": "google-sub-login-test",
        "email": "login@example.com",
        "name": "Login User",
        "picture": "https://example.com/avatar.png",
    }
    monkeypatch.setattr(
        auth_service, "verify_google_token",
        lambda *_a, **_kw: fake_id_info,
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    resp = test_client_base.post("/auth/google", json={"id_token": "valid-token"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Login successful."
    assert data["user"]["email"] == "login@example.com"
    assert "session_id" in resp.cookies


def test_google_login_invalid_token(test_client_base, isolated_db, monkeypatch, app):
    """Invalid token raises Unauthorized -> 401."""
    def _raise(*_a, **_kw):
        raise ValueError("Invalid token")

    monkeypatch.setattr(auth_service, "verify_google_token", _raise)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    resp = test_client_base.post("/auth/google", json={"id_token": "bad-token"})
    assert resp.status_code == 401


# ------------------------------------------------------------------
# GET /auth/me
# ------------------------------------------------------------------

def test_get_me_authenticated(test_client):
    """Authenticated user can fetch their profile."""
    resp = test_client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == TEST_USER_ID


def test_get_me_no_session(test_client_base, isolated_db, app):
    """No cookie -> 401."""
    # Temporarily remove the override to test real behavior.
    override = app.dependency_overrides.pop(require_session, None)
    try:
        resp = test_client_base.get("/auth/me")
        assert resp.status_code == 401
    finally:
        if override is not None:
            app.dependency_overrides[require_session] = override


def test_get_me_expired_session(test_client_base, isolated_db, app):
    """Expired session -> 401."""
    override = app.dependency_overrides.pop(require_session, None)
    try:
        # Create an already-expired session.
        session_id = str(uuid4())
        with isolated_db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (session_id, user_id, expires_at)
                VALUES (%(session_id)s, %(user_id)s, %(expires_at)s)
                """,
                {
                    "session_id": session_id,
                    "user_id": TEST_USER_ID,
                    "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                },
            )
        resp = test_client_base.get("/auth/me", cookies={"session_id": session_id})
        assert resp.status_code == 401
    finally:
        if override is not None:
            app.dependency_overrides[require_session] = override


# ------------------------------------------------------------------
# POST /auth/logout
# ------------------------------------------------------------------

def test_logout(test_client_base, isolated_db, monkeypatch, app):
    """Login then logout clears session."""
    fake_id_info = {
        "sub": "google-sub-logout-test",
        "email": "logout@example.com",
        "name": "Logout User",
    }
    monkeypatch.setattr(
        auth_service, "verify_google_token",
        lambda *_a, **_kw: fake_id_info,
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    login_resp = test_client_base.post("/auth/google", json={"id_token": "tok"})
    assert login_resp.status_code == 200

    session_cookie = login_resp.cookies.get("session_id")
    logout_resp = test_client_base.post("/auth/logout", cookies={"session_id": session_cookie})
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"status": "logged_out"}


# ------------------------------------------------------------------
# Ownership
# ------------------------------------------------------------------

def test_create_mailbox_sets_owner(test_client):
    """Created mailbox has owner_user_id set to the authenticated user."""
    resp = test_client.post(_MAILBOX_URL, json={"display_name": "Owned MB"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner_user_id"] == TEST_USER_ID


def test_list_mailboxes_filtered_by_owner(test_client, isolated_db):
    """Each user only sees their own mailboxes."""
    # Create a mailbox for the test user (via the overridden session).
    test_client.post(_MAILBOX_URL, json={"display_name": "My MB"})

    # Create a second user and a mailbox owned by them directly in the DB.
    other_user_id = str(uuid4())
    other_mailbox_id = str(uuid4())
    with isolated_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, google_sub, email)
            VALUES (%(user_id)s, %(google_sub)s, %(email)s)
            """,
            {"user_id": other_user_id, "google_sub": "other-sub", "email": "other@example.com"},
        )
        cur.execute(
            """
            INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
            VALUES (%(mailbox_id)s, %(display_name)s, %(owner_user_id)s)
            """,
            {
                "mailbox_id": other_mailbox_id,
                "display_name": "Other MB",
                "owner_user_id": other_user_id,
            },
        )

    resp = test_client.get(_MAILBOX_URL)
    assert resp.status_code == 200
    ids = [m["mailbox_id"] for m in resp.json()]
    assert other_mailbox_id not in ids


def test_protected_endpoint_no_auth(test_client_base, isolated_db, app):
    """GET /mailboxes without session cookie -> 401."""
    override = app.dependency_overrides.pop(require_session, None)
    try:
        resp = test_client_base.get(_MAILBOX_URL)
        assert resp.status_code == 401
    finally:
        if override is not None:
            app.dependency_overrides[require_session] = override


# ------------------------------------------------------------------
# DELETE /auth/me
# ------------------------------------------------------------------

def test_delete_account_success(test_client, isolated_db, monkeypatch):
    """Deleting own account removes user, cascades to mailboxes, clears cookie."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    # Create a mailbox so we can verify cascade.
    mb_resp = test_client.post(_MAILBOX_URL, json={"display_name": "To be cascaded"})
    assert mb_resp.status_code == 200

    resp = test_client.delete("/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"status": "account_deleted"}

    # Cookie should be cleared.
    assert resp.headers.get("set-cookie") is not None
    assert "session_id" in resp.headers["set-cookie"]

    # User row should be gone.
    with isolated_db.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE user_id = %s", (TEST_USER_ID,))
        assert cur.fetchone() is None

    # Mailboxes should be gone (CASCADE).
    with isolated_db.cursor() as cur:
        cur.execute("SELECT 1 FROM mailboxes WHERE owner_user_id = %s", (TEST_USER_ID,))
        assert cur.fetchone() is None


def test_delete_account_user_gone(test_client, isolated_db):
    """Deleting a user that was already removed returns 404."""
    # Remove the test user directly.
    with isolated_db.cursor() as cur:
        cur.execute("DELETE FROM users WHERE user_id = %s", (TEST_USER_ID,))

    resp = test_client.delete("/auth/me")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "user_not_found"


def test_delete_account_no_session(test_client_base, isolated_db, app):
    """DELETE /auth/me without session cookie -> 401."""
    override = app.dependency_overrides.pop(require_session, None)
    try:
        resp = test_client_base.delete("/auth/me")
        assert resp.status_code == 401
    finally:
        if override is not None:
            app.dependency_overrides[require_session] = override


def test_mailbox_ownership_forbidden(test_client, isolated_db):
    """User A's mailbox accessed by user B -> 403."""
    other_user_id = str(uuid4())
    other_mailbox_id = str(uuid4())
    with isolated_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, google_sub, email)
            VALUES (%(user_id)s, %(google_sub)s, %(email)s)
            """,
            {"user_id": other_user_id, "google_sub": "forbidden-sub", "email": "b@example.com"},
        )
        cur.execute(
            """
            INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
            VALUES (%(mailbox_id)s, %(display_name)s, %(owner_user_id)s)
            """,
            {
                "mailbox_id": other_mailbox_id,
                "display_name": "Forbidden MB",
                "owner_user_id": other_user_id,
            },
        )

    resp = test_client.get(f"{_MAILBOX_URL}/{other_mailbox_id}")
    assert resp.status_code == 403


# ------------------------------------------------------------------
# NULL owner_user_id defense-in-depth
# ------------------------------------------------------------------

def test_null_owner_mailbox_forbidden(test_client, isolated_db):
    """A mailbox with NULL owner_user_id must not be accessible."""
    orphan_id = str(uuid4())
    with isolated_db.cursor() as cur:
        cur.execute("ALTER TABLE mailboxes ALTER COLUMN owner_user_id DROP NOT NULL")
        cur.execute(
            """
            INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
            VALUES (%(mailbox_id)s, %(display_name)s, NULL)
            """,
            {"mailbox_id": orphan_id, "display_name": "Orphan MB"},
        )

    resp = test_client.get(f"{_MAILBOX_URL}/{orphan_id}")
    assert resp.status_code == 403


def test_null_owner_mailbox_not_listed(test_client, isolated_db):
    """A mailbox with NULL owner_user_id must not appear in the listing."""
    orphan_id = str(uuid4())
    with isolated_db.cursor() as cur:
        cur.execute("ALTER TABLE mailboxes ALTER COLUMN owner_user_id DROP NOT NULL")
        cur.execute(
            """
            INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
            VALUES (%(mailbox_id)s, %(display_name)s, NULL)
            """,
            {"mailbox_id": orphan_id, "display_name": "Orphan MB"},
        )

    resp = test_client.get(_MAILBOX_URL)
    assert resp.status_code == 200
    ids = [m["mailbox_id"] for m in resp.json()]
    assert orphan_id not in ids
