"""Extended unit tests for EmailManager orchestration gaps."""

from __future__ import annotations

import pytest

from core.email.email_manager import EmailManager
from core.email.errors import EmailExternalAPIError


def test_authenticate_all_silent_with_payloads_passes_creds_and_tokens(
    manager: EmailManager, fake_client_factory
):
    """auth_payloads tuple (creds, tokens) is forwarded to authenticate_silent()."""
    client = fake_client_factory("acct1")
    manager.add_client(client)

    app_creds = {"client_id": "id"}
    user_toks = {"access_token": "at"}
    payloads = {"acct1": (app_creds, user_toks)}
    manager.authenticate_all_silent(auth_payloads=payloads)

    assert client.authenticate_silent_calls == 1
    assert client.last_app_credentials == app_creds
    assert client.last_user_tokens == user_toks


def test_authenticate_all_silent_returns_refreshed_tokens_dict(
    manager: EmailManager, fake_client_factory
):
    """When a client returns tokens from authenticate_silent, they appear in the result."""
    refreshed = {"access_token": "new", "refresh_token": "new_rt"}
    client = fake_client_factory("acct1", auth_silent_return=refreshed)
    manager.add_client(client)

    result = manager.authenticate_all_silent()
    assert result == {"acct1": refreshed}


def test_authenticate_all_silent_no_refresh_returns_empty_dict(
    manager: EmailManager, fake_client_factory
):
    """When no client refreshes, the result is an empty dict."""
    client = fake_client_factory("acct1", auth_silent_return=None)
    manager.add_client(client)

    result = manager.authenticate_all_silent()
    assert result == {}


def test_connect_account_passes_app_credentials_to_client(
    manager: EmailManager, fake_client_factory
):
    """connect_account forwards app_credentials to the client's authenticate()."""
    client = fake_client_factory("acct1")
    manager.add_client(client)

    creds = {"client_id": "id", "client_secret": "s"}
    manager.connect_account("acct1", app_credentials=creds)

    assert client.last_app_credentials == creds


def test_connect_account_returns_token_dict_from_client(
    manager: EmailManager, fake_client_factory
):
    """connect_account returns whatever the client's authenticate() returns."""
    token_dict = {"access_token": "tok", "refresh_token": "rt"}
    client = fake_client_factory("acct1", auth_return=token_dict)
    manager.add_client(client)

    result = manager.connect_account("acct1")
    assert result == token_dict


def test_send_email_from_account_propagates_client_exception(
    manager: EmailManager, fake_client_factory
):
    """Exceptions from the client's send_email() propagate to the caller."""
    exc = EmailExternalAPIError("send failed")
    client = fake_client_factory("acct1", send_exc=exc)
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="send failed"):
        manager.send_email_from_account("acct1", "subj", "body", ["a@b.com"])


def test_fetch_empty_manager_returns_empty_dict(manager: EmailManager):
    """A manager with no clients returns an empty dict for fetch."""
    result = manager.fetch_all_email_metadata()
    assert result == {}
    assert manager.get_last_errors() == {}
