"""
Integration tests for the POST /mailboxes/{mid}/accounts/{aid}/drafts endpoint.

Exercises the real FastAPI app + real PostgreSQL (transaction-rolled-back)
with FakeEmailClient replacing provider calls.
"""

from __future__ import annotations

import psycopg2.extras

from tests.integration.conftest import MAILBOX_URL as _MAILBOX_URL


def _create_draft_url(mailbox_id: str, account_id: str) -> str:
    return f"{_MAILBOX_URL}/{mailbox_id}/accounts/{account_id}/drafts"


def test_create_draft_happy_path_returns_draft(
    test_client, setup_mailbox_and_account,
):
    """A POST returns the created draft with provider_draft_id and the same payload fields."""
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        _create_draft_url(mid, aid),
        json={
            "to_recipients": ["to@example.com"],
            "cc_recipients": ["cc@example.com"],
            "bcc_recipients": [],
            "subject": "Integration draft",
            "body_html": "<p>Hi</p>",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_draft_id"] == "fake_draft_1"
    assert body["account_id"] == aid
    assert body["to_recipients"] == ["to@example.com"]
    assert body["cc_recipients"] == ["cc@example.com"]
    assert body["bcc_recipients"] == []
    assert body["subject"] == "Integration draft"
    assert body["body_html"] == "<p>Hi</p>"
    assert "created_at" in body
    assert "updated_at" in body


def test_create_draft_persists_to_db(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """The new draft must be queryable in the drafts table after the POST."""
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        _create_draft_url(mid, aid),
        json={
            "to_recipients": ["a@b.com"],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": "DB Check",
            "body_html": "<b>ok</b>",
        },
    )
    assert resp.status_code == 200, resp.text

    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT provider_draft_id, to_recipients, cc_recipients, bcc_recipients, "
            "subject, body_html FROM drafts WHERE account_id = %s::uuid",
            (aid,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["to_recipients"] == ["a@b.com"]
    assert row["cc_recipients"] == []
    assert row["bcc_recipients"] == []
    assert row["subject"] == "DB Check"
    assert row["body_html"] == "<b>ok</b>"


def test_create_empty_draft_allowed(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """An empty body must be accepted (empty drafts allowed) and persist defaults in DB."""
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(_create_draft_url(mid, aid), json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == ""
    assert body["body_html"] == ""
    assert body["to_recipients"] == []
    assert body["cc_recipients"] == []
    assert body["bcc_recipients"] == []

    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT subject, body_html, to_recipients, cc_recipients, bcc_recipients "
            "FROM drafts WHERE account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row["subject"] == ""
    assert row["body_html"] == ""
    assert row["to_recipients"] == []
    assert row["cc_recipients"] == []
    assert row["bcc_recipients"] == []


def test_create_draft_account_not_found(
    test_client, setup_mailbox_and_account,
):
    """Posting to a nonexistent account under an existing mailbox returns 404."""
    mid, _ = setup_mailbox_and_account(test_client)
    nonexistent_aid = "00000000-0000-4000-a000-000000000099"
    resp = test_client.post(
        _create_draft_url(mid, nonexistent_aid),
        json={"subject": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_create_draft_nonexistent_mailbox(test_client):
    """Posting to a nonexistent mailbox returns 404 (mailbox_not_found)."""
    fake_mid = "00000000-0000-4000-a000-000000000099"
    fake_aid = "00000000-0000-4000-a000-000000000098"
    resp = test_client.post(
        _create_draft_url(fake_mid, fake_aid),
        json={"subject": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"
