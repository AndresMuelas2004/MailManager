"""
Integration tests — happy-path and behavioral tests for every API endpoint.

Each test exercises the full router → service → core → storage flow.
Only external dependencies (provider APIs, disk tokens, env vars) are faked
via the ``test_client`` fixture defined in the integration conftest.

Error-path tests live in ``test_api_errors.py``.
"""

from __future__ import annotations


_MAILBOX_URL = "/mailboxes"


def _setup_mailbox_and_account(client) -> tuple[str, str]:
    """Create a mailbox + gmail account and return ``(mailbox_id, account_id)``."""
    mb = client.post(_MAILBOX_URL, json={"display_name": "Test MB"})
    mailbox_id = mb.json()["mailbox_id"]
    acc = client.post(
        f"{_MAILBOX_URL}/{mailbox_id}/accounts",
        json={"provider": "gmail", "display_label": "my-gmail"},
    )
    account_id = acc.json()["account_id"]
    return mailbox_id, account_id


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

def test_health(test_client):
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ------------------------------------------------------------------
# Mailboxes
# ------------------------------------------------------------------

def test_create_mailbox(test_client):
    resp = test_client.post(_MAILBOX_URL, json={"display_name": "My Mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    assert "mailbox_id" in data
    assert data["display_name"] == "My Mailbox"


def test_list_mailboxes(test_client):
    test_client.post(_MAILBOX_URL, json={"display_name": "Listed"})
    resp = test_client.get(_MAILBOX_URL)
    assert resp.status_code == 200
    names = [m["display_name"] for m in resp.json()]
    assert "Listed" in names


def test_get_mailbox(test_client):
    created = test_client.post(_MAILBOX_URL, json={"display_name": "Fetched"}).json()
    resp = test_client.get(f"{_MAILBOX_URL}/{created['mailbox_id']}")
    assert resp.status_code == 200
    assert resp.json()["mailbox_id"] == created["mailbox_id"]


def test_delete_mailbox(test_client):
    created = test_client.post(_MAILBOX_URL, json={"display_name": "ToDelete"}).json()
    mid = created["mailbox_id"]
    resp = test_client.delete(f"{_MAILBOX_URL}/{mid}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}
    assert test_client.get(f"{_MAILBOX_URL}/{mid}").status_code == 404


# ------------------------------------------------------------------
# Accounts
# ------------------------------------------------------------------

def test_create_account(test_client):
    mb = test_client.post(_MAILBOX_URL, json={"display_name": "AccMB"}).json()
    mid = mb["mailbox_id"]
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "gmail", "display_label": "acc1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "account_id" in data
    assert data["provider"] == "gmail"


def test_list_accounts(test_client):
    mid, _ = _setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/accounts")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_account(test_client):
    mid, aid = _setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/{aid}")
    assert resp.status_code == 200
    assert resp.json()["account_id"] == aid


def test_update_account(test_client):
    mid, aid = _setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/{aid}",
        json={"display_label": "renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_label"] == "renamed"


def test_delete_account(test_client):
    mid, aid = _setup_mailbox_and_account(test_client)
    resp = test_client.delete(f"{_MAILBOX_URL}/{mid}/accounts/{aid}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


def test_connect_account(test_client):
    mid, aid = _setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["account_id"] == aid


# ------------------------------------------------------------------
# Emails
# ------------------------------------------------------------------

def test_list_unread_emails(test_client):
    mid, _ = _setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/emails/unread")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_send_email(test_client):
    mid, aid = _setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={
            "account_id": aid,
            "subject": "Hello",
            "body": "World",
            "recipients": ["dest@example.com"],
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}


# ==================================================================
# Multi-account scenarios
# ==================================================================

def _setup_mailbox_with_two_accounts(client) -> tuple[str, str, str]:
    """Create a mailbox with a gmail and an outlook account."""
    mid = client.post(_MAILBOX_URL, json={"display_name": "Multi"}).json()["mailbox_id"]
    aid1 = client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "gmail", "display_label": "gmail-acc"},
    ).json()["account_id"]
    aid2 = client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "outlook", "display_label": "outlook-acc"},
    ).json()["account_id"]
    return mid, aid1, aid2


def test_multi_account_unread_aggregates(test_client):
    mid, _, _ = _setup_mailbox_with_two_accounts(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/emails/unread")
    assert resp.status_code == 200
    # Each FakeEmailClient returns 3 sample messages → 2 accounts = 6.
    assert len(resp.json()) == 6


def test_multi_account_send_targets_specific_account(test_client):
    mid, aid1, _ = _setup_mailbox_with_two_accounts(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={
            "account_id": aid1,
            "subject": "Targeted",
            "body": "Only aid1",
            "recipients": ["r@e.com"],
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}


# ==================================================================
# Delete mailbox cascade
# ==================================================================

def test_delete_mailbox_removes_accounts(test_client):
    mid, aid1, aid2 = _setup_mailbox_with_two_accounts(test_client)
    test_client.delete(f"{_MAILBOX_URL}/{mid}")
    # Mailbox gone → any account operation returns 404.
    assert test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/{aid1}").status_code == 404
    assert test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/{aid2}").status_code == 404


# ==================================================================
# Partial update
# ==================================================================

def test_update_account_config_only(test_client):
    mid, aid = _setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/{aid}",
        json={"config": {"extra": True}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"] == {"extra": True}
    assert data["display_label"] == "my-gmail"  # unchanged


# ==================================================================
# Outlook end-to-end
# ==================================================================

def test_outlook_account_connect(test_client):
    mid = test_client.post(_MAILBOX_URL, json={"display_name": "OL"}).json()["mailbox_id"]
    aid = test_client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "outlook", "display_label": "my-outlook"},
    ).json()["account_id"]
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert resp.json()["provider"] == "outlook"
