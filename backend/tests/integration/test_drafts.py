"""
Integration tests for the drafts endpoints:
    - POST /mailboxes/{mid}/accounts/{aid}/drafts (create_draft)
    - GET  /mailboxes/{mid}/drafts                (list_drafts)

Exercises the real FastAPI app + real PostgreSQL (transaction-rolled-back)
with FakeEmailClient replacing provider calls.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg2.extras

from tests.integration.conftest import MAILBOX_URL as _MAILBOX_URL


def _create_draft_url(mailbox_id: str, account_id: str) -> str:
    return f"{_MAILBOX_URL}/{mailbox_id}/accounts/{account_id}/drafts"


def _list_drafts_url(mailbox_id: str, account_id: str | None = None) -> str:
    url = f"{_MAILBOX_URL}/{mailbox_id}/drafts"
    if account_id is not None:
        url += f"?account_id={account_id}"
    return url


def _create_foreign_mailbox(isolated_db) -> str:
    """Create a mailbox owned by another user and return its ID."""
    other_user_id = str(uuid4())
    other_mailbox_id = str(uuid4())
    with isolated_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, google_sub, email)
            VALUES (%(user_id)s, %(google_sub)s, %(email)s)
            """,
            {
                "user_id": other_user_id,
                "google_sub": f"sub-{other_user_id[:8]}",
                "email": "other-drafts@e.com",
            },
        )
        cur.execute(
            """
            INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
            VALUES (%(mailbox_id)s, %(display_name)s, %(owner_user_id)s)
            """,
            {
                "mailbox_id": other_mailbox_id,
                "display_name": "Foreign Drafts",
                "owner_user_id": other_user_id,
            },
        )
    return other_mailbox_id


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


# ------------------------------------------------------------------
# GET /mailboxes/{mid}/drafts — list_drafts
# ------------------------------------------------------------------


def test_list_drafts_empty_returns_empty_list(
    test_client, setup_mailbox_and_account,
):
    """GET drafts on a fresh mailbox with no POSTs returns an empty list."""
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.get(_list_drafts_url(mid))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def _insert_draft(
    isolated_db,
    *,
    account_id: str,
    provider_draft_id: str,
    subject: str = "",
    body_html: str = "",
    to_recipients: list[str] | None = None,
    created_at: str | None = None,
) -> None:
    """Insert a draft row directly via SQL (bypasses the FakeEmailClient
    whose default create_draft_id collides across multiple POSTs).

    ``created_at`` can be passed as an ISO timestamp to force a specific
    ordering — inside the same transaction ``now()`` returns the same value
    for every row, so ordering tests must supply explicit timestamps.
    """
    if created_at is None:
        sql = """
            INSERT INTO drafts (
                provider_draft_id, account_id, to_recipients,
                cc_recipients, bcc_recipients, subject, body_html
            ) VALUES (
                %(pid)s, %(aid)s::uuid, %(tor)s,
                %(ccr)s, %(bccr)s, %(subj)s, %(body)s
            )
        """
    else:
        sql = """
            INSERT INTO drafts (
                provider_draft_id, account_id, to_recipients,
                cc_recipients, bcc_recipients, subject, body_html,
                created_at, updated_at
            ) VALUES (
                %(pid)s, %(aid)s::uuid, %(tor)s,
                %(ccr)s, %(bccr)s, %(subj)s, %(body)s,
                %(ts)s::timestamptz, %(ts)s::timestamptz
            )
        """
    with isolated_db.cursor() as cur:
        cur.execute(
            sql,
            {
                "pid": provider_draft_id,
                "aid": account_id,
                "tor": to_recipients or [],
                "ccr": [],
                "bccr": [],
                "subj": subject,
                "body": body_html,
                "ts": created_at,
            },
        )


def test_list_drafts_single_account_view(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """GET with account_id returns only that account's drafts, newest first."""
    mid, aid = setup_mailbox_and_account(test_client)
    # Insert drafts directly with explicit timestamps so the ORDER BY DESC
    # assertion is deterministic (within a single transaction now() returns
    # the same value for every row).
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="d1",
        subject="first", created_at="2024-01-01T10:00:00Z",
    )
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="d2",
        subject="second", created_at="2024-01-01T11:00:00Z",
    )
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="d3",
        subject="third", created_at="2024-01-01T12:00:00Z",
    )

    resp = test_client.get(_list_drafts_url(mid, aid))
    assert resp.status_code == 200, resp.text
    drafts = resp.json()
    assert len(drafts) == 3
    # All belong to the requested account.
    for d in drafts:
        assert d["account_id"] == aid
    # Ordered by created_at DESC — third (12:00) → second (11:00) → first (10:00).
    subjects = [d["subject"] for d in drafts]
    assert subjects == ["third", "second", "first"]


def test_list_drafts_unified_view(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """GET without account_id returns drafts from all accounts in the mailbox."""
    mid, aid_gmail = setup_mailbox_and_account(test_client, provider="gmail")
    # Create a second account in the same mailbox.
    acc_resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "outlook", "display_label": "test-outlook"},
    )
    assert acc_resp.status_code == 200, acc_resp.text
    aid_outlook = acc_resp.json()["account_id"]

    # Insert 2 drafts per account via SQL (avoids FakeEmailClient PK collision).
    _insert_draft(isolated_db, account_id=aid_gmail, provider_draft_id="g1", subject="gmail-1")
    _insert_draft(isolated_db, account_id=aid_gmail, provider_draft_id="g2", subject="gmail-2")
    _insert_draft(isolated_db, account_id=aid_outlook, provider_draft_id="o1", subject="outlook-1")
    _insert_draft(isolated_db, account_id=aid_outlook, provider_draft_id="o2", subject="outlook-2")

    resp = test_client.get(_list_drafts_url(mid))
    assert resp.status_code == 200, resp.text
    drafts = resp.json()
    assert len(drafts) == 4
    account_ids = {d["account_id"] for d in drafts}
    assert account_ids == {aid_gmail, aid_outlook}
    subjects = {d["subject"] for d in drafts}
    assert subjects == {"gmail-1", "gmail-2", "outlook-1", "outlook-2"}


def test_list_drafts_unified_view_ignores_other_mailboxes(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """A GET for mailbox A must not return drafts created in mailbox B."""
    mid_a, aid_a = setup_mailbox_and_account(test_client, provider="gmail")
    mid_b, aid_b = setup_mailbox_and_account(test_client, provider="gmail")

    _insert_draft(isolated_db, account_id=aid_a, provider_draft_id="a1", subject="for-a")
    _insert_draft(isolated_db, account_id=aid_b, provider_draft_id="b1", subject="for-b")

    resp_a = test_client.get(_list_drafts_url(mid_a))
    assert resp_a.status_code == 200
    drafts_a = resp_a.json()
    assert len(drafts_a) == 1
    assert drafts_a[0]["subject"] == "for-a"
    assert drafts_a[0]["account_id"] == aid_a

    resp_b = test_client.get(_list_drafts_url(mid_b))
    assert resp_b.status_code == 200
    drafts_b = resp_b.json()
    assert len(drafts_b) == 1
    assert drafts_b[0]["subject"] == "for-b"
    assert drafts_b[0]["account_id"] == aid_b


def test_list_drafts_nonexistent_mailbox_returns_404(test_client):
    fake_mid = "00000000-0000-4000-a000-000000000099"
    resp = test_client.get(_list_drafts_url(fake_mid))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_list_drafts_nonexistent_account_returns_404(
    test_client, setup_mailbox_and_account,
):
    mid, _ = setup_mailbox_and_account(test_client)
    fake_aid = "00000000-0000-4000-a000-000000000099"
    resp = test_client.get(_list_drafts_url(mid, fake_aid))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_list_drafts_on_foreign_mailbox_forbidden(test_client, isolated_db):
    """Listing drafts on a mailbox owned by another user returns 403."""
    mid = _create_foreign_mailbox(isolated_db)
    resp = test_client.get(_list_drafts_url(mid))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
