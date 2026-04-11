"""
Integration tests for the GET /{provider_message_id}/content endpoint.

Tests exercise the full router -> service -> core -> storage flow.
Only external dependencies (provider APIs, disk tokens) are faked
via the integration conftest fixtures.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg2.extras
import pytest

from core.email import EmailContent
from core.email.errors import EmailExternalAPIError
from tests.integration.conftest import (
    MAILBOX_URL as _MAILBOX_URL,
)


def _content_url(mailbox_id: str, message_id: str, account_id: str) -> str:
    return f"{_MAILBOX_URL}/{mailbox_id}/emails/{message_id}/content?account_id={account_id}"


# ------------------------------------------------------------------
# Happy path — DB miss, fetched from FakeEmailClient
# ------------------------------------------------------------------


def test_get_email_content_db_miss_fetches_from_provider(
    test_client, setup_mailbox_and_account,
):
    """When email content is not in DB, the endpoint fetches from the provider."""
    mid, aid = setup_mailbox_and_account(test_client)
    # Sync metadata first so the account exists in the DB
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    resp = test_client.get(_content_url(mid, "m1", aid))
    assert resp.status_code == 200
    data = resp.json()
    # FakeEmailClient.fetch_email_content returns EmailContent(html_body=None, text_body=None)
    assert data["html_body"] is None
    assert data["text_body"] is None


# ------------------------------------------------------------------
# Happy path — DB hit (pre-seeded content, no core call)
# ------------------------------------------------------------------


def test_get_email_content_db_hit(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """When email content is already in DB, it is returned without calling core."""
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # Seed email_content directly in the DB
    with isolated_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO email_content (provider_message_id, account_id, html_body, text_body)
            VALUES (%(pmid)s, %(aid)s::uuid, %(html)s, %(txt)s)
            ON CONFLICT (provider_message_id, account_id) DO UPDATE SET
                html_body = EXCLUDED.html_body, text_body = EXCLUDED.text_body
            """,
            {"pmid": "m1", "aid": aid, "html": "<p>cached</p>", "txt": "cached"},
        )

    resp = test_client.get(_content_url(mid, "m1", aid))
    assert resp.status_code == 200
    data = resp.json()
    assert data["html_body"] == "<p>cached</p>"
    assert data["text_body"] == "cached"


# ------------------------------------------------------------------
# Wrong user → 403
# ------------------------------------------------------------------


def test_get_email_content_wrong_user(
    test_client, setup_mailbox_and_account, isolated_db, app,
):
    """Accessing content on a mailbox owned by another user returns 403."""
    from api.routers.routers_helpers import require_session
    from tests.integration.conftest import TEST_USER_ID

    mid, aid = setup_mailbox_and_account(test_client)

    # Create a different user and override the session dependency
    other_user_id = str(uuid4())
    with isolated_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, google_sub, email, name)
            VALUES (%(uid)s, %(sub)s, %(email)s, %(name)s)
            """,
            {
                "uid": other_user_id,
                "sub": f"google-sub-{other_user_id}",
                "email": f"{other_user_id}@example.com",
                "name": "Other User",
            },
        )

    app.dependency_overrides[require_session] = lambda: other_user_id
    try:
        resp = test_client.get(_content_url(mid, "m1", aid))
        assert resp.status_code == 403
    finally:
        app.dependency_overrides[require_session] = lambda: TEST_USER_ID


# ------------------------------------------------------------------
# Missing account → 404
# ------------------------------------------------------------------


def test_get_email_content_missing_account(
    test_client, setup_mailbox_and_account,
):
    """Non-existent account_id returns 404."""
    mid, _ = setup_mailbox_and_account(test_client)
    fake_account_id = str(uuid4())
    resp = test_client.get(_content_url(mid, "m1", fake_account_id))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


# ------------------------------------------------------------------
# Missing mailbox → 404
# ------------------------------------------------------------------


def test_get_email_content_missing_mailbox(test_client):
    """Non-existent mailbox_id returns 404."""
    fake_mailbox_id = str(uuid4())
    fake_account_id = str(uuid4())
    resp = test_client.get(_content_url(fake_mailbox_id, "m1", fake_account_id))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


# ------------------------------------------------------------------
# Core error → 502
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "failing_test_client",
    [{"fetch_content_exc": EmailExternalAPIError("API timeout.")}],
    indirect=True,
)
def test_get_email_content_core_error_returns_502(
    failing_test_client, setup_mailbox_and_account,
):
    """CoreError during fetch_email_content is translated to 502."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    resp = failing_test_client.get(_content_url(mid, "m1", aid))
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


# ------------------------------------------------------------------
# Missing metadata row → 404 email_not_found
# ------------------------------------------------------------------


def test_get_email_content_missing_metadata_returns_404(
    test_client, setup_mailbox_and_account,
):
    """When the requested email has no metadata row, return 404 email_not_found."""
    mid, aid = setup_mailbox_and_account(test_client)
    # Intentionally skip sync-metadata so no metadata exists for this account.
    resp = test_client.get(_content_url(mid, "never-existed", aid))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "email_not_found"
