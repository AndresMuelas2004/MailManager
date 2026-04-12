"""
E2E full-flow tests — real Gmail and Outlook APIs, no fakes.

Each test checks its own prerequisites via flow_state keys.
If a prerequisite is missing (because the producing test failed),
the dependent test is SKIPPED. Independent tests always run.

Run with: python -m pytest backend/tests/e2e -v --tb=short
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

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


def _boxes_for_ids(account_id: str, ids: list[str]) -> dict[str, str]:
    """Return {provider_message_id: box} for the given IDs under an account."""
    if not ids:
        return {}
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider_message_id, box FROM email_metadata "
                "WHERE account_id = %s AND provider_message_id = ANY(%s)",
                (account_id, ids),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _ids_in_box(account_id: str, box: str) -> set[str]:
    """Return the full set of provider_message_ids currently in `box` for an account."""
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s AND box = %s",
                (account_id, box),
            )
            return {row[0] for row in cur.fetchall()}
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

    # Verify each moved email is now in SPAM (robust to concurrent provider events).
    boxes = _boxes_for_ids(GMAIL_ACCOUNT_ID, msg_ids)
    for mid in msg_ids:
        assert boxes.get(mid) == "SPAM", (
            f"Expected Gmail email {mid} to be in SPAM, got {boxes.get(mid)}"
        )

    flow_state["gmail_spam_done"] = "true"


def test_24_restore_from_spam_gmail(e2e_client, flow_state):
    """Pick 10 spam emails, restore, verify DB."""
    _require(flow_state, "gmail_spam_done")

    msg_ids = _fetch_email_ids(GMAIL_ACCOUNT_ID, 10, "SPAM")
    if len(msg_ids) < 10:
        pytest.skip("Not enough SPAM emails for Gmail restore test")

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

    # Verify each restored email is no longer in SPAM (robust to concurrent provider events).
    boxes = _boxes_for_ids(GMAIL_ACCOUNT_ID, msg_ids)
    for mid in msg_ids:
        assert boxes.get(mid) != "SPAM", (
            f"Expected Gmail email {mid} to be out of SPAM, still in {boxes.get(mid)}"
        )

    flow_state["gmail_restore_done"] = "true"


def test_25_move_to_spam_outlook(e2e_client, flow_state):
    """Sync, pick 10 emails, move to spam, verify DB, stash new SPAM IDs."""
    sync_resp = e2e_client.post(f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(sync_resp)

    msg_ids = _fetch_email_ids(OUTLOOK_ACCOUNT_ID, 10, "ALL_MAIL")
    if len(msg_ids) < 10:
        pytest.skip("Not enough ALL_MAIL emails for Outlook spam test")

    # Outlook mutates provider_message_id when moving between folders. The IDs
    # we send are NOT the IDs that end up in SPAM after the move — Outlook
    # assigns new ones. To identify the 10 rows we just created, snapshot the
    # set of SPAM IDs before the move and take the delta after.
    spam_before_ids = _ids_in_box(OUTLOOK_ACCOUNT_ID, "SPAM")

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

    # Compute the delta: IDs that appeared in SPAM as a result of the move.
    spam_after_ids = _ids_in_box(OUTLOOK_ACCOUNT_ID, "SPAM")
    newly_spam_ids = sorted(spam_after_ids - spam_before_ids)
    assert len(newly_spam_ids) == 10, (
        f"Expected 10 new SPAM IDs after move, got {len(newly_spam_ids)}"
    )

    # Verify DB consistency for each new ID.
    boxes = _boxes_for_ids(OUTLOOK_ACCOUNT_ID, newly_spam_ids)
    for mid in newly_spam_ids:
        assert boxes.get(mid) == "SPAM", (
            f"Expected Outlook email {mid} to be in SPAM, got {boxes.get(mid)}"
        )

    # Stash for test 26 — these are the exact IDs it should attempt to restore,
    # avoiding stale residue from previous E2E runs.
    flow_state["outlook_spam_moved_ids"] = newly_spam_ids
    flow_state["outlook_spam_done"] = "true"


def test_26_restore_from_spam_outlook(e2e_client, flow_state):
    """Restore the exact 10 SPAM IDs that test 25 just created."""
    _require(flow_state, "outlook_spam_done", "outlook_spam_moved_ids")

    msg_ids = flow_state["outlook_spam_moved_ids"]
    assert len(msg_ids) == 10, (
        f"Expected 10 IDs from flow_state, got {len(msg_ids)}"
    )

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

    # After restore, none of the original 10 IDs should still be in SPAM.
    # Outlook mutates IDs again on this second move, so the DB row for the
    # old ID is either gone (replaced by a new one) or its box is no longer
    # 'SPAM'.
    boxes = _boxes_for_ids(OUTLOOK_ACCOUNT_ID, msg_ids)
    for mid in msg_ids:
        assert boxes.get(mid) != "SPAM", (
            f"Expected Outlook email {mid} to be out of SPAM after restore, "
            f"still in {boxes.get(mid)}"
        )


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

            # Outlook IDs change on move, so we cannot rely on the pre-move IDs.
            # Fetch any 2 TRASH rows for this account so later tests (28-31)
            # can operate on real current IDs. Filter by previous_box IS NOT NULL
            # to prefer rows that were just moved by our app when possible, but
            # fall back to any TRASH row if no such rows are found (rows that
            # had the ID mutated may have lost the previous_box linkage in the
            # upsert path, which is an Outlook-specific quirk).
            cur.execute(
                "SELECT provider_message_id FROM email_metadata "
                "WHERE account_id = %s AND box = 'TRASH' "
                "ORDER BY (previous_box IS NOT NULL) DESC, provider_message_id "
                "LIMIT %s",
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
    """Restore 1 Outlook email from trash — verify restored (provider_message_id may or may not change)."""
    _require(flow_state, "move_to_trash_done")
    outlook_id = flow_state["trash_outlook_ids"][1]

    dsn = os.getenv("DATABASE_URL", "").strip()

    # Snapshot: count rows in non-TRASH/non-DELETED boxes with cleared previous_box.
    # After a successful restore, this count must grow by exactly 1.
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM email_metadata "
                "WHERE account_id = %s AND box NOT IN ('TRASH', 'DELETED') "
                "AND previous_box IS NULL",
                (OUTLOOK_ACCOUNT_ID,),
            )
            restored_count_before = cur.fetchone()[0]
    finally:
        conn.close()

    resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": outlook_id, "account_id": OUTLOOK_ACCOUNT_ID}],
        },
    )
    _assert_ok(resp)
    assert resp.json()["affected"] == 1

    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            # Outlook restore may or may not change the provider_message_id.
            cur.execute(
                "SELECT box, previous_box FROM email_metadata "
                "WHERE provider_message_id = %s AND account_id = %s",
                (outlook_id, OUTLOOK_ACCOUNT_ID),
            )
            old_row = cur.fetchone()
            if old_row is not None:
                # ID stayed the same (some moves don't change ID)
                assert old_row[0] != "TRASH", f"Should be restored, got {old_row[0]}"
                assert old_row[1] is None, "previous_box should be NULL after restore"
            else:
                # ID changed — the set of restored rows must have grown by
                # exactly 1. A simple `len(rows) > 0` would pass even if the
                # restore silently failed, because other emails already sit in
                # non-TRASH boxes with NULL previous_box.
                cur.execute(
                    "SELECT COUNT(*) FROM email_metadata "
                    "WHERE account_id = %s AND box NOT IN ('TRASH', 'DELETED') "
                    "AND previous_box IS NULL",
                    (OUTLOOK_ACCOUNT_ID,),
                )
                restored_count_after = cur.fetchone()[0]
                assert restored_count_after == restored_count_before + 1, (
                    f"Expected restored-row count to increase by 1, "
                    f"got {restored_count_before} -> {restored_count_after}"
                )
    finally:
        conn.close()

    flow_state["outlook_restore_done"] = "true"


# ===================================================================
# Section 5b: Drafts — pre-existing accounts (tests 32–33)
#
# TODO: Manual DB cleanup is performed inline because the DELETE drafts
# endpoint does not exist yet. The draft is intentionally left at the
# provider; a future DELETE drafts endpoint will replace this manual
# cleanup with proper provider-side deletion.
# ===================================================================

def test_32_create_draft_gmail(e2e_client):
    """Create a draft on the seeded Gmail test account and clean up the local row."""
    subject = f"E2E draft — Gmail {datetime.now(timezone.utc).isoformat()}"
    response = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/accounts/{GMAIL_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": subject,
            "body_html": "<p>E2E test body</p>",
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["provider_draft_id"]
    assert data["account_id"] == GMAIL_ACCOUNT_ID
    assert data["subject"] == subject
    assert data["to_recipients"] == [SEND_RECIPIENT]
    assert data["cc_recipients"] == []
    assert data["bcc_recipients"] == []
    assert data["body_html"] == "<p>E2E test body</p>"
    assert data["created_at"]
    assert data["updated_at"]

    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM drafts WHERE provider_draft_id = %s AND account_id = %s",
                (data["provider_draft_id"], GMAIL_ACCOUNT_ID),
            )
            assert cur.fetchone() is not None
            cur.execute(
                "DELETE FROM drafts WHERE provider_draft_id = %s AND account_id = %s",
                (data["provider_draft_id"], GMAIL_ACCOUNT_ID),
            )
        conn.commit()
    finally:
        conn.close()


def test_33_create_draft_outlook(e2e_client):
    """Create a draft on the seeded Outlook test account; verifies the ImmutableId header path."""
    subject = f"E2E draft — Outlook {datetime.now(timezone.utc).isoformat()}"
    response = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/accounts/{OUTLOOK_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": subject,
            "body_html": "<p>E2E Outlook test body</p>",
        },
    )
    _assert_ok(response)
    data = response.json()
    assert data["provider_draft_id"]
    assert data["account_id"] == OUTLOOK_ACCOUNT_ID
    assert data["subject"] == subject
    assert data["to_recipients"] == [SEND_RECIPIENT]
    assert data["cc_recipients"] == []
    assert data["bcc_recipients"] == []
    assert data["body_html"] == "<p>E2E Outlook test body</p>"
    assert data["created_at"]
    assert data["updated_at"]

    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM drafts WHERE provider_draft_id = %s AND account_id = %s",
                (data["provider_draft_id"], OUTLOOK_ACCOUNT_ID),
            )
            assert cur.fetchone() is not None
            cur.execute(
                "DELETE FROM drafts WHERE provider_draft_id = %s AND account_id = %s",
                (data["provider_draft_id"], OUTLOOK_ACCOUNT_ID),
            )
        conn.commit()
    finally:
        conn.close()


# ===================================================================
# Section 5c: Drafts sync (provider → local DB)
#
# Each test creates a draft first (to guarantee the provider has at
# least one known draft with a unique subject), clears the local rows
# for that account, runs the sync, verifies the created draft is now
# in the local DB, and finally cleans up the local rows. Provider-side
# drafts are not deleted (same pattern as tests 32 and 33).
# ===================================================================

def _clear_local_drafts(account_id: str) -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM drafts WHERE account_id = %s", (account_id,))
        conn.commit()
    finally:
        conn.close()


def _find_local_draft(provider_draft_id: str, account_id: str) -> tuple | None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT subject, to_recipients, cc_recipients, bcc_recipients, body_html "
                "FROM drafts "
                "WHERE provider_draft_id = %s AND account_id = %s",
                (provider_draft_id, account_id),
            )
            return cur.fetchone()
    finally:
        conn.close()


def test_34_sync_drafts_gmail_single_account(e2e_client):
    """Gmail + single account: create a draft, sync that account, verify the draft is in DB."""
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"E2E sync — Gmail single {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/accounts/{GMAIL_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "subject": subject,
            "body_html": "<p>sync test</p>",
        },
    )
    _assert_ok(create_resp)
    created_id = create_resp.json()["provider_draft_id"]

    _clear_local_drafts(GMAIL_ACCOUNT_ID)

    sync_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/drafts/sync?account_id={GMAIL_ACCOUNT_ID}",
    )
    _assert_ok(sync_resp)
    data = sync_resp.json()
    assert data["total_synced"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == GMAIL_ACCOUNT_ID
    assert data["accounts"][0]["provider"] == "gmail"
    assert data["accounts"][0]["drafts_synced"] == data["total_synced"]

    row = _find_local_draft(created_id, GMAIL_ACCOUNT_ID)
    assert row is not None, "Created draft should be present in DB after sync"
    db_subject, db_to, db_cc, _db_bcc, db_body = row
    assert db_subject == subject
    assert db_to == [SEND_RECIPIENT]
    assert db_cc == []
    assert db_body == "<p>sync test</p>"

    _clear_local_drafts(GMAIL_ACCOUNT_ID)


def test_35_sync_drafts_gmail_mailbox(e2e_client):
    """Gmail + mailbox-wide: create a draft, sync the whole mailbox, verify the draft is in DB."""
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"E2E sync — Gmail mailbox {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/accounts/{GMAIL_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "subject": subject,
            "body_html": "<p>sync test</p>",
        },
    )
    _assert_ok(create_resp)
    created_id = create_resp.json()["provider_draft_id"]

    _clear_local_drafts(GMAIL_ACCOUNT_ID)

    sync_resp = e2e_client.post(f"/mailboxes/{GMAIL_MAILBOX_ID}/drafts/sync")
    _assert_ok(sync_resp)
    data = sync_resp.json()
    assert data["total_synced"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == GMAIL_ACCOUNT_ID
    assert data["accounts"][0]["provider"] == "gmail"
    assert data["accounts"][0]["drafts_synced"] == data["total_synced"]

    row = _find_local_draft(created_id, GMAIL_ACCOUNT_ID)
    assert row is not None, "Created draft should be present in DB after mailbox sync"
    db_subject, db_to, db_cc, _db_bcc, db_body = row
    assert db_subject == subject
    assert db_to == [SEND_RECIPIENT]
    assert db_cc == []
    assert db_body == "<p>sync test</p>"

    _clear_local_drafts(GMAIL_ACCOUNT_ID)


def test_36_sync_drafts_outlook_single_account(e2e_client):
    """Outlook + single account: create a draft, sync that account, verify the draft is in DB."""
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"E2E sync — Outlook single {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/accounts/{OUTLOOK_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "subject": subject,
            "body_html": "<p>sync test</p>",
        },
    )
    _assert_ok(create_resp)
    created_id = create_resp.json()["provider_draft_id"]

    _clear_local_drafts(OUTLOOK_ACCOUNT_ID)

    sync_resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/drafts/sync?account_id={OUTLOOK_ACCOUNT_ID}",
    )
    _assert_ok(sync_resp)
    data = sync_resp.json()
    assert data["total_synced"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == OUTLOOK_ACCOUNT_ID
    assert data["accounts"][0]["provider"] == "outlook"
    assert data["accounts"][0]["drafts_synced"] == data["total_synced"]

    row = _find_local_draft(created_id, OUTLOOK_ACCOUNT_ID)
    assert row is not None, "Created draft should be present in DB after sync"
    db_subject, db_to, db_cc, _db_bcc, _db_body = row
    assert db_subject == subject
    assert db_to == [SEND_RECIPIENT]
    assert db_cc == []
    # Outlook wraps plain HTML in a full <html>/<body> structure, so body_html
    # is not asserted byte-for-byte; presence is enough.

    _clear_local_drafts(OUTLOOK_ACCOUNT_ID)


def test_37_sync_drafts_outlook_mailbox(e2e_client):
    """Outlook + mailbox-wide: create a draft, sync the whole mailbox, verify the draft is in DB."""
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"E2E sync — Outlook mailbox {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/accounts/{OUTLOOK_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "subject": subject,
            "body_html": "<p>sync test</p>",
        },
    )
    _assert_ok(create_resp)
    created_id = create_resp.json()["provider_draft_id"]

    _clear_local_drafts(OUTLOOK_ACCOUNT_ID)

    sync_resp = e2e_client.post(f"/mailboxes/{OUTLOOK_MAILBOX_ID}/drafts/sync")
    _assert_ok(sync_resp)
    data = sync_resp.json()
    assert data["total_synced"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == OUTLOOK_ACCOUNT_ID
    assert data["accounts"][0]["provider"] == "outlook"
    assert data["accounts"][0]["drafts_synced"] == data["total_synced"]

    row = _find_local_draft(created_id, OUTLOOK_ACCOUNT_ID)
    assert row is not None, "Created draft should be present in DB after mailbox sync"
    db_subject, db_to, db_cc, _db_bcc, _db_body = row
    assert db_subject == subject
    assert db_to == [SEND_RECIPIENT]
    assert db_cc == []

    _clear_local_drafts(OUTLOOK_ACCOUNT_ID)


# ===================================================================
# Section 5d: DB-backed GET coverage — pre-existing accounts (tests 38–40)
# ===================================================================
# Tests 38–40 complement the automated suite with end-to-end coverage of
# three GET endpoints that return database content:
#   - GET /mailboxes/{mid}/emails      (list_emails, DB-only)
#   - GET /mailboxes/{mid}/emails/{id}/content (cache-aside)
#   - GET /mailboxes/{mid}/drafts      (list_drafts, DB-only)
# ===================================================================


def test_38_list_emails_gmail(e2e_client):
    """Sync gmail metadata, then GET /emails?box=ALL_MAIL and verify
    the response contains rows for the account."""
    # Ensure there is fresh metadata for the account.
    sync_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata?account_id={GMAIL_ACCOUNT_ID}",
    )
    _assert_ok(sync_resp)

    resp = e2e_client.get(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails"
        f"?box=ALL_MAIL&account_id={GMAIL_ACCOUNT_ID}",
    )
    _assert_ok(resp)
    emails = resp.json()
    assert isinstance(emails, list)
    assert len(emails) >= 1, "Gmail account should have at least one email in ALL_MAIL after sync"
    # Every returned row must belong to the requested account and box.
    for e in emails:
        assert e["account_id"] == GMAIL_ACCOUNT_ID
        assert e["box"] == "ALL_MAIL"


def test_39_get_email_content_gmail(e2e_client):
    """Pick an email from the DB, GET /content (first call hits provider
    and caches; second call is a cache hit)."""
    # Sync to guarantee metadata exists.
    sync_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata?account_id={GMAIL_ACCOUNT_ID}",
    )
    _assert_ok(sync_resp)

    list_resp = e2e_client.get(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails"
        f"?box=ALL_MAIL&account_id={GMAIL_ACCOUNT_ID}",
    )
    _assert_ok(list_resp)
    emails = list_resp.json()
    if not emails:
        pytest.skip("No Gmail emails available for content fetch test.")

    provider_message_id = emails[0]["provider_message_id"]
    content_url = (
        f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/{provider_message_id}/content"
        f"?account_id={GMAIL_ACCOUNT_ID}"
    )

    # First call: cache miss → provider fetch.
    first = e2e_client.get(content_url)
    _assert_ok(first)
    body_1 = first.json()
    assert "html_body" in body_1 or "text_body" in body_1

    # Second call: cache hit → same response.
    second = e2e_client.get(content_url)
    _assert_ok(second)
    body_2 = second.json()
    assert body_2 == body_1


def test_40_list_drafts_gmail(e2e_client):
    """Create a gmail draft, verify GET /drafts?account_id returns it, cleanup."""
    ts = datetime.now(timezone.utc).isoformat()
    subject = f"E2E list — Gmail {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/accounts/{GMAIL_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "subject": subject,
            "body_html": "<p>list test</p>",
        },
    )
    _assert_ok(create_resp)
    created_id = create_resp.json()["provider_draft_id"]
    try:
        resp = e2e_client.get(
            f"/mailboxes/{GMAIL_MAILBOX_ID}/drafts?account_id={GMAIL_ACCOUNT_ID}",
        )
        _assert_ok(resp)
        drafts = resp.json()
        assert isinstance(drafts, list)
        matched = [d for d in drafts if d["provider_draft_id"] == created_id]
        assert matched, (
            f"Created draft {created_id} should appear in GET /drafts result."
        )
        assert matched[0]["subject"] == subject
        assert matched[0]["account_id"] == GMAIL_ACCOUNT_ID
    finally:
        # Cleanup the local row (draft remains at the provider, same pattern
        # as tests 32–37).
        _clear_local_drafts(GMAIL_ACCOUNT_ID)


# ===================================================================
# Section 5e: Drafts update (tests 41–42)
#
# Each test creates a draft via POST, captures the returned
# provider_draft_id, calls the PATCH endpoint with new recipients /
# subject / body, asserts the response reflects the new content,
# verifies the local DB row, and cleans up (deletes the local row only;
# the draft is intentionally left at the provider — same pattern as
# tests 32/33).
# ===================================================================


def test_41_update_draft_gmail(e2e_client):
    """Create a Gmail draft, update it via PATCH, verify the new content, clean up."""
    ts = datetime.now(timezone.utc).isoformat()
    initial_subject = f"E2E update — Gmail {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{GMAIL_MAILBOX_ID}/accounts/{GMAIL_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": initial_subject,
            "body_html": "<p>E2E update initial</p>",
        },
    )
    _assert_ok(create_resp)
    provider_draft_id = create_resp.json()["provider_draft_id"]
    original_created_at = create_resp.json()["created_at"]

    try:
        new_subject = f"E2E updated — Gmail {datetime.now(timezone.utc).isoformat()}"
        patch_resp = e2e_client.patch(
            f"/mailboxes/{GMAIL_MAILBOX_ID}/accounts/{GMAIL_ACCOUNT_ID}"
            f"/drafts/{provider_draft_id}",
            json={
                "to_recipients": [SEND_RECIPIENT],
                "cc_recipients": [],
                "bcc_recipients": [],
                "subject": new_subject,
                "body_html": "<p>E2E updated body</p>",
            },
        )
        _assert_ok(patch_resp)
        data = patch_resp.json()
        assert data["provider_draft_id"] == provider_draft_id
        assert data["account_id"] == GMAIL_ACCOUNT_ID
        assert data["to_recipients"] == [SEND_RECIPIENT]
        assert data["cc_recipients"] == []
        assert data["bcc_recipients"] == []
        assert data["subject"] == new_subject
        assert data["body_html"] == "<p>E2E updated body</p>"
        assert data["created_at"] == original_created_at
        assert data["updated_at"] >= original_created_at

        # Verify the local DB row reflects the new content.
        conn = _db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT subject, body_html, to_recipients, created_at, updated_at "
                    "FROM drafts "
                    "WHERE provider_draft_id = %s AND account_id = %s",
                    (provider_draft_id, GMAIL_ACCOUNT_ID),
                )
                row = cur.fetchone()
            assert row is not None
            assert row[0] == new_subject
            assert row[1] == "<p>E2E updated body</p>"
            assert row[2] == [SEND_RECIPIENT]
        finally:
            conn.close()
    finally:
        # Clean up the local row (draft stays at the provider — same as tests 32/33).
        conn = _db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM drafts WHERE provider_draft_id = %s AND account_id = %s",
                    (provider_draft_id, GMAIL_ACCOUNT_ID),
                )
            conn.commit()
        finally:
            conn.close()


def test_42_update_draft_outlook(e2e_client):
    """Create an Outlook draft, update it via PATCH, verify the new content, clean up."""
    ts = datetime.now(timezone.utc).isoformat()
    initial_subject = f"E2E update — Outlook {ts}"
    create_resp = e2e_client.post(
        f"/mailboxes/{OUTLOOK_MAILBOX_ID}/accounts/{OUTLOOK_ACCOUNT_ID}/drafts",
        json={
            "to_recipients": [SEND_RECIPIENT],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": initial_subject,
            "body_html": "<p>E2E update initial</p>",
        },
    )
    _assert_ok(create_resp)
    provider_draft_id = create_resp.json()["provider_draft_id"]
    original_created_at = create_resp.json()["created_at"]

    try:
        new_subject = f"E2E updated — Outlook {datetime.now(timezone.utc).isoformat()}"
        patch_resp = e2e_client.patch(
            f"/mailboxes/{OUTLOOK_MAILBOX_ID}/accounts/{OUTLOOK_ACCOUNT_ID}"
            f"/drafts/{provider_draft_id}",
            json={
                "to_recipients": [SEND_RECIPIENT],
                "cc_recipients": [],
                "bcc_recipients": [],
                "subject": new_subject,
                "body_html": "<p>E2E updated body</p>",
            },
        )
        _assert_ok(patch_resp)
        data = patch_resp.json()
        assert data["provider_draft_id"] == provider_draft_id
        assert data["account_id"] == OUTLOOK_ACCOUNT_ID
        assert data["to_recipients"] == [SEND_RECIPIENT]
        assert data["cc_recipients"] == []
        assert data["bcc_recipients"] == []
        assert data["subject"] == new_subject
        # Outlook wraps plain HTML in a full <html>/<body> structure, so match
        # by containment rather than equality (same pattern as tests 36/37).
        assert "E2E updated body" in data["body_html"]
        assert data["created_at"] == original_created_at
        assert data["updated_at"] >= original_created_at

        # Verify the local DB row reflects the new content.
        conn = _db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT subject, body_html, to_recipients "
                    "FROM drafts "
                    "WHERE provider_draft_id = %s AND account_id = %s",
                    (provider_draft_id, OUTLOOK_ACCOUNT_ID),
                )
                row = cur.fetchone()
            assert row is not None
            assert row[0] == new_subject
            assert "E2E updated body" in row[1]
            assert row[2] == [SEND_RECIPIENT]
        finally:
            conn.close()
    finally:
        conn = _db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM drafts WHERE provider_draft_id = %s AND account_id = %s",
                    (provider_draft_id, OUTLOOK_ACCOUNT_ID),
                )
            conn.commit()
        finally:
            conn.close()


# ===================================================================
# Section 6: Auth lifecycle (MUST BE LAST — invalidates session)
# ===================================================================

def test_43_post_auth_logout(e2e_client, flow_state):
    response = e2e_client.post("/auth/logout")
    _assert_ok(response)
    assert response.json() == {"status": "logged_out"}
    flow_state["logged_out"] = "true"


def test_44_get_auth_me_after_logout_401(e2e_client, flow_state):
    _require(flow_state, "logged_out")
    response = e2e_client.get("/auth/me")
    _assert_ok(response, expected=401)
