import os

import pytest

from api.services import accounts_service
from core.email.email_manager import EmailManager


def _create_mailbox(test_client, display_name="Primary"):
    response = test_client.post("/mailboxes", json={"display_name": display_name})
    assert response.status_code == 200
    return response.json()


def _create_account(test_client, mailbox_id, payload=None):
    if payload is None:
        payload = {
            "provider": "gmail",
            "display_label": "primary-account",
            "config": {"client_id": "id"},
        }
    response = test_client.post(
        f"/mailboxes/{mailbox_id}/accounts",
        json=payload,
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.integration
def test_list_accounts_empty(test_client):
    mailbox = _create_mailbox(test_client)
    response = test_client.get(f"/mailboxes/{mailbox['mailbox_id']}/accounts")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_create_get_update_delete_account(test_client):
    mailbox = _create_mailbox(test_client)
    mailbox_id = mailbox["mailbox_id"]
    created = _create_account(test_client, mailbox_id)
    account_id = created["account_id"]

    list_response = test_client.get(f"/mailboxes/{mailbox_id}/accounts")
    assert list_response.status_code == 200
    assert [item["account_id"] for item in list_response.json()] == [account_id]

    get_response = test_client.get(
        f"/mailboxes/{mailbox_id}/accounts/{account_id}"
    )
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["account_id"] == account_id
    assert payload["display_label"] == "primary-account"

    patch_response = test_client.patch(
        f"/mailboxes/{mailbox_id}/accounts/{account_id}",
        json={"display_label": "updated", "config": {"key": "value"}},
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["display_label"] == "updated"
    assert updated["config"] == {"key": "value"}

    delete_response = test_client.delete(
        f"/mailboxes/{mailbox_id}/accounts/{account_id}"
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted"}

    missing_response = test_client.get(
        f"/mailboxes/{mailbox_id}/accounts/{account_id}"
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "account_not_found"


@pytest.mark.integration
def test_connect_account_success(test_client):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/accounts/{account['account_id']}/connect"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["account_id"] == account["account_id"]
    assert payload["account_label"] == f"{mailbox['mailbox_id']}__{account['account_id']}"


@pytest.mark.integration
def test_create_account_and_connect_existing_mailbox_real_flow(
    test_client_base, temp_base_dir, monkeypatch
):
    if not os.getenv("MIA_GMAIL_CREDENTIALS_PATH"):
        pytest.skip("Set MIA_GMAIL_CREDENTIALS_PATH to run the OAuth connect flow.")

    if not os.getenv("MIA_GMAIL_TOKEN_PATH"):
        token_dir = temp_base_dir / "gmail_tokens"
        token_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("MIA_GMAIL_TOKEN_PATH", str(token_dir))

    mailbox = _create_mailbox(test_client_base)
    mailbox_id = mailbox["mailbox_id"]
    account = _create_account(test_client_base, mailbox_id)

    assert account["mailbox_id"] == mailbox_id

    response = test_client_base.post(
        f"/mailboxes/{mailbox_id}/accounts/{account['account_id']}/connect"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["account_id"] == account["account_id"]
    assert payload["account_label"] == f"{mailbox_id}__{account['account_id']}"


@pytest.mark.integration
def test_connect_account_auth_error_returns_401(
    test_client, fake_client_class, monkeypatch
):
    mailbox = _create_mailbox(test_client)
    account = _create_account(test_client, mailbox["mailbox_id"])

    manager = EmailManager()
    label = f"{mailbox['mailbox_id']}__{account['account_id']}"
    manager.add_client(
        fake_client_class(label, auth_exc=Exception("auth failed"))
    )

    def _build_manager_for_accounts(_accounts):
        return manager

    monkeypatch.setattr(accounts_service, "build_manager_for_accounts", _build_manager_for_accounts)

    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/accounts/{account['account_id']}/connect"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "provider_auth_error"


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"provider": "gmail"},
        {"display_label": "label"},
        {"provider": "", "display_label": "label"},
    ],
)
def test_create_account_validation_errors(test_client, payload):
    mailbox = _create_mailbox(test_client)
    response = test_client.post(
        f"/mailboxes/{mailbox['mailbox_id']}/accounts",
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_account_endpoints_missing_mailbox(test_client):
    mailbox_id = "missing-mailbox"

    list_response = test_client.get(f"/mailboxes/{mailbox_id}/accounts")
    assert list_response.status_code == 404
    assert list_response.json()["error"]["code"] == "mailbox_not_found"

    create_response = test_client.post(
        f"/mailboxes/{mailbox_id}/accounts",
        json={"provider": "gmail", "display_label": "label"},
    )
    assert create_response.status_code == 404
    assert create_response.json()["error"]["code"] == "mailbox_not_found"

    get_response = test_client.get(f"/mailboxes/{mailbox_id}/accounts/missing")
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "mailbox_not_found"


@pytest.mark.integration
def test_account_endpoints_missing_account(test_client):
    mailbox = _create_mailbox(test_client)
    mailbox_id = mailbox["mailbox_id"]
    missing_account = "missing-account"

    get_response = test_client.get(f"/mailboxes/{mailbox_id}/accounts/{missing_account}")
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "account_not_found"

    patch_response = test_client.patch(
        f"/mailboxes/{mailbox_id}/accounts/{missing_account}",
        json={"display_label": "name"},
    )
    assert patch_response.status_code == 404
    assert patch_response.json()["error"]["code"] == "account_not_found"

    delete_response = test_client.delete(
        f"/mailboxes/{mailbox_id}/accounts/{missing_account}"
    )
    assert delete_response.status_code == 404
    assert delete_response.json()["error"]["code"] == "account_not_found"

    connect_response = test_client.post(
        f"/mailboxes/{mailbox_id}/accounts/{missing_account}/connect"
    )
    assert connect_response.status_code == 404
    assert connect_response.json()["error"]["code"] == "account_not_found"
