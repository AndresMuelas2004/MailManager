import pytest


def _create_mailbox(test_client, display_name="Primary"):
    response = test_client.post("/mailboxes", json={"display_name": display_name})
    assert response.status_code == 200
    return response.json()


@pytest.mark.integration
def test_create_list_get_delete_mailbox(test_client):
    created = _create_mailbox(test_client, display_name="Inbox")
    mailbox_id = created["mailbox_id"]

    list_response = test_client.get("/mailboxes")
    assert list_response.status_code == 200
    mailbox_ids = {item["mailbox_id"] for item in list_response.json()}
    assert mailbox_id in mailbox_ids

    get_response = test_client.get(f"/mailboxes/{mailbox_id}")
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["mailbox_id"] == mailbox_id
    assert payload["display_name"] == "Inbox"

    delete_response = test_client.delete(f"/mailboxes/{mailbox_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted"}

    missing_response = test_client.get(f"/mailboxes/{mailbox_id}")
    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "mailbox_not_found"


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": "x" * 200},
    ],
)
def test_create_mailbox_validation_errors(test_client, payload):
    response = test_client.post("/mailboxes", json=payload)
    assert response.status_code == 422


@pytest.mark.integration
def test_get_delete_missing_mailbox(test_client):
    mailbox_id = "missing-mailbox"

    get_response = test_client.get(f"/mailboxes/{mailbox_id}")
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "mailbox_not_found"

    delete_response = test_client.delete(f"/mailboxes/{mailbox_id}")
    assert delete_response.status_code == 404
    assert delete_response.json()["error"]["code"] == "mailbox_not_found"
