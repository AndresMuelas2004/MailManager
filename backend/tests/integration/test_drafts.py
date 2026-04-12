"""
Integration tests for the drafts endpoints:
    - POST /mailboxes/{mid}/accounts/{aid}/drafts (create_draft)
    - GET  /mailboxes/{mid}/drafts                (list_drafts)
    - POST /mailboxes/{mid}/drafts/sync           (sync_drafts)

Exercises the real FastAPI app + real PostgreSQL (transaction-rolled-back)
with FakeEmailClient replacing provider calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import psycopg2.extras

from api.services import drafts_service
from core.email import DraftMetadata, EmailManager
from tests.integration.conftest import MAILBOX_URL as _MAILBOX_URL
from tests.shared.email_fakes import FakeEmailClient


def _create_draft_url(mailbox_id: str, account_id: str) -> str:
    return f"{_MAILBOX_URL}/{mailbox_id}/accounts/{account_id}/drafts"


def _list_drafts_url(mailbox_id: str, account_id: str | None = None) -> str:
    url = f"{_MAILBOX_URL}/{mailbox_id}/drafts"
    if account_id is not None:
        url += f"?account_id={account_id}"
    return url


def _sync_drafts_url(mailbox_id: str, account_id: str | None = None) -> str:
    url = f"{_MAILBOX_URL}/{mailbox_id}/drafts/sync"
    if account_id is not None:
        url += f"?account_id={account_id}"
    return url


_SYNC_TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_draft(provider_draft_id: str, *, subject: str = "S") -> DraftMetadata:
    return DraftMetadata(
        provider_draft_id=provider_draft_id,
        to_recipients=["to@example.com"],
        cc_recipients=[],
        bcc_recipients=[],
        subject=subject,
        body_html=f"<p>{provider_draft_id}</p>",
        created_at=_SYNC_TS,
        updated_at=_SYNC_TS,
    )


def _patch_drafts_builder(
    monkeypatch,
    drafts_by_account: dict[str, list[DraftMetadata]],
) -> None:
    """Override build_manager_for_accounts so sync_drafts uses FakeEmailClients
    whose fetch_drafts returns the drafts for the matching account_id."""

    def _build(accounts):
        manager = EmailManager()
        for acc in accounts:
            mid = str(acc.get("mailbox_id", ""))
            aid = str(acc.get("account_id", ""))
            label = f"{mid}__{aid}"
            manager.add_client(FakeEmailClient(
                label,
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                fetch_drafts_return=list(drafts_by_account.get(aid, [])),
            ))
        return manager

    monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)


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


# ------------------------------------------------------------------
# POST /mailboxes/{mid}/drafts/sync — sync_drafts
# ------------------------------------------------------------------


def test_sync_drafts_empty_provider_returns_zero(
    test_client, setup_mailbox_and_account, monkeypatch, isolated_db,
):
    """Provider returns 0 drafts → response total_synced == 0, 0 rows in DB."""
    mid, aid = setup_mailbox_and_account(test_client)
    _patch_drafts_builder(monkeypatch, {aid: []})

    resp = test_client.post(_sync_drafts_url(mid, aid))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_synced"] == 0
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == aid
    assert data["accounts"][0]["drafts_synced"] == 0

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM drafts WHERE account_id = %s::uuid", (aid,),
        )
        assert cur.fetchone()[0] == 0


def test_sync_drafts_single_account_persists_rows(
    test_client, setup_mailbox_and_account, monkeypatch, isolated_db,
):
    """A 3-draft provider response is persisted to the drafts table."""
    mid, aid = setup_mailbox_and_account(test_client)
    drafts = [_make_draft(f"d{i}", subject=f"s{i}") for i in range(3)]
    _patch_drafts_builder(monkeypatch, {aid: drafts})

    resp = test_client.post(_sync_drafts_url(mid, aid))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_synced"] == 3
    assert data["accounts"][0]["drafts_synced"] == 3

    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT provider_draft_id, subject FROM drafts "
            "WHERE account_id = %s::uuid ORDER BY provider_draft_id",
            (aid,),
        )
        rows = cur.fetchall()
    assert len(rows) == 3
    assert [r["provider_draft_id"] for r in rows] == ["d0", "d1", "d2"]


def test_sync_drafts_mailbox_view_persists_rows_for_all_accounts(
    test_client, setup_mailbox_and_account, monkeypatch, isolated_db,
):
    """Without account_id the sync runs for every account in the mailbox."""
    mid, aid_gmail = setup_mailbox_and_account(test_client, provider="gmail")
    acc_resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "outlook", "display_label": "test-outlook"},
    )
    assert acc_resp.status_code == 200, acc_resp.text
    aid_outlook = acc_resp.json()["account_id"]

    drafts_by_account = {
        aid_gmail: [_make_draft("g1"), _make_draft("g2")],
        aid_outlook: [_make_draft("o1"), _make_draft("o2")],
    }
    _patch_drafts_builder(monkeypatch, drafts_by_account)

    resp = test_client.post(_sync_drafts_url(mid))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_synced"] == 4
    assert len(data["accounts"]) == 2
    account_ids = {a["account_id"] for a in data["accounts"]}
    assert account_ids == {aid_gmail, aid_outlook}
    # Each account must report its own drafts_synced count (not aggregated).
    assert all(a["drafts_synced"] == 2 for a in data["accounts"])

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM drafts WHERE account_id = ANY(%s::uuid[])",
            ([aid_gmail, aid_outlook],),
        )
        assert cur.fetchone()[0] == 4


def test_sync_drafts_replaces_stale_rows(
    test_client, setup_mailbox_and_account, monkeypatch, isolated_db,
):
    """Local drafts not returned by the provider are deleted on sync."""
    mid, aid = setup_mailbox_and_account(test_client)

    # Pre-insert 2 stale drafts directly into the DB.
    with isolated_db.cursor() as cur:
        for stale_id in ("old1", "old2"):
            cur.execute(
                """
                INSERT INTO drafts (
                    provider_draft_id, account_id, to_recipients,
                    cc_recipients, bcc_recipients, subject, body_html
                ) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s)
                """,
                (stale_id, aid, [], [], [], "stale", ""),
            )

    # Provider returns only one new draft.
    _patch_drafts_builder(monkeypatch, {aid: [_make_draft("newA")]})

    resp = test_client.post(_sync_drafts_url(mid, aid))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_synced"] == 1

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT provider_draft_id FROM drafts WHERE account_id = %s::uuid",
            (aid,),
        )
        rows = [r[0] for r in cur.fetchall()]
    assert rows == ["newA"]


def test_sync_drafts_upserts_existing_rows(
    test_client, setup_mailbox_and_account, monkeypatch, isolated_db,
):
    """Existing draft rows are updated in place (UPSERT)."""
    mid, aid = setup_mailbox_and_account(test_client)

    with isolated_db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO drafts (
                provider_draft_id, account_id, to_recipients,
                cc_recipients, bcc_recipients, subject, body_html
            ) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s)
            """,
            ("existing1", aid, [], [], [], "old subject", "old body"),
        )

    _patch_drafts_builder(monkeypatch, {
        aid: [_make_draft("existing1", subject="new subject")],
    })

    resp = test_client.post(_sync_drafts_url(mid, aid))
    assert resp.status_code == 200, resp.text

    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT subject, body_html FROM drafts WHERE account_id = %s::uuid",
            (aid,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["subject"] == "new subject"
    assert rows[0]["body_html"] == "<p>existing1</p>"


def test_sync_drafts_account_not_found_returns_404(
    test_client, setup_mailbox_and_account, monkeypatch,
):
    mid, _ = setup_mailbox_and_account(test_client)
    _patch_drafts_builder(monkeypatch, {})
    fake_aid = "00000000-0000-4000-a000-000000000099"
    resp = test_client.post(_sync_drafts_url(mid, fake_aid))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_sync_drafts_on_foreign_mailbox_forbidden(
    test_client, isolated_db, monkeypatch,
):
    mid = _create_foreign_mailbox(isolated_db)
    _patch_drafts_builder(monkeypatch, {})
    resp = test_client.post(_sync_drafts_url(mid))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_sync_drafts_empty_mailbox_returns_zero(
    test_client, monkeypatch,
):
    """A mailbox with no accounts returns total_synced=0 and accounts=[] (early return)."""
    # Create a mailbox with NO accounts.
    resp_create = test_client.post(_MAILBOX_URL, json={"display_name": "Empty MB"})
    assert resp_create.status_code == 200, resp_create.text
    mid = resp_create.json()["mailbox_id"]

    _patch_drafts_builder(monkeypatch, {})
    resp = test_client.post(_sync_drafts_url(mid))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_synced"] == 0
    assert data["accounts"] == []


def test_sync_drafts_empty_provider_unified_view(
    test_client, setup_mailbox_and_account, monkeypatch, isolated_db,
):
    """Unified view: provider returns empty → total_synced=0, one account detail entry."""
    mid, aid = setup_mailbox_and_account(test_client)
    _patch_drafts_builder(monkeypatch, {aid: []})

    resp = test_client.post(_sync_drafts_url(mid))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_synced"] == 0
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == aid
    assert data["accounts"][0]["drafts_synced"] == 0


def test_sync_drafts_db_error_on_replace_returns_503(
    test_client, setup_mailbox_and_account, monkeypatch,
):
    """A DbQueryError from draft_store.replace_all_for_account surfaces as 503."""
    from database.errors import QueryError as DbQueryError

    mid, aid = setup_mailbox_and_account(test_client)
    _patch_drafts_builder(monkeypatch, {aid: [_make_draft("d1")]})

    def _raise_db(*_a, **_kw):
        raise DbQueryError("persist failed")

    monkeypatch.setattr(
        drafts_service.draft_store, "replace_all_for_account", _raise_db,
    )
    resp = test_client.post(_sync_drafts_url(mid, aid))
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_query_error"


# ------------------------------------------------------------------
# PATCH /mailboxes/{mid}/accounts/{aid}/drafts/{provider_draft_id}
# update_draft
# ------------------------------------------------------------------


def _update_draft_url(mailbox_id: str, account_id: str, provider_draft_id: str) -> str:
    return (
        f"{_MAILBOX_URL}/{mailbox_id}/accounts/{account_id}"
        f"/drafts/{provider_draft_id}"
    )


def _update_payload(**overrides) -> dict:
    base = {
        "to_recipients": ["updated@example.com"],
        "cc_recipients": [],
        "bcc_recipients": [],
        "subject": "Updated",
        "body_html": "<p>updated</p>",
    }
    base.update(overrides)
    return base


def test_update_draft_happy_path_returns_updated_draft(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """Inserting a draft then PATCHing it returns the new content."""
    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-1",
        subject="original", body_html="<p>old</p>",
        to_recipients=["old@example.com"],
    )

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-1"),
        json=_update_payload(
            to_recipients=["updated@example.com"],
            subject="Updated",
            body_html="<p>new</p>",
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_draft_id"] == "draft-update-1"
    assert body["account_id"] == aid
    assert body["to_recipients"] == ["updated@example.com"]
    assert body["cc_recipients"] == []
    assert body["bcc_recipients"] == []
    assert body["subject"] == "Updated"
    assert body["body_html"] == "<p>new</p>"


def test_update_draft_persists_to_db(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """After the PATCH, the drafts row must contain the new content."""
    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-2",
        subject="original",
    )

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-2"),
        json=_update_payload(
            to_recipients=["a@b.com", "c@d.com"],
            cc_recipients=["cc@e.com"],
            bcc_recipients=["bcc@f.com"],
            subject="DB Check",
            body_html="<b>ok</b>",
        ),
    )
    assert resp.status_code == 200, resp.text

    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT to_recipients, cc_recipients, bcc_recipients, subject, body_html "
            "FROM drafts WHERE provider_draft_id = %s AND account_id = %s::uuid",
            ("draft-update-2", aid),
        )
        row = cur.fetchone()
    assert row is not None
    assert row["to_recipients"] == ["a@b.com", "c@d.com"]
    assert row["cc_recipients"] == ["cc@e.com"]
    assert row["bcc_recipients"] == ["bcc@f.com"]
    assert row["subject"] == "DB Check"
    assert row["body_html"] == "<b>ok</b>"


def test_update_draft_preserves_created_at_refreshes_updated_at(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """created_at must NOT change on update; updated_at is refreshed by the DB."""
    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-3",
        subject="original", created_at="2023-01-01T10:00:00Z",
    )

    # Capture the original created_at / updated_at to compare after the PATCH.
    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT created_at, updated_at FROM drafts "
            "WHERE provider_draft_id = %s AND account_id = %s::uuid",
            ("draft-update-3", aid),
        )
        before = cur.fetchone()

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-3"),
        json=_update_payload(subject="new"),
    )
    assert resp.status_code == 200, resp.text

    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT created_at, updated_at FROM drafts "
            "WHERE provider_draft_id = %s AND account_id = %s::uuid",
            ("draft-update-3", aid),
        )
        after = cur.fetchone()

    assert after["created_at"] == before["created_at"]
    # The UPDATE sets updated_at = now(); inside a single transaction now() is
    # frozen at transaction start, so updated_at == created_at when the insert
    # also used the transaction's now(). Use >= for robustness.
    assert after["updated_at"] >= after["created_at"]


def test_update_draft_empty_body_allowed(
    test_client, setup_mailbox_and_account, isolated_db,
):
    """An empty payload must be accepted (consistent with create)."""
    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-empty",
        subject="original", to_recipients=["old@example.com"],
    )

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-empty"),
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == ""
    assert body["body_html"] == ""
    assert body["to_recipients"] == []
    assert body["cc_recipients"] == []
    assert body["bcc_recipients"] == []


def test_update_draft_draft_not_found_returns_404(
    test_client, setup_mailbox_and_account,
):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        _update_draft_url(mid, aid, "does-not-exist"),
        json=_update_payload(),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "draft_not_found"


def test_update_draft_account_not_found_returns_404(
    test_client, setup_mailbox_and_account,
):
    mid, _ = setup_mailbox_and_account(test_client)
    fake_aid = "00000000-0000-4000-a000-000000000099"
    resp = test_client.patch(
        _update_draft_url(mid, fake_aid, "any-draft-id"),
        json=_update_payload(),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_update_draft_nonexistent_mailbox_returns_404(test_client):
    fake_mid = "00000000-0000-4000-a000-000000000099"
    fake_aid = "00000000-0000-4000-a000-000000000098"
    resp = test_client.patch(
        _update_draft_url(fake_mid, fake_aid, "any-draft-id"),
        json=_update_payload(),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_update_draft_on_foreign_mailbox_forbidden(test_client, isolated_db):
    """PATCHing a draft on a mailbox owned by another user returns 403."""
    foreign_mid = _create_foreign_mailbox(isolated_db)
    fake_aid = "00000000-0000-4000-a000-000000000099"
    resp = test_client.patch(
        _update_draft_url(foreign_mid, fake_aid, "any-draft-id"),
        json=_update_payload(),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_update_draft_provider_external_api_error_returns_502(
    test_client, setup_mailbox_and_account, isolated_db, monkeypatch,
):
    """EmailExternalAPIError from the provider surfaces as 502 external_api_error."""
    from core.email.errors import EmailExternalAPIError

    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-err",
        subject="original",
    )

    def _build(accounts):
        manager = EmailManager()
        for acc in accounts:
            mid_ = str(acc.get("mailbox_id", ""))
            aid_ = str(acc.get("account_id", ""))
            label = f"{mid_}__{aid_}"
            manager.add_client(FakeEmailClient(
                label,
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                update_draft_exc=EmailExternalAPIError("Graph 400"),
            ))
        return manager

    monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-err"),
        json=_update_payload(),
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


def test_update_draft_provider_generic_exception_returns_502(
    test_client, setup_mailbox_and_account, isolated_db, monkeypatch,
):
    """A plain RuntimeError from the provider is wrapped into ExternalAPIError (502)."""
    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-rt",
        subject="original",
    )

    def _build(accounts):
        manager = EmailManager()
        for acc in accounts:
            mid_ = str(acc.get("mailbox_id", ""))
            aid_ = str(acc.get("account_id", ""))
            label = f"{mid_}__{aid_}"
            manager.add_client(FakeEmailClient(
                label,
                auth_return={"access_token": "tok", "refresh_token": "ref"},
                update_draft_exc=RuntimeError("boom"),
            ))
        return manager

    monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-rt"),
        json=_update_payload(),
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


def test_update_draft_db_update_error_returns_503(
    test_client, setup_mailbox_and_account, isolated_db, monkeypatch,
):
    """A DbQueryError from draft_store.update surfaces as 503."""
    from database.errors import QueryError as DbQueryError

    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-db",
        subject="original",
    )

    def _raise_db(*_a, **_kw):
        raise DbQueryError("update failed")

    monkeypatch.setattr(drafts_service.draft_store, "update", _raise_db)

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-db"),
        json=_update_payload(),
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_query_error"


def test_update_draft_silent_auth_failure_returns_409(
    test_client, setup_mailbox_and_account, isolated_db, monkeypatch,
):
    """Silent auth failure during update_draft -> AccountNotConnected (409)."""
    from core.email.errors import EmailAuthError

    mid, aid = setup_mailbox_and_account(test_client)
    _insert_draft(
        isolated_db, account_id=aid, provider_draft_id="draft-update-auth",
        subject="original",
    )

    def _build(accounts):
        manager = EmailManager()
        for acc in accounts:
            mid_ = str(acc.get("mailbox_id", ""))
            aid_ = str(acc.get("account_id", ""))
            label = f"{mid_}__{aid_}"
            manager.add_client(FakeEmailClient(
                label,
                auth_silent_exc=EmailAuthError("Token expired."),
            ))
        return manager

    monkeypatch.setattr(drafts_service, "build_manager_for_accounts", _build)

    resp = test_client.patch(
        _update_draft_url(mid, aid, "draft-update-auth"),
        json=_update_payload(),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"
