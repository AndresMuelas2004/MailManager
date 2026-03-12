"""
Integration tests — direct API-layer error raises.

Tests every ``raise ApiError(...)`` that originates directly in the service
layer **without** going through ``translate_core_error``.  Core-escalated
errors are covered in ``test_core_error_translation.py``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.services import emails_service
from database import account_store, mailbox_store, ConnectionPoolError, QueryError


_MAILBOX_URL = "/mailboxes"


# ==================================================================
# MailboxNotFound (404) — ensure_mailbox_access / direct service guard
# ==================================================================

def test_get_mailbox_not_found(test_client):
    resp = test_client.get(f"{_MAILBOX_URL}/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_delete_mailbox_not_found(test_client):
    resp = test_client.delete(f"{_MAILBOX_URL}/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_create_account_on_missing_mailbox(test_client):
    resp = test_client.post(
        f"{_MAILBOX_URL}/nonexistent/accounts",
        json={"provider": "gmail", "display_label": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_list_accounts_missing_mailbox(test_client):
    resp = test_client.get(f"{_MAILBOX_URL}/nonexistent/accounts")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_connect_account_missing_mailbox(test_client):
    resp = test_client.post(f"{_MAILBOX_URL}/nonexistent/accounts/fake-id/connect")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_sync_metadata_missing_mailbox(test_client):
    resp = test_client.post(f"{_MAILBOX_URL}/nonexistent/emails/sync-metadata")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


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
    assert resp.json()["error"]["code"] == "mailbox_not_found"


# ==================================================================
# AccountNotFound (404) — direct service lookups
# ==================================================================

def test_get_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_update_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/nonexistent",
        json={"display_label": "nope"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_delete_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.delete(f"{_MAILBOX_URL}/{mid}/accounts/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_connect_account_not_found(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/nonexistent/connect")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


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
    assert resp.json()["error"]["code"] == "account_not_found"


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


# ==================================================================
# 3C: EmailSendRequest 422 validation
# ==================================================================

def test_send_email_empty_recipients(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": []},
    )
    assert resp.status_code == 422


def test_send_email_empty_subject(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 422


def test_send_email_empty_body(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 422


def test_send_email_missing_account_id(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 422


# ==================================================================
# 3G: handle_unexpected_error — bare RuntimeError → 500 + api_error
# ==================================================================

def test_unexpected_runtime_error_returns_500(test_client, setup_mailbox_and_account, monkeypatch, app):
    mid, _ = setup_mailbox_and_account(test_client)

    def _boom(*_a, **_kw):
        raise RuntimeError("totally unexpected")

    monkeypatch.setattr(emails_service, "sync_email_metadata", _boom)
    # TestClient defaults to raise_server_exceptions=True, so we need a
    # non-raising client to verify the 500 JSON response from the handler.
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "api_error"


# ==================================================================
# DatabaseError translation — monkeypatched store failures
# ==================================================================

def test_list_mailboxes_database_query_error(test_client, monkeypatch):
    def _raise(uid):
        raise QueryError("DB fail")

    monkeypatch.setattr(mailbox_store, "list_by_owner", _raise)
    resp = test_client.get(_MAILBOX_URL)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_query_error"


def test_create_account_database_connection_error(test_client, setup_mailbox_and_account, monkeypatch):
    mid, _ = setup_mailbox_and_account(test_client)

    def _raise(rec):
        raise ConnectionPoolError("Pool exhausted")

    monkeypatch.setattr(account_store, "upsert", _raise)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "gmail", "display_label": "x"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_connection_error"


def test_delete_mailbox_database_query_error(test_client, monkeypatch):
    mb = test_client.post(_MAILBOX_URL, json={"display_name": "To Delete"})
    mid = mb.json()["mailbox_id"]

    def _raise(mailbox_id):
        raise QueryError("DB fail")

    monkeypatch.setattr(mailbox_store, "delete", _raise)
    resp = test_client.delete(f"{_MAILBOX_URL}/{mid}")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_query_error"


# ==================================================================
# Additional 422 validation
# ==================================================================

def test_update_account_empty_display_label(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/{aid}",
        json={"display_label": ""},
    )
    assert resp.status_code == 422


def test_google_login_empty_id_token(test_client):
    resp = test_client.post("/auth/google", json={"id_token": ""})
    assert resp.status_code == 422
