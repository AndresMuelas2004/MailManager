"""
Integration tests — happy-path and behavioral tests for every API endpoint.

Each test exercises the full router -> service -> core -> storage flow.
Only external dependencies (provider APIs, disk tokens, env vars) are faked
via the ``test_client`` fixture defined in the integration conftest.

Error-path tests live in ``test_api_layer_errors.py`` and
``test_core_error_translation.py``.
"""

from __future__ import annotations

from core.email.email_client import LabelUpdate
from tests.integration.conftest import MAILBOX_URL as _MAILBOX_URL
from tests.shared.email_fakes import build_metadata


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


def test_list_accounts(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/accounts")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_account(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/{aid}")
    assert resp.status_code == 200
    assert resp.json()["account_id"] == aid


def test_update_account(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/{aid}",
        json={"display_label": "renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_label"] == "renamed"


def test_delete_account(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.delete(f"{_MAILBOX_URL}/{mid}/accounts/{aid}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


def test_connect_account(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["account_id"] == aid


# ------------------------------------------------------------------
# Emails — sync-metadata
# ------------------------------------------------------------------

def test_sync_email_metadata(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] == 3
    assert isinstance(data["accounts"], list)
    assert len(data["accounts"]) == 1
    detail = data["accounts"][0]
    assert "account_id" in detail
    assert "provider" in detail
    assert isinstance(detail["emails_synced"], int)
    assert detail["emails_synced"] == 3
    assert data["total_synced"] == detail["emails_synced"]


def test_sync_email_metadata_persists_to_db(test_client, setup_mailbox_and_account, isolated_db):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200
    total_synced = resp.json()["total_synced"]
    assert total_synced > 0

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM email_metadata WHERE account_id IN "
            "(SELECT account_id FROM accounts WHERE mailbox_id = %s::uuid)",
            (mid,),
        )
        row_count = cur.fetchone()[0]
    assert row_count == total_synced


def test_send_email(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
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


def test_send_email_persists_metadata(test_client, setup_mailbox_and_account, isolated_db):
    """After send, the sent email metadata is persisted in the database."""
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={
            "account_id": aid,
            "subject": "Persisted Send",
            "body": "Body",
            "recipients": ["dest@example.com"],
        },
    )
    assert resp.status_code == 200
    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM email_metadata "
            "WHERE account_id = %s::uuid AND box = 'SENT'",
            (aid,),
        )
        count = cur.fetchone()[0]
    assert count >= 1


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


def test_multi_account_sync_metadata(test_client):
    mid, _, _ = _setup_mailbox_with_two_accounts(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["accounts"]) == 2


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

def test_delete_mailbox_removes_accounts(test_client, isolated_db):
    mid, aid1, aid2 = _setup_mailbox_with_two_accounts(test_client)
    test_client.delete(f"{_MAILBOX_URL}/{mid}")
    assert test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/{aid1}").status_code == 404
    assert test_client.get(f"{_MAILBOX_URL}/{mid}/accounts/{aid2}").status_code == 404

    # 3H: Verify accounts are actually gone at DB level (CASCADE).
    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM accounts WHERE mailbox_id = %s::uuid", (mid,),
        )
        assert cur.fetchone()[0] == 0


# ==================================================================
# Partial update
# ==================================================================

def test_update_account_config_only(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/accounts/{aid}",
        json={"config": {"extra": True}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"] == {"extra": True}
    assert data["display_label"] == "test-gmail"


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


# ==================================================================
# Sync pipeline: advanced scenarios
# ==================================================================


def _setup_configurable(client_and_config, provider="gmail"):
    """Create mailbox + account using the configurable_test_client."""
    client, config = client_and_config
    mb = client.post(_MAILBOX_URL, json={"display_name": "Cfg MB"})
    mailbox_id = mb.json()["mailbox_id"]
    acc = client.post(
        f"{_MAILBOX_URL}/{mailbox_id}/accounts",
        json={"provider": provider, "display_label": f"cfg-{provider}"},
    )
    account_id = acc.json()["account_id"]
    return client, config, mailbox_id, account_id


def test_sync_reconciliation_deletes_ghosts_from_db(
    configurable_test_client, isolated_db,
):
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    # Phase 1: incremental sync with 3 messages
    m1 = build_metadata(provider_message_id="m1")
    m2 = build_metadata(provider_message_id="m2")
    m3 = build_metadata(provider_message_id="m3")
    config["metadata"] = [m1, m2, m3]
    config["is_full_sync"] = False
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200
    assert resp.json()["total_synced"] == 3

    # Phase 2: full sync that only returns m1; m2 and m3 are ghosts
    config["metadata"] = [m1]
    config["is_full_sync"] = True
    config["existing_message_ids"] = ["m1"]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM email_metadata WHERE account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == 1


def test_sync_deletes_removes_messages_from_db(
    configurable_test_client, isolated_db,
):
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    # Phase 1: seed 3 messages
    m1 = build_metadata(provider_message_id="m1")
    m2 = build_metadata(provider_message_id="m2")
    m3 = build_metadata(provider_message_id="m3")
    config["metadata"] = [m1, m2, m3]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Phase 2: delete m1 via SyncResult.deletes
    config["metadata"] = []
    config["deletes"] = ["m1"]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM email_metadata WHERE account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT provider_message_id FROM email_metadata WHERE account_id = %s::uuid",
            (aid,),
        )
        remaining = {row[0] for row in cur.fetchall()}
        assert "m1" not in remaining


def test_sync_label_updates_modifies_db_records(
    configurable_test_client, isolated_db,
):
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    # Phase 1: insert m1 with is_read=False, box=ALL_MAIL
    m1 = build_metadata(provider_message_id="m1", is_read=False, box="ALL_MAIL")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Phase 2: update m1 labels
    config["metadata"] = []
    config["label_updates"] = [LabelUpdate("m1", is_read=True, box="SENT")]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT is_read, box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row[0] is True
        assert row[1] == "SENT"


def test_sync_persists_and_updates_cursor(
    configurable_test_client, isolated_db,
):
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    # Phase 1: sync with cursor_v1
    config["sync_cursor_return"] = "cursor_v1"
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT sync_cursor FROM accounts WHERE account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == "cursor_v1"

    # Phase 2: sync with cursor_v2
    config["metadata"] = []
    config["sync_cursor_return"] = "cursor_v2"
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT sync_cursor FROM accounts WHERE account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == "cursor_v2"
