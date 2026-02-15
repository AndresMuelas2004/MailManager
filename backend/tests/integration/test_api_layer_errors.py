"""
Integration tests — direct API-layer error raises.

Tests every ``raise ApiError(...)`` that originates directly in the service
layer **without** going through ``translate_core_error``.  Core-escalated
errors are covered in ``test_core_error_translation.py``.
"""

from __future__ import annotations


_MAILBOX_URL = "/mailboxes"


# ==================================================================
# MailboxNotFound (404) — ensure_mailbox_exists / direct service guard
# ==================================================================

def test_get_mailbox_not_found(test_client):
    resp = test_client.get(f"{_MAILBOX_URL}/nonexistent")
    assert resp.status_code == 404


def test_delete_mailbox_not_found(test_client):
    resp = test_client.delete(f"{_MAILBOX_URL}/nonexistent")
    assert resp.status_code == 404


def test_create_account_on_missing_mailbox(test_client):
    resp = test_client.post(
        f"{_MAILBOX_URL}/nonexistent/accounts",
        json={"provider": "gmail", "display_label": "x"},
    )
    assert resp.status_code == 404


def test_list_accounts_missing_mailbox(test_client):
    resp = test_client.get(f"{_MAILBOX_URL}/nonexistent/accounts")
    assert resp.status_code == 404


def test_connect_account_missing_mailbox(test_client):
    resp = test_client.post(f"{_MAILBOX_URL}/nonexistent/accounts/fake-id/connect")
    assert resp.status_code == 404


def test_unread_missing_mailbox(test_client):
    resp = test_client.get(f"{_MAILBOX_URL}/nonexistent/emails/unread")
    assert resp.status_code == 404


def test_send_missing_mailbox(test_client):
    resp = test_client.post(
        f"{_MAILBOX_URL}/nonexistent/emails/send",
        json={
            "account_id": "x",
            "subject": "S",
            "body": "B",
            "recipients": ["a@b.com"],
        },
    )
    assert resp.status_code == 404


# ==================================================================
# AccountNotFound (404) — direct service lookups
# ==================================================================

def test_get_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/nonexistent")
    assert resp.status_code == 404


def test_update_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/nonexistent",
        json={"display_label": "nope"},
    )
    assert resp.status_code == 404


def test_delete_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.delete(f"{_MAILBOX_URL}/{mid}/accounts/nonexistent")
    assert resp.status_code == 404


def test_connect_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/nonexistent/connect")
    assert resp.status_code == 404


def test_send_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={
            "account_id": "nonexistent",
            "subject": "Hi",
            "body": "Bye",
            "recipients": ["a@b.com"],
        },
    )
    assert resp.status_code == 404


# ==================================================================
# Pydantic 422 — schema validation (FastAPI automatic)
# ==================================================================

def test_create_mailbox_invalid_body(test_client):
    resp = test_client.post(_MAILBOX_URL, json={})
    assert resp.status_code == 422


def test_create_account_empty_provider(test_client):
    mid = test_client.post(_MAILBOX_URL, json={"display_name": "V"}).json()["mailbox_id"]
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "", "display_label": "x"},
    )
    assert resp.status_code == 422
