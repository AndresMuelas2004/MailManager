"""Unit tests for EmailManager behavior using in-memory fake clients."""

import pytest

from core.email.email_manager import EmailManager
from core.email.errors import (
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailClientUnsupportedError,
    EmailDuplicateAccountLabelError,
    EmailProviderConfigError,
)
from core.email.outlook_client import OutlookClient


def test_add_account_record_requires_mailbox_id(manager: EmailManager):
    record = {"account_id": "acc", "provider": "gmail", "config": {}}
    with pytest.raises(EmailAccountRecordError, match="mailbox_id"):
        manager.add_account_record(record)


def test_add_account_record_requires_account_id(manager: EmailManager):
    record = {"mailbox_id": "mb", "provider": "gmail", "config": {}}
    with pytest.raises(EmailAccountRecordError, match="account_id"):
        manager.add_account_record(record)


def test_add_account_record_requires_provider(manager: EmailManager):
    record = {"mailbox_id": "mb", "account_id": "acc", "config": {}}
    with pytest.raises(EmailAccountRecordError, match="provider"):
        manager.add_account_record(record)


def test_add_account_record_builds_label_mailbox__account_and_registers_client(
    manager: EmailManager,
):
    """Builds a label from mailbox/account IDs and registers the client."""
    record = {"mailbox_id": "mb", "account_id": "acc", "provider": "gmail"}
    manager.add_account_record(record)
    assert len(manager._clients) == 1
    assert manager._clients[0].get_account_label() == "mb__acc"


def test_build_client_unsupported_provider_raises_error(manager: EmailManager):
    """Rejects unknown providers."""
    with pytest.raises(EmailProviderConfigError, match="Unknown provider"):
        manager._build_client("yahoo", "label")


def test_build_client_outlook_builds_client(manager: EmailManager):
    client = manager._build_client("outlook", "label")
    assert isinstance(client, OutlookClient)
    assert client.get_account_label() == "label"


def test_add_client_accepts_multiple_distinct_labels(
    manager: EmailManager, fake_client_ok, fake_client_ok_2
):
    """Allows registering multiple unique account labels."""
    manager.add_client(fake_client_ok)
    manager.add_client(fake_client_ok_2)
    assert len(manager._clients) == 2


def test_add_client_rejects_duplicate_account_label(
    manager: EmailManager, fake_client_ok, fake_client_factory
):
    """Rejects a second client with the same account label."""
    manager.add_client(fake_client_ok)
    dup = fake_client_factory(fake_client_ok.get_account_label())
    with pytest.raises(EmailDuplicateAccountLabelError, match="already exists"):
        manager.add_client(dup)

def test_authenticate_all_silent_calls_authenticate_silent_on_each_client(
    manager: EmailManager, fake_client_ok, fake_client_ok_2
):
    """Calls authenticate_silent on every registered client."""
    manager.add_client(fake_client_ok)
    manager.add_client(fake_client_ok_2)
    manager.authenticate_all_silent()
    assert fake_client_ok.authenticate_silent_calls == 1
    assert fake_client_ok_2.authenticate_silent_calls == 1
    assert manager.get_last_errors() == {}


def test_authenticate_all_silent_records_errors_and_continues(
    manager: EmailManager, fake_client_fail_auth_silent, fake_client_ok
):
    """Records silent auth errors and still authenticates remaining clients."""
    manager.add_client(fake_client_fail_auth_silent)
    manager.add_client(fake_client_ok)
    manager.authenticate_all_silent()
    errors = manager.get_last_errors()
    assert set(errors.keys()) == {fake_client_fail_auth_silent.get_account_label()}
    assert fake_client_ok.authenticate_silent_calls == 1


def test_authenticate_all_silent_client_without_method_is_recorded_as_error(
    manager: EmailManager,
):
    """Treats missing authenticate_silent as an error."""
    class MinimalClient:
        def __init__(self, label: str) -> None:
            self._label = label

        def authenticate(self) -> None:
            return None

        def get_account_label(self) -> str:
            return self._label

    minimal = MinimalClient("acct_min")
    manager.add_client(minimal)
    manager.authenticate_all_silent()
    errors = manager.get_last_errors()
    assert set(errors.keys()) == {"acct_min"}
    assert isinstance(errors["acct_min"], EmailClientUnsupportedError)


def test_connect_account_authenticates_only_requested_label(
    manager: EmailManager, fake_client_ok, fake_client_ok_2
):
    """Authenticates the specified account without touching others."""
    manager.add_client(fake_client_ok)
    manager.add_client(fake_client_ok_2)
    manager.connect_account(fake_client_ok.get_account_label())
    assert fake_client_ok.authenticate_calls == 1
    assert fake_client_ok_2.authenticate_calls == 0


def test_connect_account_not_found_raises_error(manager: EmailManager):
    with pytest.raises(EmailAccountNotFoundError, match="not found"):
        manager.connect_account("missing")
    assert manager.get_last_errors() == {}


def test_connect_account_authenticate_failure_is_recorded_and_raised(
    manager: EmailManager, fake_client_fail_auth
):
    """Propagates auth failure and records it under the account label."""
    manager.add_client(fake_client_fail_auth)
    with pytest.raises(Exception):
        manager.connect_account(fake_client_fail_auth.get_account_label())
    errors = manager.get_last_errors()
    assert set(errors.keys()) == {fake_client_fail_auth.get_account_label()}


def test_fetch_all_unread_emails_aggregates_lists_from_all_clients(
    manager: EmailManager, sample_messages, fake_client_factory
):
    """Aggregates unread messages from all clients in order."""
    client1 = fake_client_factory(
        "acct1", unread_messages=[sample_messages[0], sample_messages[1]]
    )
    client2 = fake_client_factory("acct2", unread_messages=[sample_messages[2]])
    manager.add_client(client1)
    manager.add_client(client2)

    results = manager.fetch_all_unread_emails()
    assert [m.message_id for m in results] == ["m1", "m2", "m3"]


def test_fetch_all_unread_emails_records_errors_and_continues(
    manager: EmailManager, fake_client_fail_fetch, fake_client_ok
):
    """Records fetch errors and returns successful results."""
    manager.add_client(fake_client_fail_fetch)
    manager.add_client(fake_client_ok)
    results = manager.fetch_all_unread_emails()
    assert [m.message_id for m in results] == ["m1"]
    errors = manager.get_last_errors()
    assert set(errors.keys()) == {fake_client_fail_fetch.get_account_label()}


def test_send_email_from_account_routes_to_correct_client(
    manager: EmailManager, fake_client_ok, fake_client_ok_2
):
    """Routes send requests to the matching account label."""
    manager.add_client(fake_client_ok)
    manager.add_client(fake_client_ok_2)

    manager.send_email_from_account(
        fake_client_ok.get_account_label(),
        subject="hello",
        body="body",
        recipients=["a@example.com"],
    )

    assert fake_client_ok.sent_emails == [("hello", "body", ["a@example.com"])]
    assert fake_client_ok_2.sent_emails == []


def test_send_email_from_account_not_found_raises_error(manager: EmailManager):
    with pytest.raises(EmailAccountNotFoundError, match="not found"):
        manager.send_email_from_account("missing", "s", "b", ["a@example.com"])


def test_get_last_errors_returns_copy(manager: EmailManager, fake_client_fail_fetch):
    """Protects internal error registry from external mutation."""
    manager.add_client(fake_client_fail_fetch)
    manager.fetch_all_unread_emails()

    errors = manager.get_last_errors()
    errors["new"] = Exception("mutate")

    fresh = manager.get_last_errors()
    assert "new" not in fresh
    assert set(fresh.keys()) == {fake_client_fail_fetch.get_account_label()}
