import pytest

from api.services import emails_service
from core.email.email_manager import EmailManager


def _create_mailbox(test_client, display_name="Primary"):
    response = test_client.post("/mailboxes", json={"display_name": display_name})
    assert response.status_code == 200
    return response.json()


def _create_account(test_client, mailbox_id):
    response = test_client.post(
        f"/mailboxes/{mailbox_id}/accounts",
        json={
            "provider": "gmail",
            "display_label": "primary-account",
            "config": {"client_id": "id"},
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.integration
def test_list_unread_emails_empty(test_client):
    mailbox = _create_mailbox(test_client)
    response = test_client.get(f"/mailboxes/{mailbox['mailbox_id']}/emails/unread")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_list_unread_emails_success_with_clients(
    test_client, fake_client_class, sample_messages, monkeypatch
):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    manager = EmailManager()
    label = f"{mailbox['mailbox_id']}__{account['account_id']}"
    manager.add_client(fake_client_class(label, unread_messages=sample_messages))

    def _build_manager_for_accounts(_accounts):
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager_for_accounts)

    response = test_client.get(f"/mailboxes/{mailbox['mailbox_id']}/emails/unread")
    assert response.status_code == 200
    payload = response.json()
    assert [item["message_id"] for item in payload] == ["m1", "m2", "m3"]
    assert [client.get_account_label() for client in manager._clients] == [label]


@pytest.mark.integration
def test_list_unread_emails_auth_error_returns_409(
    test_client, fake_client_class, monkeypatch
):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    manager = EmailManager()
    label = f"{mailbox['mailbox_id']}__{account['account_id']}"
    manager.add_client(fake_client_class(label, auth_silent_exc=Exception("missing_token")))

    def _build_manager_for_accounts(_accounts):
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager_for_accounts)

    response = test_client.get(f"/mailboxes/{mailbox['mailbox_id']}/emails/unread")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_not_connected"


@pytest.mark.integration
def test_list_unread_emails_fetch_error_returns_502(
    test_client, fake_client_class, monkeypatch
):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    manager = EmailManager()
    label = f"{mailbox['mailbox_id']}__{account['account_id']}"
    manager.add_client(fake_client_class(label, fetch_exc=Exception("boom")))

    def _build_manager_for_accounts(_accounts):
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager_for_accounts)

    response = test_client.get(f"/mailboxes/{mailbox['mailbox_id']}/emails/unread")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "email_fetch_error"


@pytest.mark.integration
def test_send_email_success(test_client):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/emails/send",
        json={
            "account_id": account["account_id"],
            "subject": "hello",
            "body": "content",
            "recipients": ["to@example.com"],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "sent"}


@pytest.mark.integration
def test_send_email_account_missing_returns_404(test_client):
    mailbox = _create_mailbox(test_client)
    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/emails/send",
        json={
            "account_id": "missing",
            "subject": "hello",
            "body": "content",
            "recipients": ["to@example.com"],
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_found"


@pytest.mark.integration
def test_send_email_auth_error_returns_409(
    test_client, fake_client_class, monkeypatch
):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    manager = EmailManager()
    label = f"{mailbox['mailbox_id']}__{account['account_id']}"
    manager.add_client(fake_client_class(label, auth_silent_exc=Exception("missing_token")))

    def _build_manager_for_accounts(_accounts):
        return manager

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager_for_accounts)

    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/emails/send",
        json={
            "account_id": account["account_id"],
            "subject": "hello",
            "body": "content",
            "recipients": ["to@example.com"],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_not_connected"


@pytest.mark.integration
def test_send_email_failure_returns_502(test_client, monkeypatch):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    manager = EmailManager()

    def _build_manager_for_accounts(_accounts):
        return manager

    def _fail_send_email(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager_for_accounts)
    monkeypatch.setattr(manager, "send_email_from_account", _fail_send_email)

    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/emails/send",
        json={
            "account_id": account["account_id"],
            "subject": "hello",
            "body": "content",
            "recipients": ["to@example.com"],
        },
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "email_send_error"


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"account_id": "acc"},
        {"account_id": "acc", "subject": "s"},
        {"account_id": "acc", "subject": "s", "body": ""},
    ],
)
def test_send_email_validation_errors(test_client, payload):
    mailbox = _create_mailbox(test_client)
    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/emails/send",
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_email_endpoints_missing_mailbox(test_client):
    mailbox_id = "missing-mailbox"

    unread_response = test_client.get(f"/mailboxes/{mailbox_id}/emails/unread")
    assert unread_response.status_code == 404
    assert unread_response.json()["error"]["code"] == "mailbox_not_found"

    send_response = test_client.post(
        f"/mailboxes/{mailbox_id}/emails/send",
        json={
            "account_id": "acc",
            "subject": "hello",
            "body": "content",
            "recipients": ["to@example.com"],
        },
    )
    assert send_response.status_code == 404
    assert send_response.json()["error"]["code"] == "mailbox_not_found"
