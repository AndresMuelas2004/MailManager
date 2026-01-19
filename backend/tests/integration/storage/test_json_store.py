import pytest


@pytest.mark.integration
def test_mailbox_store_create_list_get_delete(mailbox_store):
    initial = mailbox_store.list()
    record = {
        "mailbox_id": "mb-test",
        "display_name": "Inbox",
        "created_at": "2024-01-01T00:00:00+00:00",
    }

    created = mailbox_store.create(record)
    assert created == record
    assert mailbox_store.get("mb-test") == record

    all_mailboxes = mailbox_store.list()
    assert record in all_mailboxes

    mailbox_store.delete("mb-test")
    assert mailbox_store.get("mb-test") is None
    assert mailbox_store.list() == initial


@pytest.mark.integration
def test_account_store_upsert_list_get_delete(account_store):
    initial = list(account_store.list_by_mailbox("mb-acc-test"))
    record = {
        "mailbox_id": "mb-acc-test",
        "account_id": "acc-1",
        "provider": "gmail",
        "display_label": "primary",
        "config": {"key": "value"},
        "created_at": "2024-01-01T00:00:00+00:00",
    }

    created = account_store.upsert(record)
    assert created == record
    assert account_store.get("mb-acc-test", "acc-1") == record
    assert record in account_store.list_by_mailbox("mb-acc-test")

    updated = dict(record)
    updated["display_label"] = "updated"
    updated["config"] = {"updated": True}
    account_store.upsert(updated)

    fetched = account_store.get("mb-acc-test", "acc-1")
    assert fetched == updated

    account_store.delete("mb-acc-test", "acc-1")
    assert account_store.get("mb-acc-test", "acc-1") is None
    assert account_store.list_by_mailbox("mb-acc-test") == initial
