"""
Integration tests — core errors escalated to API errors via ``translate_core_error``.

Each test triggers a ``CoreError`` inside a provider client (via ``FakeEmailClient``
kwargs) and verifies that the service layer translates it into the correct HTTP
status code.  Direct API-layer raises are covered in ``test_api_layer_errors.py``.
"""

from __future__ import annotations

import pytest

from api.errors.exceptions import AccountMisconfigured
from api.services import accounts_service, emails_service, services_helpers
from core.email.errors import (
    EmailAuthError,
    EmailExternalAPIError,
    EmailProviderConfigError,
)


_MAILBOX_URL = "/mailboxes"


# ==================================================================
# connect_account — CoreError during authenticate (translate_core_error)
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_exc": EmailAuthError("Token rejected.")}],
    indirect=True,
)
def test_connect_auth_failure(failing_test_client, setup_mailbox_and_account):
    """EmailAuthError during connect -> translate_core_error -> HTTP status."""
    mid, aid = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.post(f"{_MAILBOX_URL}/{mid}/accounts/{aid}/connect")
    # EmailAuthError maps to AccountNotConnected (409) through _CORE_TO_API_MAP,
    # even though the service fallback is ProviderAuthError.
    assert resp.status_code == 409


# ==================================================================
# authenticate_all_silent — auth errors -> raise_on_silent_auth_errors
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"auth_silent_exc": EmailAuthError("Refresh token expired.")}],
    indirect=True,
)
def test_unread_account_not_connected(failing_test_client, setup_mailbox_and_account):
    """Silent auth failure before fetch -> AccountNotConnected (409)."""
    mid, _ = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.get(f"{_MAILBOX_URL}/{mid}/emails/unread")
    assert resp.status_code == 409


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


# ==================================================================
# fetch_all_unread_emails — per-client error -> post-fetch check (502)
# ==================================================================

@pytest.mark.parametrize(
    "failing_test_client",
    [{"fetch_exc": EmailExternalAPIError("API timeout.")}],
    indirect=True,
)
def test_unread_fetch_failure(failing_test_client, setup_mailbox_and_account):
    """Fetch failure collected in last_errors -> ExternalAPIError (502)."""
    mid, _ = setup_mailbox_and_account(failing_test_client)
    resp = failing_test_client.get(f"{_MAILBOX_URL}/{mid}/emails/unread")
    assert resp.status_code == 502


# ==================================================================
# send_email_from_account — CoreError during send (translate_core_error)
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


# ==================================================================
# build_manager_for_accounts — CoreError -> translate_core_error -> 400
# ==================================================================

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
