"""
E2E full-flow tests — real Gmail and Outlook APIs, no fakes.

Each test checks its own prerequisites via flow_state keys.
If a prerequisite is missing (because the producing test failed),
the dependent test is SKIPPED. Independent tests always run.

Run with: python -m pytest backend/tests/e2e -v --tb=short
"""

from __future__ import annotations

import os

import psycopg2
import pytest

from .e2e_config import (
    GMAIL_ACCOUNT_ID,
    GMAIL_MAILBOX_ID,
    OUTLOOK_ACCOUNT_ID,
    OUTLOOK_MAILBOX_ID,
    SEND_RECIPIENT,
    TEST_USER_ID,
)


def _assert_ok(response, *, expected: int = 200) -> None:
    assert response.status_code == expected, response.text


def _require(flow_state: dict, *keys: str) -> None:
    """Skip if any required flow_state keys are missing."""
    missing = [k for k in keys if k not in flow_state]
    if missing:
        pytest.skip(f"Prerequisites not met: {', '.join(missing)}")


def _db_conn():
    """Create a psycopg2 connection from DATABASE_URL."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    return psycopg2.connect(dsn=dsn)


def _fetch_email_ids(
    account_id: str, limit: int, box_filter: str = "ALL_MAIL",
) -> list[str]:
    """Fetch provider_message_ids from DB for the given account and box."""
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s AND box = %s LIMIT %s",
                (account_id, box_filter, limit),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def _count_by_box(account_id: str, box: str) -> int:
    """Count emails in a given box for an account."""
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM email_metadata "
                "WHERE account_id = %s AND box = %s",
                (account_id, box),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def _clear_sync_cursor(account_id: str) -> None:
    """Set sync_cursor to NULL so the next sync exercises Path 1 (bootstrap)."""
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE accounts SET sync_cursor = NULL WHERE account_id = %s",
                (account_id,),
            )
        conn.commit()
    finally:
        conn.close()


def _fetch_one_message_id(account_id: str) -> str | None:
    """Fetch a single provider_message_id for the account, or None."""
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s LIMIT 1",
                (account_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


# ===================================================================
# Section 1: Health
# ===================================================================

def test_01_health_check(e2e_client):
    response = e2e_client.get("/health")
    _assert_ok(response)
    assert response.json() == {"status": "ok"}


# ===================================================================
# Section 2: Auth read
# ===================================================================

def test_02_get_auth_me(e2e_client):
    response = e2e_client.get("/auth/me")
    _assert_ok(response)
    assert response.json()["user_id"] == TEST_USER_ID


# ===================================================================
# Section 3: CRUD (temp mailbox + accounts)
# ===================================================================

def test_03_create_mailbox(e2e_client, flow_state, created_resources):
    response = e2e_client.post("/mailboxes", json={"display_name": "E2E Temp Mailbox"})
    _assert_ok(response)
    data = response.json()
    assert data["display_name"] == "E2E Temp Mailbox"
    mid = data["mailbox_id"]
    flow_state["temp_mid"] = mid
    created_resources["mailbox_ids"].append(mid)


def test_04_create_gmail_account(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.post(
        f"/mailboxes/{flow_state['temp_mid']}/accounts",
        json={"provider": "gmail", "display_label": "e2e-gmail-temp"},
    )
    _assert_ok(response)
    flow_state["temp_gmail_id"] = response.json()["account_id"]


def test_05_create_outlook_account(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.post(
        f"/mailboxes/{flow_state['temp_mid']}/accounts",
        json={"provider": "outlook", "display_label": "e2e-outlook-temp"},
    )
    _assert_ok(response)
    flow_state["temp_outlook_id"] = response.json()["account_id"]


def test_06_list_mailboxes(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.get("/mailboxes")
    _assert_ok(response)
    ids = [m["mailbox_id"] for m in response.json()]
    assert flow_state["temp_mid"] in ids


def test_07_get_mailbox_detail(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.get(f"/mailboxes/{flow_state['temp_mid']}")
    _assert_ok(response)
    assert response.json()["mailbox_id"] == flow_state["temp_mid"]


def test_08_list_accounts(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.get(f"/mailboxes/{flow_state['temp_mid']}/accounts")
    _assert_ok(response)
    assert len(response.json()) >= 2


def test_09_get_gmail_account_detail(e2e_client, flow_state):
    _require(flow_state, "temp_gmail_id")
    response = e2e_client.get(
        f"/mailboxes/{flow_state['temp_mid']}/accounts/{flow_state['temp_gmail_id']}"
    )
    _assert_ok(response)
    assert response.json()["account_id"] == flow_state["temp_gmail_id"]


def test_10_get_outlook_account_detail(e2e_client, flow_state):
    _require(flow_state, "temp_outlook_id")
    response = e2e_client.get(
        f"/mailboxes/{flow_state['temp_mid']}/accounts/{flow_state['temp_outlook_id']}"
    )
    _assert_ok(response)
    assert response.json()["account_id"] == flow_state["temp_outlook_id"]


def test_11_patch_account_label(e2e_client, flow_state):
    _require(flow_state, "temp_gmail_id")
    response = e2e_client.patch(
        f"/mailboxes/{flow_state['temp_mid']}/accounts/{flow_state['temp_gmail_id']}",
        json={"display_label": "e2e-gmail-renamed"},
    )
    _assert_ok(response)
    assert response.json()["display_label"] == "e2e-gmail-renamed"


def test_12_delete_account(e2e_client, flow_state):
    _require(flow_state, "temp_outlook_id")
    response = e2e_client.delete(
        f"/mailboxes/{flow_state['temp_mid']}/accounts/{flow_state['temp_outlook_id']}"
    )
    _assert_ok(response)
    assert response.json() == {"status": "deleted"}


def test_13_delete_mailbox(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.delete(f"/mailboxes/{flow_state['temp_mid']}")
    _assert_ok(response)
    assert response.json() == {"status": "deleted"}
    flow_state["temp_mid_deleted"] = flow_state["temp_mid"]


def test_14_get_deleted_mailbox_404(e2e_client, flow_state):
    _require(flow_state, "temp_mid_deleted")
    response = e2e_client.get(f"/mailboxes/{flow_state['temp_mid_deleted']}")
    _assert_ok(response, expected=404)


# ===================================================================
# Section 4: Provider operations (pre-existing connected accounts)
# ===================================================================

def test_15_sync_metadata_gmail_path_1(e2e_client, flow_state):
    _clear_sync_cursor(GMAIL_ACCOUNT_ID)
    response = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata",
        params={"account_id": GMAIL_ACCOUNT_ID},
    )
    _assert_ok(response)
    data = response.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] >= 0
    accounts = data["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == GMAIL_ACCOUNT_ID
    assert accounts[0]["sync_cursor"] is not None
    flow_state["gmail_path1_done"] = "true"


def test_16_sync_metadata_outlook_path_1(e2e_client, flow_state):
    _clear_sync_cursor(OUTLOOK_ACCOUNT_ID)
    response = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/sync-metadata",
        params={"account_id": OUTLOOK_ACCOUNT_ID},
    )
    _assert_ok(response)
    data = response.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] >= 0
    accounts = data["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == OUTLOOK_ACCOUNT_ID
    assert accounts[0]["sync_cursor"] is not None
    flow_state["outlook_path1_done"] = "true"


def test_17_sync_metadata_gmail_path_2(e2e_client, flow_state):
    response = e2e_client.post(f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(response)
    data = response.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] >= 0
    accounts = data["accounts"]
    synced_ids = {a["account_id"] for a in accounts}
    assert GMAIL_ACCOUNT_ID in synced_ids
    gmail_account = next(a for a in accounts if a["account_id"] == GMAIL_ACCOUNT_ID)
    assert gmail_account["sync_cursor"] is not None


def test_18_sync_metadata_outlook_path_2(e2e_client, flow_state):
    response = e2e_client.post(f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(response)
    data = response.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] >= 0
    accounts = data["accounts"]
    synced_ids = {a["account_id"] for a in accounts}
    assert OUTLOOK_ACCOUNT_ID in synced_ids
    outlook_account = next(a for a in accounts if a["account_id"] == OUTLOOK_ACCOUNT_ID)
    assert outlook_account["sync_cursor"] is not None


def test_19_send_email_gmail(e2e_client):
    response = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/send",
        json={
            "account_id": GMAIL_ACCOUNT_ID,
            "subject": "E2E automated test — Gmail send",
            "body": "Automated E2E test email sent via Gmail.",
            "recipients": [SEND_RECIPIENT],
        },
    )
    _assert_ok(response)
    assert response.json()["status"] == "sent"


def test_20_send_email_outlook(e2e_client):
    response = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/send",
        json={
            "account_id": OUTLOOK_ACCOUNT_ID,
            "subject": "E2E automated test — Outlook send",
            "body": "Automated E2E test email sent via Outlook.",
            "recipients": [SEND_RECIPIENT],
        },
    )
    _assert_ok(response)
    assert response.json()["status"] == "sent"


def test_21_update_read_status_gmail(e2e_client, flow_state):
    """Sync metadata, pick a message, mark as read."""
    # Sync first to ensure email_metadata rows exist in DB for the test account
    sync_resp = e2e_client.post(f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(sync_resp)

    msg_id = _fetch_one_message_id(GMAIL_ACCOUNT_ID)
    if msg_id is None:
        pytest.skip("No synced emails found for Gmail test account")
    response = e2e_client.patch(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": GMAIL_ACCOUNT_ID, "provider_message_id": msg_id}],
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["updated_count"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == GMAIL_ACCOUNT_ID
    flow_state["gmail_read_status_done"] = "true"


def test_22_update_read_status_outlook(e2e_client, flow_state):
    """Sync metadata, pick a message, mark as unread."""
    # Sync first to ensure email_metadata rows exist in DB for the test account
    sync_resp = e2e_client.post(f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(sync_resp)

    msg_id = _fetch_one_message_id(OUTLOOK_ACCOUNT_ID)
    if msg_id is None:
        pytest.skip("No synced emails found for Outlook test account")
    response = e2e_client.patch(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/read-status",
        json={
            "is_read": False,
            "items": [{"account_id": OUTLOOK_ACCOUNT_ID, "provider_message_id": msg_id}],
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["updated_count"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == OUTLOOK_ACCOUNT_ID


# ===================================================================
# Section 4b: Spam operations (pre-existing connected accounts)
# ===================================================================

def test_23_move_to_spam_gmail(e2e_client, flow_state):
    """Sync, pick 10 emails, move to spam, verify DB."""
    sync_resp = e2e_client.post(f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(sync_resp)

    msg_ids = _fetch_email_ids(GMAIL_ACCOUNT_ID, 10, "ALL_MAIL")
    if len(msg_ids) < 10:
        pytest.skip("Not enough ALL_MAIL emails for Gmail spam test")

    spam_before = _count_by_box(GMAIL_ACCOUNT_ID, "SPAM")

    response = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/spam",
        json={
            "items": [
                {"account_id": GMAIL_ACCOUNT_ID, "provider_message_id": mid}
                for mid in msg_ids
            ],
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["moved_count"] == 10
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == GMAIL_ACCOUNT_ID
    assert data["accounts"][0]["moved"] == 10

    spam_after = _count_by_box(GMAIL_ACCOUNT_ID, "SPAM")
    assert spam_after == spam_before + 10

    flow_state["gmail_spam_done"] = "true"


def test_24_restore_from_spam_gmail(e2e_client, flow_state):
    """Pick 10 spam emails, restore, verify DB."""
    _require(flow_state, "gmail_spam_done")

    msg_ids = _fetch_email_ids(GMAIL_ACCOUNT_ID, 10, "SPAM")
    if len(msg_ids) < 10:
        pytest.skip("Not enough SPAM emails for Gmail restore test")

    spam_before = _count_by_box(GMAIL_ACCOUNT_ID, "SPAM")

    response = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/restore-from-spam",
        json={
            "items": [
                {"account_id": GMAIL_ACCOUNT_ID, "provider_message_id": mid}
                for mid in msg_ids
            ],
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["moved_count"] == 10
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == GMAIL_ACCOUNT_ID
    assert data["accounts"][0]["moved"] == 10

    spam_after = _count_by_box(GMAIL_ACCOUNT_ID, "SPAM")
    assert spam_after == spam_before - 10

    flow_state["gmail_restore_done"] = "true"


def test_25_move_to_spam_outlook(e2e_client, flow_state):
    """Sync, pick 10 emails, move to spam, verify DB."""
    sync_resp = e2e_client.post(f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(sync_resp)

    msg_ids = _fetch_email_ids(OUTLOOK_ACCOUNT_ID, 10, "ALL_MAIL")
    if len(msg_ids) < 10:
        pytest.skip("Not enough ALL_MAIL emails for Outlook spam test")

    spam_before = _count_by_box(OUTLOOK_ACCOUNT_ID, "SPAM")

    response = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/spam",
        json={
            "items": [
                {"account_id": OUTLOOK_ACCOUNT_ID, "provider_message_id": mid}
                for mid in msg_ids
            ],
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["moved_count"] == 10
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == OUTLOOK_ACCOUNT_ID
    assert data["accounts"][0]["moved"] == 10

    spam_after = _count_by_box(OUTLOOK_ACCOUNT_ID, "SPAM")
    assert spam_after == spam_before + 10

    flow_state["outlook_spam_done"] = "true"


def test_26_restore_from_spam_outlook(e2e_client, flow_state):
    """Pick 10 spam emails, restore, verify DB."""
    _require(flow_state, "outlook_spam_done")

    msg_ids = _fetch_email_ids(OUTLOOK_ACCOUNT_ID, 10, "SPAM")
    if len(msg_ids) < 10:
        pytest.skip("Not enough SPAM emails for Outlook restore test")

    spam_before = _count_by_box(OUTLOOK_ACCOUNT_ID, "SPAM")

    response = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/restore-from-spam",
        json={
            "items": [
                {"account_id": OUTLOOK_ACCOUNT_ID, "provider_message_id": mid}
                for mid in msg_ids
            ],
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["moved_count"] == 10
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == OUTLOOK_ACCOUNT_ID
    assert data["accounts"][0]["moved"] == 10

    spam_after = _count_by_box(OUTLOOK_ACCOUNT_ID, "SPAM")
    assert spam_after == spam_before - 10


# ===================================================================
# Section 5: Trash lifecycle (move to trash -> restore -> delete)
# ===================================================================

def test_27_move_to_trash(e2e_client, flow_state):
    """Sync both providers, pick 4 non-TRASH emails, move them to trash."""
    _require(flow_state, "gmail_path1_done", "outlook_path1_done")

    dsn = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s AND box NOT IN ('TRASH', 'DELETED') "
                "LIMIT 2",
                (GMAIL_ACCOUNT_ID,),
            )
            gmail_ids = [row[0] for row in cur.fetchall()]
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s AND box NOT IN ('TRASH', 'DELETED') "
                "LIMIT 2",
                (OUTLOOK_ACCOUNT_ID,),
            )
            outlook_ids = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    assert len(gmail_ids) >= 2, "Need at least 2 Gmail emails for trash lifecycle"
    assert len(outlook_ids) >= 2, "Need at least 2 Outlook emails for trash lifecycle"

    flow_state["trash_gmail_ids"] = gmail_ids
    flow_state["trash_outlook_ids"] = outlook_ids

    items = (
        [{"provider_message_id": mid, "account_id": GMAIL_ACCOUNT_ID} for mid in gmail_ids]
        + [{"provider_message_id": mid, "account_id": OUTLOOK_ACCOUNT_ID} for mid in outlook_ids]
    )

    # Gmail move-to-trash
    gmail_items = [i for i in items if i["account_id"] == GMAIL_ACCOUNT_ID]
    resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/move-to-trash",
        json={"items": gmail_items},
    )
    _assert_ok(resp)

    # Outlook move-to-trash
    outlook_items = [i for i in items if i["account_id"] == OUTLOOK_ACCOUNT_ID]
    resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/move-to-trash",
        json={"items": outlook_items},
    )
    _assert_ok(resp)

    # Verify DB state
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            # Gmail IDs don't change — verify by provider_message_id
            for mid in gmail_ids:
                cur.execute(
                    "SELECT box, previous_box FROM email_metadata "
                    "WHERE provider_message_id = %s AND account_id = %s",
                    (mid, GMAIL_ACCOUNT_ID),
                )
                row = cur.fetchone()
                assert row is not None, f"Gmail email {mid} not found"
                assert row[0] == "TRASH", f"Gmail email {mid} box should be TRASH, got {row[0]}"
                assert row[1] is not None, f"Gmail email {mid} previous_box should be set"

            # Outlook IDs may have changed — verify by account + TRASH box
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s AND box = 'TRASH' "
                "ORDER BY provider_message_id LIMIT %s",
                (OUTLOOK_ACCOUNT_ID, len(outlook_ids)),
            )
            new_outlook_ids = [row[0] for row in cur.fetchall()]
            assert len(new_outlook_ids) >= len(outlook_ids), (
                f"Expected at least {len(outlook_ids)} Outlook TRASH emails, got {len(new_outlook_ids)}"
            )
            flow_state["trash_outlook_ids"] = new_outlook_ids
    finally:
        conn.close()

    flow_state["move_to_trash_done"] = "true"


def test_28_restore_gmail_from_trash(e2e_client, flow_state):
    """Restore 1 Gmail email from trash — verify restored to original box."""
    _require(flow_state, "move_to_trash_done")
    gmail_id = flow_state["trash_gmail_ids"][0]

    resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": gmail_id, "account_id": GMAIL_ACCOUNT_ID}],
        },
    )
    _assert_ok(resp)
    assert resp.json()["affected"] == 1

    dsn = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT box, previous_box FROM email_metadata "
                "WHERE provider_message_id = %s AND account_id = %s",
                (gmail_id, GMAIL_ACCOUNT_ID),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] != "TRASH", f"Gmail email should be restored, got box={row[0]}"
            assert row[1] is None, "previous_box should be NULL after restore"
    finally:
        conn.close()

    flow_state["gmail_trash_restore_done"] = "true"


def test_29_delete_gmail_from_trash(e2e_client, flow_state):
    """Delete 1 Gmail email from trash — verify marked as DELETED."""
    _require(flow_state, "move_to_trash_done")
    gmail_id = flow_state["trash_gmail_ids"][1]

    resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/trash",
        json={
            "action": "delete",
            "items": [{"provider_message_id": gmail_id, "account_id": GMAIL_ACCOUNT_ID}],
        },
    )
    _assert_ok(resp)
    assert resp.json()["affected"] == 1

    dsn = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT box FROM email_metadata "
                "WHERE provider_message_id = %s AND account_id = %s",
                (gmail_id, GMAIL_ACCOUNT_ID),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "DELETED"
    finally:
        conn.close()

    flow_state["gmail_delete_done"] = "true"


def test_30_delete_outlook_from_trash(e2e_client, flow_state):
    """Delete 1 Outlook email from trash — verify marked as DELETED."""
    _require(flow_state, "move_to_trash_done")
    outlook_id = flow_state["trash_outlook_ids"][0]

    resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/trash",
        json={
            "action": "delete",
            "items": [{"provider_message_id": outlook_id, "account_id": OUTLOOK_ACCOUNT_ID}],
        },
    )
    _assert_ok(resp)
    assert resp.json()["affected"] == 1

    dsn = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT box FROM email_metadata "
                "WHERE provider_message_id = %s AND account_id = %s",
                (outlook_id, OUTLOOK_ACCOUNT_ID),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "DELETED"
    finally:
        conn.close()

    flow_state["outlook_delete_done"] = "true"


def test_31_restore_outlook_from_trash(e2e_client, flow_state):
    """Restore 1 Outlook email from trash — verify restored + provider_message_id updated."""
    _require(flow_state, "move_to_trash_done")
    outlook_id = flow_state["trash_outlook_ids"][1]

    resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": outlook_id, "account_id": OUTLOOK_ACCOUNT_ID}],
        },
    )
    _assert_ok(resp)
    assert resp.json()["affected"] == 1

    dsn = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            # Outlook restore changes the provider_message_id, so the old one should be gone
            cur.execute(
                "SELECT box, previous_box FROM email_metadata "
                "WHERE provider_message_id = %s AND account_id = %s",
                (outlook_id, OUTLOOK_ACCOUNT_ID),
            )
            old_row = cur.fetchone()
            # Check if the old ID was replaced (Outlook changes ID on move)
            # or if it stayed the same
            if old_row is not None:
                # ID stayed the same (some moves don't change ID)
                assert old_row[0] != "TRASH", f"Should be restored, got {old_row[0]}"
                assert old_row[1] is None, "previous_box should be NULL after restore"
            else:
                # ID changed — find the new record by checking for non-TRASH entries
                # that were recently restored (previous_box is NULL after restore)
                cur.execute(
                    "SELECT provider_message_id, box FROM email_metadata "
                    "WHERE account_id = %s AND box NOT IN ('TRASH', 'DELETED') "
                    "AND previous_box IS NULL",
                    (OUTLOOK_ACCOUNT_ID,),
                )
                rows = cur.fetchall()
                assert len(rows) > 0, "Should find at least one restored email"
    finally:
        conn.close()

    flow_state["outlook_restore_done"] = "true"


# ===================================================================
# Section 6: Auth lifecycle (MUST BE LAST — invalidates session)
# ===================================================================

def test_32_post_auth_logout(e2e_client, flow_state):
    response = e2e_client.post("/auth/logout")
    _assert_ok(response)
    assert response.json() == {"status": "logged_out"}
    flow_state["logged_out"] = "true"


def test_33_get_auth_me_after_logout_401(e2e_client, flow_state):
    _require(flow_state, "logged_out")
    response = e2e_client.get("/auth/me")
    _assert_ok(response, expected=401)
