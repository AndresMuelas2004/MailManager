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
import pytest

from tests.integration.conftest import (
    MAILBOX_URL as _MAILBOX_URL,
    SEEDED_USER_ID as _SEEDED_USER,
    SEEDED_GMAIL_ACCOUNT_ID as _SEEDED_GMAIL_ACCOUNT,
    SEEDED_GMAIL_MAILBOX_ID as _SEEDED_GMAIL_MAILBOX,
    SEEDED_OUTLOOK_ACCOUNT_ID as _SEEDED_OUTLOOK_ACCOUNT,
    SEEDED_OUTLOOK_MAILBOX_ID as _SEEDED_OUTLOOK_MAILBOX,
)
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


def test_list_mailboxes(seeded_test_client):
    resp = seeded_test_client.get(_MAILBOX_URL)
    assert resp.status_code == 200
    data = resp.json()
    names = {m["display_name"] for m in data}
    assert "Gmail inventada" in names
    assert "Outlook inventada" in names
    gmail_mb = next(m for m in data if m["mailbox_id"] == _SEEDED_GMAIL_MAILBOX)
    assert gmail_mb["owner_user_id"] == _SEEDED_USER
    assert gmail_mb["display_name"] == "Gmail inventada"


def test_get_mailbox(seeded_test_client):
    resp = seeded_test_client.get(f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mailbox_id"] == _SEEDED_GMAIL_MAILBOX
    assert data["display_name"] == "Gmail inventada"
    assert data["owner_user_id"] == _SEEDED_USER


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


def test_list_accounts(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/accounts"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    account = data[0]
    assert account["account_id"] == _SEEDED_GMAIL_ACCOUNT
    assert account["provider"] == "gmail"
    assert account["display_label"] == "Gmail inventada - inventadoParaEndpointGet"
    assert account["email_address"] == "gmailinventada@gmail.com"
    assert account["mailbox_id"] == _SEEDED_GMAIL_MAILBOX


def test_get_account(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_OUTLOOK_MAILBOX}/accounts/{_SEEDED_OUTLOOK_ACCOUNT}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["account_id"] == _SEEDED_OUTLOOK_ACCOUNT
    assert data["provider"] == "outlook"
    assert data["display_label"] == "Outlook inventada - inventadoParaEndpointGet"
    assert data["email_address"] == "outlookinventada@outlook.com"
    assert data["mailbox_id"] == _SEEDED_OUTLOOK_MAILBOX


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
    assert "email_address" in data


# ------------------------------------------------------------------
# Emails — sync-metadata
# ------------------------------------------------------------------

def test_sync_email_metadata(test_client, setup_mailbox_and_account, sample_metadata):
    mid, _ = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200
    data = resp.json()
    expected_count = len(sample_metadata)
    assert isinstance(data["total_synced"], int)
    assert data["total_synced"] == expected_count
    assert isinstance(data["accounts"], list)
    assert len(data["accounts"]) == 1
    detail = data["accounts"][0]
    assert "account_id" in detail
    assert "provider" in detail
    assert isinstance(detail["emails_synced"], int)
    assert detail["emails_synced"] == expected_count
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


def test_sync_email_metadata_single_account(test_client, setup_mailbox_and_account, sample_metadata):
    mid, aid = setup_mailbox_and_account(test_client)
    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata?account_id={aid}")
    assert resp.status_code == 200
    data = resp.json()
    expected_count = len(sample_metadata)
    assert data["total_synced"] == expected_count
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == aid


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


# ==================================================================
# Trash management
# ==================================================================


def test_trash_delete_marks_as_deleted(configurable_test_client, isolated_db):
    """Delete action marks TRASH emails as DELETED in the database."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    # Phase 1: sync 2 messages
    m1 = build_metadata(provider_message_id="m1")
    m2 = build_metadata(provider_message_id="m2")
    config["metadata"] = [m1, m2]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Manually move m1 to TRASH in DB
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )

    # Delete m1 from trash
    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "delete",
            "items": [{"provider_message_id": "m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    # Verify m1 is DELETED in DB
    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == "DELETED"


def test_trash_restore_with_previous_box(configurable_test_client, isolated_db):
    """Restore action restores email to previous_box value."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    # Phase 1: sync a message
    m1 = build_metadata(provider_message_id="m1")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Manually set to TRASH with previous_box = SENT
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH', previous_box = 'SENT' "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )

    # Restore m1
    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": "m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    # Verify m1 is restored to SENT and previous_box is NULL
    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box, previous_box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row[0] == "SENT"
        assert row[1] is None


def test_trash_restore_null_previous_box_defaults_to_all_mail(configurable_test_client, isolated_db):
    """When previous_box is NULL and fetch_messages_metadata returns nothing, defaults to ALL_MAIL."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Set to TRASH with no previous_box
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": "m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == "ALL_MAIL"


def test_trash_restore_null_previous_box_discovers_real_box(configurable_test_client, isolated_db):
    """When previous_box is NULL, fetch_messages_metadata discovers the real box."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1")
    config["metadata"] = [m1]
    # Configure fetch_messages_metadata to return SENT for m1
    config["fetch_messages_metadata_return"] = [
        build_metadata(provider_message_id="m1", box="SENT"),
    ]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Set to TRASH with no previous_box
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": "m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box, previous_box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row[0] == "SENT"
        assert row[1] is None


def test_trash_restore_updates_provider_message_id(configurable_test_client, isolated_db):
    """Restore works when the provider_message_id stays the same (default FakeEmailClient path)."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="old_m1")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE provider_message_id = 'old_m1' AND account_id = %s::uuid",
            (aid,),
        )

    # FakeEmailClient.restore_from_trash returns {k: k} by default,
    # so provider_message_id stays 'old_m1' → 'old_m1'.
    # This test verifies the DB update path works even when ID stays the same.
    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": "old_m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT provider_message_id, box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id = 'old_m1'",
            (aid,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[1] == "ALL_MAIL"


def test_trash_delete_partial_success(configurable_test_client, isolated_db):
    """Provider-first: if provider only deletes 1 of 2, DB only marks 1 as DELETED."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1")
    m2 = build_metadata(provider_message_id="m2")
    config["metadata"] = [m1, m2]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Move both to TRASH
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE account_id = %s::uuid AND provider_message_id IN ('m1', 'm2')",
            (aid,),
        )

    # Provider only succeeds for m1
    config["delete_return"] = ["m1"]

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "delete",
            "items": [
                {"provider_message_id": "m1", "account_id": aid},
                {"provider_message_id": "m2", "account_id": aid},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT provider_message_id, box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id IN ('m1', 'm2') "
            "ORDER BY provider_message_id",
            (aid,),
        )
        rows = cur.fetchall()
        result = {r[0]: r[1] for r in rows}
        assert result["m1"] == "DELETED"
        assert result["m2"] == "TRASH"


def test_trash_restore_changes_provider_message_id(configurable_test_client, isolated_db):
    """Restore updates the provider_message_id when the provider returns a new ID (Outlook)."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="old_m1")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE provider_message_id = 'old_m1' AND account_id = %s::uuid",
            (aid,),
        )

    # Provider returns a new ID for the restored message
    config["restore_return"] = {"old_m1": "new_m1"}

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "restore",
            "items": [{"provider_message_id": "old_m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    with isolated_db.cursor() as cur:
        # new_m1 should exist with box = ALL_MAIL
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'new_m1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "ALL_MAIL"
        # old_m1 should no longer exist
        cur.execute(
            "SELECT count(*) FROM email_metadata "
            "WHERE provider_message_id = 'old_m1' AND account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == 0


def test_trash_delete_multi_account(configurable_test_client, isolated_db):
    """Delete across two accounts in a single request."""
    client, config, mid, _ = _setup_configurable(configurable_test_client)

    # Create a second account under the same mailbox
    acc2_resp = client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "gmail", "display_label": "cfg-gmail-2"},
    )
    aid2 = acc2_resp.json()["account_id"]

    # Get aid1 from the first account
    accounts_resp = client.get(f"{_MAILBOX_URL}/{mid}/accounts")
    all_accounts = accounts_resp.json()
    aid1 = next(a["account_id"] for a in all_accounts if a["display_label"] == "cfg-gmail")

    # Sync m1 for account 1
    config["metadata"] = [build_metadata(provider_message_id="m1")]
    client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # Sync m2 for account 2 (same metadata list, different account syncs it)
    config["metadata"] = [build_metadata(provider_message_id="m2")]
    client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # Move both to TRASH
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE account_id = %s::uuid AND provider_message_id = 'm1'",
            (aid1,),
        )
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE account_id = %s::uuid AND provider_message_id = 'm2'",
            (aid2,),
        )

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "delete",
            "items": [
                {"provider_message_id": "m1", "account_id": aid1},
                {"provider_message_id": "m2", "account_id": aid2},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 2

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id = 'm1'",
            (aid1,),
        )
        assert cur.fetchone()[0] == "DELETED"
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id = 'm2'",
            (aid2,),
        )
        assert cur.fetchone()[0] == "DELETED"


# ==================================================================
# Move to trash
# ==================================================================


def test_move_to_trash_happy_path(configurable_test_client, isolated_db):
    """move-to-trash sets box='TRASH' and previous_box in the database."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1", box="ALL_MAIL")
    m2 = build_metadata(provider_message_id="m2", box="SENT")
    config["metadata"] = [m1, m2]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/move-to-trash",
        json={
            "items": [
                {"provider_message_id": "m1", "account_id": aid},
                {"provider_message_id": "m2", "account_id": aid},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 2

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box, previous_box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row[0] == "TRASH"
        assert row[1] == "ALL_MAIL"

        cur.execute(
            "SELECT box, previous_box FROM email_metadata "
            "WHERE provider_message_id = 'm2' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row[0] == "TRASH"
        assert row[1] == "SENT"


def test_move_to_trash_multi_account(configurable_test_client, isolated_db):
    """move-to-trash across two accounts in a single request."""
    client, config, mid, _ = _setup_configurable(configurable_test_client)

    acc2_resp = client.post(
        f"{_MAILBOX_URL}/{mid}/accounts",
        json={"provider": "gmail", "display_label": "cfg-gmail-2"},
    )
    aid2 = acc2_resp.json()["account_id"]

    accounts_resp = client.get(f"{_MAILBOX_URL}/{mid}/accounts")
    all_accounts = accounts_resp.json()
    aid1 = next(a["account_id"] for a in all_accounts if a["display_label"] == "cfg-gmail")

    config["metadata"] = [build_metadata(provider_message_id="m1")]
    client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    config["metadata"] = [build_metadata(provider_message_id="m2")]
    client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/move-to-trash",
        json={
            "items": [
                {"provider_message_id": "m1", "account_id": aid1},
                {"provider_message_id": "m2", "account_id": aid2},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 2

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id = 'm1'",
            (aid1,),
        )
        assert cur.fetchone()[0] == "TRASH"
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id = 'm2'",
            (aid2,),
        )
        assert cur.fetchone()[0] == "TRASH"


def test_move_to_trash_partial_success(configurable_test_client, isolated_db):
    """Provider-first: if provider only trashes 1 of 2, DB only updates 1."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1")
    m2 = build_metadata(provider_message_id="m2")
    config["metadata"] = [m1, m2]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    config["move_to_trash_return"] = {"m1": "m1"}

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/move-to-trash",
        json={
            "items": [
                {"provider_message_id": "m1", "account_id": aid},
                {"provider_message_id": "m2", "account_id": aid},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT provider_message_id, box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id IN ('m1', 'm2') "
            "ORDER BY provider_message_id",
            (aid,),
        )
        rows = cur.fetchall()
        result = {r[0]: r[1] for r in rows}
        assert result["m1"] == "TRASH"
        assert result["m2"] == "ALL_MAIL"


def test_move_to_trash_already_in_trash(configurable_test_client, isolated_db):
    """Moving emails already in TRASH should result in affected == 0."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Manually set m1 to TRASH in DB
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )

    # Try to move m1 to trash again — SQL filter excludes TRASH rows
    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/move-to-trash",
        json={
            "items": [{"provider_message_id": "m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 0


def test_move_to_trash_changes_provider_message_id(configurable_test_client, isolated_db):
    """When the provider returns a new ID (e.g. Outlook), the DB stores the new ID with box=TRASH."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="old_m1")
    config["metadata"] = [m1]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    config["move_to_trash_return"] = {"old_m1": "new_m1"}

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/move-to-trash",
        json={
            "items": [{"provider_message_id": "old_m1", "account_id": aid}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    with isolated_db.cursor() as cur:
        # new_m1 should exist with box = TRASH
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'new_m1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "TRASH"
        # old_m1 should no longer exist
        cur.execute(
            "SELECT count(*) FROM email_metadata "
            "WHERE provider_message_id = 'old_m1' AND account_id = %s::uuid",
            (aid,),
        )
        assert cur.fetchone()[0] == 0


def test_trash_restore_partial_success(configurable_test_client, isolated_db):
    """Provider-first: if provider only restores 1 of 2, DB only restores 1."""
    client, config, mid, aid = _setup_configurable(configurable_test_client)

    m1 = build_metadata(provider_message_id="m1")
    m2 = build_metadata(provider_message_id="m2")
    config["metadata"] = [m1, m2]
    resp = client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 200

    # Move both to TRASH
    with isolated_db.cursor() as cur:
        cur.execute(
            "UPDATE email_metadata SET box = 'TRASH' "
            "WHERE account_id = %s::uuid AND provider_message_id IN ('m1', 'm2')",
            (aid,),
        )

    # Provider only restores m1
    config["restore_return"] = {"m1": "m1"}

    resp = client.post(
        f"{_MAILBOX_URL}/{mid}/emails/trash",
        json={
            "action": "restore",
            "items": [
                {"provider_message_id": "m1", "account_id": aid},
                {"provider_message_id": "m2", "account_id": aid},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT provider_message_id, box FROM email_metadata "
            "WHERE account_id = %s::uuid AND provider_message_id IN ('m1', 'm2') "
            "ORDER BY provider_message_id",
            (aid,),
        )
        rows = cur.fetchall()
        result = {r[0]: r[1] for r in rows}
        assert result["m1"] == "ALL_MAIL"
        assert result["m2"] == "TRASH"


# ==================================================================
# Read status
# ==================================================================

def test_update_read_status(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    # Sync metadata first so messages exist in DB
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": aid, "provider_message_id": "m1"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "updated_count" in data
    assert isinstance(data["updated_count"], int)
    assert data["updated_count"] >= 1
    assert "accounts" in data
    assert isinstance(data["accounts"], list)
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == aid
    assert isinstance(data["accounts"][0]["updated"], int)


def test_update_read_status_persists_to_db(test_client, setup_mailbox_and_account, isolated_db):
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # All three messages start with is_read=False; mark m1 as read
    test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": aid, "provider_message_id": "m1"}],
        },
    )

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT is_read FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is True


def test_update_read_status_preserves_box(test_client, setup_mailbox_and_account, isolated_db):
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # Record the box value before the read-status update
    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        box_before = cur.fetchone()[0]

    test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": aid, "provider_message_id": "m1"}],
        },
    )

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        box_after = cur.fetchone()[0]
    assert box_after == box_before


def test_update_read_status_nonexistent_account_404(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    fake_account_id = "00000000-0000-4000-a000-000000000099"
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": fake_account_id, "provider_message_id": "m1"}],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_update_read_status_nonexistent_mailbox_404(test_client):
    fake_mailbox_id = "00000000-0000-4000-a000-000000000099"
    fake_account_id = "00000000-0000-4000-a000-000000000098"
    resp = test_client.patch(
        f"{_MAILBOX_URL}/{fake_mailbox_id}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": fake_account_id, "provider_message_id": "m1"}],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


# ===== Emails -- spam =====


def test_move_to_spam(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["moved_count"] >= 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == aid


def test_move_to_spam_persists_box_to_db(test_client, setup_mailbox_and_account, isolated_db):
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "SPAM"


def test_restore_from_spam(test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # First move to spam
    test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    # Then restore
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/restore-from-spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["moved_count"] >= 1


def test_restore_from_spam_persists_box_to_db(test_client, setup_mailbox_and_account, isolated_db):
    mid, aid = setup_mailbox_and_account(test_client)
    test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")

    # Move to spam first
    test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    # Restore
    test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/restore-from-spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )

    with isolated_db.cursor() as cur:
        cur.execute(
            "SELECT box FROM email_metadata "
            "WHERE provider_message_id = 'm1' AND account_id = %s::uuid",
            (aid,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "ALL_MAIL"


def test_spam_nonexistent_account_404(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    fake_account_id = "00000000-0000-4000-a000-000000000099"
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": fake_account_id, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_spam_nonexistent_mailbox_404(test_client):
    fake_mailbox_id = "00000000-0000-4000-a000-000000000099"
    fake_account_id = "00000000-0000-4000-a000-000000000098"
    resp = test_client.post(
        f"{_MAILBOX_URL}/{fake_mailbox_id}/emails/spam",
        json={"items": [{"account_id": fake_account_id, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


def test_restore_from_spam_nonexistent_account_404(test_client, setup_mailbox_and_account):
    mid, _ = setup_mailbox_and_account(test_client)
    fake_account_id = "00000000-0000-4000-a000-000000000099"
    resp = test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/restore-from-spam",
        json={"items": [{"account_id": fake_account_id, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_restore_from_spam_nonexistent_mailbox_404(test_client):
    fake_mailbox_id = "00000000-0000-4000-a000-000000000099"
    fake_account_id = "00000000-0000-4000-a000-000000000098"
    resp = test_client.post(
        f"{_MAILBOX_URL}/{fake_mailbox_id}/emails/restore-from-spam",
        json={"items": [{"account_id": fake_account_id, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


# ------------------------------------------------------------------
# Emails — list emails
# ------------------------------------------------------------------

def test_list_emails_unified_view(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails?box=ALL_MAIL"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 30
    item = data[0]
    assert "provider_message_id" in item
    assert "account_id" in item
    assert "from_email" in item
    assert "subject" in item
    assert "received_at" in item
    assert "is_read" in item
    assert all(e["box"] == "ALL_MAIL" for e in data)
    assert all(e["account_id"] == _SEEDED_GMAIL_ACCOUNT for e in data)


def test_list_emails_single_account_view(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_OUTLOOK_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_OUTLOOK_ACCOUNT},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 30
    assert all(e["account_id"] == _SEEDED_OUTLOOK_ACCOUNT for e in data)
    assert all(e["box"] == "ALL_MAIL" for e in data)


def test_list_emails_invalid_box_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails?box=INVALID"
    )
    assert resp.status_code == 422


def test_list_emails_missing_box_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails"
    )
    assert resp.status_code == 422


def test_list_emails_nonexistent_account_returns_404(seeded_test_client):
    fake_account_id = "00000000-0000-4000-a000-000000000099"
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": fake_account_id},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "account_not_found"


def test_list_emails_nonexistent_mailbox_returns_404(seeded_test_client):
    fake_mailbox_id = "00000000-0000-4000-a000-000000000099"
    resp = seeded_test_client.get(f"{_MAILBOX_URL}/{fake_mailbox_id}/emails?box=ALL_MAIL")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mailbox_not_found"


# ------------------------------------------------------------------
# Seeded GET endpoint tests — exact count per box (migration 0010)
# ------------------------------------------------------------------

@pytest.mark.parametrize("box, expected_count", [
    ("ALL_MAIL", 30),
    ("SENT", 10),
    ("TRASH", 4),
    ("SPAM", 6),
])
def test_seeded_list_emails_by_account(seeded_test_client, box, expected_count):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": box, "account_id": _SEEDED_GMAIL_ACCOUNT},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == expected_count
    assert all(e["account_id"] == _SEEDED_GMAIL_ACCOUNT for e in data)
    assert all(e["box"] == box for e in data)


@pytest.mark.parametrize("box, expected_count", [
    ("ALL_MAIL", 30),
    ("SENT", 10),
    ("TRASH", 4),
    ("SPAM", 6),
])
def test_seeded_list_emails_by_mailbox(seeded_test_client, box, expected_count):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": box},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == expected_count
    assert all(e["box"] == box for e in data)


# ------------------------------------------------------------------
# Emails — list emails: search, limit, offset (lupa MVP)
# ------------------------------------------------------------------

def test_list_emails_q_too_short_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "q": "a"},
    )
    assert resp.status_code == 422


def test_list_emails_q_empty_string_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "q": ""},
    )
    assert resp.status_code == 422


def test_list_emails_q_two_chars_is_accepted(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "q": "ab"},
    )
    assert resp.status_code == 200


def test_list_emails_q_too_long_returns_422(seeded_test_client):
    # Router enforces max_length=200.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "q": "x" * 201},
    )
    assert resp.status_code == 422


def test_list_emails_limit_zero_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "limit": 0},
    )
    assert resp.status_code == 422


def test_list_emails_limit_above_max_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "limit": 600},
    )
    assert resp.status_code == 422


def test_list_emails_limit_at_max_is_accepted(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "limit": 500},
    )
    assert resp.status_code == 200


def test_list_emails_offset_negative_returns_422(seeded_test_client):
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "offset": -1},
    )
    assert resp.status_code == 422


def test_list_emails_search_case_insensitive(seeded_test_client):
    # Seeded subject "Sprint planning - semana 12" lives only on Gmail account.
    # Different case of the same word must still match.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "SPRINT"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # Every returned row must contain "sprint" somewhere in the searchable
    # columns (subject / from_email / from_name) — case-insensitive.
    for e in data:
        haystack = " ".join([
            (e.get("subject") or ""),
            (e.get("from_email") or ""),
            (e.get("from_name") or ""),
        ]).lower()
        assert "sprint" in haystack


def test_list_emails_search_accent_insensitive_via_unaccent(seeded_test_client):
    # Seeded sender "Karen López" — search without the accent must still match.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "lopez"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    matched = [
        e for e in data
        if (e.get("from_name") or "").lower().replace("ó", "o") == "karen lopez"
    ]
    assert matched, "search 'lopez' should accent-insensitively match seeded 'Karen López'"


def test_list_emails_search_typo_does_not_match(seeded_test_client):
    # "facutra" is a typo; Opción A does not tolerate typos. There is a seeded
    # subject "Factura #4521 adjunta" — the search must NOT return it.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "facutra"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Whatever matches "facutra" as a substring is fine; what must NOT happen
    # is matching "Factura" through fuzzy/typo tolerance.
    for e in data:
        haystack = " ".join([
            (e.get("subject") or ""),
            (e.get("from_email") or ""),
            (e.get("from_name") or ""),
        ]).lower()
        assert "factura" not in haystack


def test_list_emails_search_percent_is_literal(seeded_test_client):
    # _escape_like must neutralise % so the ILIKE pattern matches the literal
    # two-char substring "%a" — not the SQL wildcard. Router rejects q="%"
    # (min_length=2), so the probe is "%a". No seeded row contains that exact
    # substring, so a regression that dropped the escape (turning % into the
    # ILIKE wildcard) would return rows instead of an empty list.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "%a"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_emails_search_underscore_is_literal(seeded_test_client):
    # Same shape as the % test, for the underscore wildcard. _escape_like must
    # turn it into a literal so q="_a" matches a literal "_a" substring (which
    # no seeded row contains), not the "any single char + a" SQL wildcard.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "_a"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_emails_search_matches_in_from_email_only(seeded_test_client):
    # Seeded row gmail-allmail-012 has from_email="karen@hr.com"; the substring
    # "hr.com" appears in no other row's subject, from_name, or from_email.
    # This pins the from_email branch of the OR predicate end-to-end against
    # real PostgreSQL — a regression that dropped from_email from the search
    # would return zero rows instead of the Karen López row.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "hr.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all("hr.com" in (row.get("from_email") or "").lower() for row in data)
    # Load-bearing assertion: at least one returned row matches ONLY in from_email.
    assert any(
        "hr.com" in (row.get("from_email") or "").lower()
        and "hr.com" not in (row.get("subject") or "").lower()
        and "hr.com" not in (row.get("from_name") or "").lower()
        for row in data
    )


def test_list_emails_search_multi_word_is_AND(seeded_test_client):
    # "Sprint planning - semana 12" matches both "sprint" and "planning".
    # "Sprint planning - tareas asignadas" also matches both.
    # No other seeded row contains both words.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={
            "box": "ALL_MAIL",
            "account_id": _SEEDED_GMAIL_ACCOUNT,
            "q": "Sprint planning",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # Every returned row must contain BOTH tokens in the union of searchable columns.
    for e in data:
        haystack = " ".join([
            (e.get("subject") or ""),
            (e.get("from_email") or ""),
            (e.get("from_name") or ""),
        ]).lower()
        assert "sprint" in haystack
        assert "planning" in haystack


def test_list_emails_search_with_unified_view_matches_only_in_mailbox(seeded_test_client):
    # The Gmail mailbox holds only the Gmail seeded account; rows from the
    # Outlook mailbox must not bleed into the unified view of the Gmail mailbox.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "q": "factura"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Whatever rows are returned, none of them belong to the Outlook account.
    assert all(e["account_id"] != _SEEDED_OUTLOOK_ACCOUNT for e in data)
    # And every row must actually contain the search token.
    for e in data:
        haystack = " ".join([
            (e.get("subject") or ""),
            (e.get("from_email") or ""),
            (e.get("from_name") or ""),
        ]).lower()
        assert "factura" in haystack


@pytest.mark.parametrize(
    ("box", "q"),
    [
        ("SENT", "solicitud"),  # appears only in SENT subjects
        ("TRASH", "semanal"),   # appears only in TRASH subjects
        ("SPAM", "urgent"),     # appears only in SPAM subjects
    ],
)
def test_list_emails_search_respects_box(seeded_test_client, box, q):
    # docs/features/lupa.md contractualises "la lupa filtra dentro del box".
    # Each (box, q) probe targets a token unique to that box on the Gmail seed,
    # so a regression dropping the box filter when q is supplied would surface
    # as rows from other boxes leaking into the response.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": box, "account_id": _SEEDED_GMAIL_ACCOUNT, "q": q},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(e["box"] == box for e in data)
    needle = q.lower()
    for row in data:
        haystack = " ".join([
            (row.get("subject") or ""),
            (row.get("from_email") or ""),
            (row.get("from_name") or ""),
        ]).lower()
        assert needle in haystack


def test_list_emails_search_matches_in_subject_only(seeded_test_client):
    # Seeded subjects "Actualización del presupuesto Q1" (gmail-allmail-004) and
    # its reply (gmail-allmail-005) contain the substring "presupuesto"; neither
    # the senders ("dave@corp.com" / "Dave Wilson", "eve@corp.com" / "Eve
    # Thompson") nor any other Gmail ALL_MAIL row contain it. Pins the subject
    # branch of the OR predicate end-to-end against real PostgreSQL — a
    # regression that dropped subject from the search would return zero rows.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "presupuesto"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Exactly 2 seeded rows in Gmail ALL_MAIL contain "presupuesto":
    # gmail-allmail-004 and gmail-allmail-005 (the reply on the same thread).
    # gmail-sent-002 also contains it but lives in box=SENT, so it is excluded.
    assert {row["provider_message_id"] for row in data} == {
        "gmail-allmail-004", "gmail-allmail-005",
    }
    assert all("presupuesto" in (row.get("subject") or "").lower() for row in data)
    # Load-bearing assertion: every returned row matches ONLY in subject —
    # neither from_email ("dave@corp.com" / "eve@corp.com") nor from_name
    # ("Dave Wilson" / "Eve Thompson") contains the token.
    assert all(
        "presupuesto" not in (row.get("from_email") or "").lower()
        and "presupuesto" not in (row.get("from_name") or "").lower()
        for row in data
    )


def test_list_emails_search_matches_in_from_name_only(seeded_test_client):
    # Seeded sender "Irene Salazar" (gmail-allmail-009) — the substring "salazar"
    # appears in no other row's subject, from_email, or from_name across the
    # Gmail seed (subject is "Contrato pendiente de firma", email is
    # "irene@legal.com"). Pins the from_name branch of the OR predicate; a
    # regression that dropped from_name from the search would return zero rows.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "salazar"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Exactly 1 seeded row contains "salazar" anywhere — gmail-allmail-009.
    assert [row["provider_message_id"] for row in data] == ["gmail-allmail-009"]
    row = data[0]
    assert "salazar" in (row.get("from_name") or "").lower()
    # Load-bearing assertion: the match is ONLY in from_name.
    assert "salazar" not in (row.get("subject") or "").lower()
    assert "salazar" not in (row.get("from_email") or "").lower()


def test_list_emails_search_accent_at_word_start(seeded_test_client):
    # Seeded subjects "Análisis competitivo Q1 - presentación" (outlook-allmail-023)
    # and "Re: Análisis competitivo - datos extra" (outlook-allmail-024) start
    # with the accented character "Á". Searching "analisis" without the accent
    # must match through unaccent — covering the case where the diacritic is on
    # the FIRST character of the word, complementing the existing "lopez" →
    # "López" test which targets accent in the middle of a word.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_OUTLOOK_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_OUTLOOK_ACCOUNT, "q": "analisis"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Exactly 2 seeded Outlook ALL_MAIL rows contain "Análisis":
    # outlook-allmail-023 and outlook-allmail-024 (the reply on the same thread).
    assert {row["provider_message_id"] for row in data} == {
        "outlook-allmail-023", "outlook-allmail-024",
    }
    assert all(
        "análisis" in (row.get("subject") or "").lower()
        for row in data
    )


def test_list_emails_search_accent_in_subject_middle(seeded_test_client):
    # Seeded subject "Recordatorio: evaluación de desempeño" (gmail-allmail-012)
    # has the accent IN THE MIDDLE of "evaluación" (over the second "o"). The
    # existing "lopez" → "López" test pins accent-in-middle behaviour for the
    # from_name column; this test pins the same behaviour for the subject column.
    # The token "evaluacion" appears in no other row's subject / from_email /
    # from_name, so all matches come from this single row's subject.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "evaluacion"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Exactly 1 seeded row contains "evaluación" — gmail-allmail-012.
    assert [row["provider_message_id"] for row in data] == ["gmail-allmail-012"]
    assert "evaluación" in (data[0].get("subject") or "").lower()


def test_list_emails_search_mixed_case_with_accent(seeded_test_client):
    # Seeded sender "Karen López" (gmail-allmail-012). Combining all-uppercase
    # with an accented character in the same query (q="LÓPEZ") must still match
    # the mixed-case stored value. Pins the interaction between case folding
    # (lower()) and accent stripping (unaccent()) inside the SQL predicate.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "LÓPEZ"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Exactly 1 seeded row contains "López" — gmail-allmail-012 ("Karen López").
    assert [row["provider_message_id"] for row in data] == ["gmail-allmail-012"]
    assert "lópez" in (data[0].get("from_name") or "").lower()


def test_list_emails_search_unaccent_handles_n_with_tilde(seeded_test_client):
    # Seeded subjects "Campaña de lanzamiento - borrador" (gmail-allmail-014)
    # and "Re: Campaña de lanzamiento - aprobado" (gmail-allmail-015) contain
    # the Spanish "ñ". PostgreSQL's standard unaccent rules transform "ñ" → "n",
    # so q="campana" (without the tilde) must match "Campaña". This covers a
    # class of accent different from the typical á/é/í/ó/ú vowel diacritics
    # already exercised by the "lopez" / "evaluacion" tests.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "q": "campana"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Exactly 2 seeded rows contain "Campaña":
    # gmail-allmail-014 and gmail-allmail-015 (the reply on the same thread).
    assert {row["provider_message_id"] for row in data} == {
        "gmail-allmail-014", "gmail-allmail-015",
    }
    assert all(
        "campaña" in (row.get("subject") or "").lower()
        for row in data
    )


def test_list_emails_limit_caps_returned_rows(seeded_test_client):
    # ALL_MAIL has 30 seeded rows for Gmail. limit=5 must trim the response.
    resp = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5


def test_list_emails_offset_skips_initial_rows(seeded_test_client):
    # With limit 5 and offset 5, the second page must differ from the first.
    first = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "limit": 5, "offset": 0},
    ).json()
    second = seeded_test_client.get(
        f"{_MAILBOX_URL}/{_SEEDED_GMAIL_MAILBOX}/emails",
        params={"box": "ALL_MAIL", "account_id": _SEEDED_GMAIL_ACCOUNT, "limit": 5, "offset": 5},
    ).json()
    assert len(first) == 5
    assert len(second) == 5
    first_ids = {e["provider_message_id"] for e in first}
    second_ids = {e["provider_message_id"] for e in second}
    assert first_ids.isdisjoint(second_ids)
