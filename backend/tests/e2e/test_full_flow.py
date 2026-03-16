"""
E2E full-flow tests — real Gmail and Outlook APIs, no fakes.

Each test checks its own prerequisites via flow_state keys.
If a prerequisite is missing (because the producing test failed),
the dependent test is SKIPPED. Independent tests always run.

Run with: python -m pytest backend/tests/e2e -v --tb=short
"""

from __future__ import annotations

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


# ===================================================================
# Section 1: Health
# ===================================================================

def test_01_health_check(e2e_client):
    _assert_ok(e2e_client.get("/health"))


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
    mid = response.json()["mailbox_id"]
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


def test_12_delete_account(e2e_client, flow_state):
    _require(flow_state, "temp_outlook_id")
    response = e2e_client.delete(
        f"/mailboxes/{flow_state['temp_mid']}/accounts/{flow_state['temp_outlook_id']}"
    )
    _assert_ok(response)


def test_13_delete_mailbox(e2e_client, flow_state):
    _require(flow_state, "temp_mid")
    response = e2e_client.delete(f"/mailboxes/{flow_state['temp_mid']}")
    _assert_ok(response)
    flow_state["temp_mid_deleted"] = flow_state["temp_mid"]


def test_14_get_deleted_mailbox_404(e2e_client, flow_state):
    _require(flow_state, "temp_mid_deleted")
    response = e2e_client.get(f"/mailboxes/{flow_state['temp_mid_deleted']}")
    _assert_ok(response, expected=404)


# ===================================================================
# Section 4: Provider operations (pre-existing connected accounts)
# ===================================================================

def test_15_sync_metadata_gmail(e2e_client):
    response = e2e_client.post(f"/mailboxes/{GMAIL_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(response)
    data = response.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] >= 0
    accounts = data["accounts"]
    synced_ids = {a["account_id"] for a in accounts}
    assert GMAIL_ACCOUNT_ID in synced_ids


def test_16_sync_metadata_outlook(e2e_client):
    response = e2e_client.post(f"/mailboxes/{OUTLOOK_MAILBOX_ID}/emails/sync-metadata")
    _assert_ok(response)
    data = response.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] >= 0
    accounts = data["accounts"]
    synced_ids = {a["account_id"] for a in accounts}
    assert OUTLOOK_ACCOUNT_ID in synced_ids


def test_17_send_email_gmail(e2e_client):
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


def test_18_send_email_outlook(e2e_client):
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


# ===================================================================
# Section 5: Auth lifecycle (MUST BE LAST — invalidates session)
# ===================================================================

def test_19_post_auth_logout(e2e_client, flow_state):
    response = e2e_client.post("/auth/logout")
    _assert_ok(response)
    assert response.json() == {"status": "logged_out"}
    flow_state["logged_out"] = "true"


def test_20_get_auth_me_after_logout_401(e2e_client, flow_state):
    _require(flow_state, "logged_out")
    response = e2e_client.get("/auth/me")
    _assert_ok(response, expected=401)
