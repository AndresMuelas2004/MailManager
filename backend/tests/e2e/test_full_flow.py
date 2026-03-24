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
    flow_state["gmail_path1_done"] = "true"


def test_16_sync_metadata_outlook_path_1(e2e_client, flow_state):
    _clear_sync_cursor(OUTLOOK_ACCOUNT_ID)
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
    flow_state["outlook_path1_done"] = "true"


def test_17_sync_metadata_gmail_path_2(e2e_client, flow_state):
    _require(flow_state, "gmail_path1_done")
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
    _require(flow_state, "outlook_path1_done")
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
# Section 5: Auth lifecycle (MUST BE LAST — invalidates session)
# ===================================================================

def test_27_post_auth_logout(e2e_client, flow_state):
    response = e2e_client.post("/auth/logout")
    _assert_ok(response)
    assert response.json() == {"status": "logged_out"}
    flow_state["logged_out"] = "true"


def test_28_get_auth_me_after_logout_401(e2e_client, flow_state):
    _require(flow_state, "logged_out")
    response = e2e_client.get("/auth/me")
    _assert_ok(response, expected=401)
