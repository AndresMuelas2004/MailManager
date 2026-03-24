"""
Integration tests - core errors escalated to API errors via translation helpers.

Each test triggers a ``CoreError`` inside a provider client (via ``FakeEmailClient``
kwargs) and verifies that the service layer translates it into the correct HTTP
status code. Direct API-layer raises are covered in ``test_api_layer_errors.py``.
"""

from __future__ import annotations

import pytest

from api.errors.exceptions import AccountMisconfigured
from api.services import accounts_service, emails_service, services_helpers
from core.email import (
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailAuthError,
    EmailConfigError,
    EmailDuplicateAccountLabelError,
    EmailExternalAPIError,
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)


from tests.integration.conftest import MAILBOX_URL as _MAILBOX_URL


# ==================================================================
# connect_account - CoreError during authenticate (translate_connect_error)
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_exc": EmailAuthError("Token rejected.")}],
    indirect=True,
)
def test_connect_auth_failure(failing_test_client, setup_mailbox_and_account):
    """EmailAuthError during connect -> translate_connect_error -> HTTP status."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "account_connect_auth_error"


# ==================================================================
# authenticate_all_silent - auth errors -> raise_on_silent_auth_errors
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_silent_exc": EmailAuthError("Refresh token expired.")}],
    indirect=True,
)
def test_sync_metadata_account_not_connected(failing_test_client, setup_mailbox_and_account):
    """Silent auth failure before sync -> AccountNotConnected (409)."""
    mid, _ = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_silent_exc": EmailAuthError("Refresh token expired.")}],
    indirect=True,
)
def test_send_account_not_connected(failing_test_client, setup_mailbox_and_account):
    """Silent auth failure before send -> AccountNotConnected (409)."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={
            "account_id": aid,
            "subject": "S",
            "body": "B",
            "recipients": ["a@b.com"],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


# ==================================================================
# fetch_all_email_metadata - per-client error -> post-fetch check (502)
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"fetch_exc": EmailExternalAPIError("API timeout.")}],
    indirect=True,
)
def test_sync_metadata_fetch_failure(failing_test_client, setup_mailbox_and_account):
    """Fetch failure collected in last_errors -> ExternalAPIError (502)."""
    mid, _ = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


# ==================================================================
# send_email_from_account - CoreError during send (translate_core_error)
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": EmailExternalAPIError("SMTP rejected.")}],
    indirect=True,
)
def test_send_failure(failing_test_client, setup_mailbox_and_account):
    """Send failure -> translate_core_error -> ExternalAPIError (502)."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={
            "account_id": aid,
            "subject": "S",
            "body": "B",
            "recipients": ["a@b.com"],
        },
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


# ==================================================================
# build_manager_for_accounts - CoreError -> translate_core_error -> 400
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_exc": RuntimeError("Provider crash.")}],
    indirect=True,
)
def test_connect_unexpected_exception(failing_test_client, setup_mailbox_and_account):
    """RuntimeError during connect -> except Exception -> AccountConnectAuthError (401)."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "account_connect_auth_error"


def test_connect_account_misconfigured(test_client, setup_mailbox_and_account, monkeypatch):
    """EmailProviderConfigError in add_account_record -> AccountMisconfigured (400).

    We patch build_manager_for_accounts to call translate_core_error with a
    real core error, mirroring the real implementation path.
    """
    mid, aid = setup_mailbox_and_account(test_client)

    def _build_that_translates(accounts):
        exc = EmailProviderConfigError("Unknown provider 'badprovider'.")
        raise services_helpers.translate_core_error(
            exc, fallback=AccountMisconfigured,
        ) from exc

    monkeypatch.setattr(services_helpers, "build_manager_for_accounts", _build_that_translates)
    monkeypatch.setattr(accounts_service, "build_manager_for_accounts", _build_that_translates)
    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_that_translates)

    resp = test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "account_misconfigured"


# ==================================================================
# 3B: Additional core→API translations via send_exc path
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": EmailRecipientsMissingError("No recipients")}],
    indirect=True,
)
def test_send_recipients_missing(failing_test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "recipients_missing"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": EmailMissingTokenError("Missing token")}],
    indirect=True,
)
def test_send_missing_token(failing_test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": EmailNotAuthenticatedError("Not authenticated")}],
    indirect=True,
)
def test_send_not_authenticated(failing_test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": EmailInvalidCredentialsDataError("Bad creds")}],
    indirect=True,
)
def test_send_invalid_credentials_data(failing_test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "app_credentials_invalid"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": EmailMissingAppCredentialsError("Missing creds")}],
    indirect=True,
)
def test_send_missing_app_credentials(failing_test_client, setup_mailbox_and_account):
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "app_credentials_missing"


# ==================================================================
# 3F: except Exception fallback in sync/send
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"fetch_exc": RuntimeError("unexpected fetch crash")}],
    indirect=True,
)
def test_sync_generic_exception_fallback(failing_test_client, setup_mailbox_and_account):
    """RuntimeError during fetch → EmailFetchError (502)."""
    mid, _ = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "email_fetch_error"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"send_exc": RuntimeError("unexpected send crash")}],
    indirect=True,
)
def test_send_generic_exception_fallback(failing_test_client, setup_mailbox_and_account):
    """RuntimeError during send → ExternalAPIError (502) via manager wrapping."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


# ==================================================================
# Additional CoreError → API translations via send_exc path
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client, expected_status, expected_code",
    [
        ({"send_exc": EmailAuthError("auth fail")}, 409, "account_not_connected"),
        ({"send_exc": EmailMissingRefreshTokenError("no RT")}, 409, "account_not_connected"),
        ({"send_exc": EmailRefreshFailedError("refresh fail")}, 409, "account_not_connected"),
        ({"send_exc": EmailInvalidExpiryError("bad expiry")}, 400, "account_misconfigured"),
        ({"send_exc": EmailInvalidTokenDataError("bad tokens")}, 400, "account_misconfigured"),
        ({"send_exc": EmailAccountRecordError("bad record")}, 400, "account_misconfigured"),
        ({"send_exc": EmailDuplicateAccountLabelError("dup")}, 400, "account_misconfigured"),
        ({"send_exc": EmailConfigError("bad config")}, 400, "account_misconfigured"),
        ({"send_exc": EmailAccountNotFoundError("not found")}, 404, "account_not_found"),
    ],
    indirect=["failing_test_client"],
)
def test_send_additional_core_error_translations(
    failing_test_client, expected_status, expected_code, setup_mailbox_and_account,
):
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/send",
        json={"account_id": aid, "subject": "S", "body": "B", "recipients": ["a@b.com"]},
    )
    assert resp.status_code == expected_status
    assert resp.json()["error"]["code"] == expected_code


# ==================================================================
# Core error translation for read-status, spam, restore-from-spam
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"update_read_status_exc": EmailExternalAPIError("API timeout.")}],
    indirect=True,
)
def test_read_status_core_error_returns_502(failing_test_client, setup_mailbox_and_account):
    """EmailExternalAPIError during update_read_status -> 502."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    resp = failing_test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": aid, "provider_message_id": "m1"}],
        },
    )
    assert resp.status_code == 502


@pytest.mark.parametrize(
    "failing_test_client",
    [{"move_to_spam_exc": EmailExternalAPIError("API timeout.")}],
    indirect=True,
)
def test_spam_move_core_error_returns_502(failing_test_client, setup_mailbox_and_account):
    """EmailExternalAPIError during move_to_spam -> 502."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 502


@pytest.mark.parametrize(
    "failing_test_client",
    [{"restore_from_spam_exc": EmailExternalAPIError("API timeout.")}],
    indirect=True,
)
def test_spam_restore_core_error_returns_502(failing_test_client, setup_mailbox_and_account):
    """EmailExternalAPIError during restore_from_spam -> 502."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/restore-from-spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 502


# ==================================================================
# Silent auth failure for read-status, spam, restore-from-spam
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_silent_exc": EmailAuthError("Token expired.")}],
    indirect=True,
)
def test_read_status_auth_silent_failure_returns_409(failing_test_client, setup_mailbox_and_account):
    """Silent auth failure before read-status -> AccountNotConnected (409)."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": aid, "provider_message_id": "m1"}],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_silent_exc": EmailAuthError("Token expired.")}],
    indirect=True,
)
def test_spam_move_auth_silent_failure_returns_409(failing_test_client, setup_mailbox_and_account):
    """Silent auth failure before spam move -> AccountNotConnected (409)."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_silent_exc": EmailAuthError("Token expired.")}],
    indirect=True,
)
def test_spam_restore_auth_silent_failure_returns_409(failing_test_client, setup_mailbox_and_account):
    """Silent auth failure before spam restore -> AccountNotConnected (409)."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/restore-from-spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_connected"


# ==================================================================
# RuntimeError fallback for read-status, spam, restore-from-spam
# RuntimeError is wrapped by EmailManager -> EmailExternalAPIError
# -> translate_core_error -> ExternalAPIError (502)
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"update_read_status_exc": RuntimeError("crash")}],
    indirect=True,
)
def test_read_status_runtime_error_returns_502(failing_test_client, setup_mailbox_and_account):
    """RuntimeError during update_read_status -> manager wraps -> 502 external_api_error."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    resp = failing_test_client.patch(
        f"{_MAILBOX_URL}/{mid}/emails/read-status",
        json={
            "is_read": True,
            "items": [{"account_id": aid, "provider_message_id": "m1"}],
        },
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"move_to_spam_exc": RuntimeError("crash")}],
    indirect=True,
)
def test_spam_move_runtime_error_returns_502(failing_test_client, setup_mailbox_and_account):
    """RuntimeError during move_to_spam -> manager wraps -> 502 external_api_error."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"


@pytest.mark.parametrize(
    "failing_test_client",
    [{"restore_from_spam_exc": RuntimeError("crash")}],
    indirect=True,
)
def test_spam_restore_runtime_error_returns_502(failing_test_client, setup_mailbox_and_account):
    """RuntimeError during restore_from_spam -> manager wraps -> 502 external_api_error."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    failing_test_client.post(f"{_MAILBOX_URL}/{mid}/emails/sync-metadata")
    resp = failing_test_client.post(
        f"{_MAILBOX_URL}/{mid}/emails/restore-from-spam",
        json={"items": [{"account_id": aid, "provider_message_id": "m1"}]},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "external_api_error"
