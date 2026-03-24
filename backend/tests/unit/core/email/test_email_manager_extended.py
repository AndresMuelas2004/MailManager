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


# ------------------------------------------------------------------
# update_read_status
# ------------------------------------------------------------------


def test_update_read_status_delegates_to_correct_client(
    manager: EmailManager, fake_client_factory
):
    """update_read_status forwards message_ids and is_read to the right client."""
    client = fake_client_factory("acct1")
    manager.add_client(client)

    result = manager.update_read_status("acct1", ["m1", "m2"], True)

    assert result == ["m1", "m2"]
    assert len(client.update_read_status_calls) == 1
    assert client.update_read_status_calls[0] == (["m1", "m2"], True)


def test_update_read_status_account_not_found_raises(
    manager: EmailManager,
):
    """Calling update_read_status with a non-existent label raises EmailAccountNotFoundError."""
    from core.email.errors import EmailAccountNotFoundError

    with pytest.raises(EmailAccountNotFoundError):
        manager.update_read_status("nonexistent", ["m1"], True)


def test_update_read_status_core_error_propagates(
    manager: EmailManager, fake_client_factory
):
    """A CoreError subclass raised by the client propagates unchanged."""
    exc = EmailExternalAPIError("provider down")
    client = fake_client_factory("acct1", update_read_status_exc=exc)
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="provider down"):
        manager.update_read_status("acct1", ["m1"], True)


def test_update_read_status_unexpected_exception_wraps(
    manager: EmailManager, fake_client_factory
):
    """A RuntimeError from the client is wrapped in EmailExternalAPIError."""
    client = fake_client_factory("acct1", update_read_status_exc=RuntimeError("boom"))
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="boom"):
        manager.update_read_status("acct1", ["m1"], False)


# ------------------------------------------------------------------
# move_to_spam
# ------------------------------------------------------------------


def test_move_to_spam_delegates_to_correct_client(
    manager: EmailManager, fake_client_factory
):
    """move_to_spam forwards message_ids to the right client and returns results."""
    from core.email.email_client import SpamMoveResult

    client = fake_client_factory("acct1")
    manager.add_client(client)

    result = manager.move_to_spam("acct1", ["m1", "m2"])

    assert len(result) == 2
    assert all(isinstance(r, SpamMoveResult) for r in result)
    assert result[0].old_id == "m1"
    assert len(client.move_to_spam_calls) == 1
    assert client.move_to_spam_calls[0] == ["m1", "m2"]


def test_move_to_spam_account_not_found_raises(
    manager: EmailManager,
):
    """Calling move_to_spam with a non-existent label raises EmailAccountNotFoundError."""
    from core.email.errors import EmailAccountNotFoundError

    with pytest.raises(EmailAccountNotFoundError):
        manager.move_to_spam("nonexistent", ["m1"])


def test_move_to_spam_core_error_propagates(
    manager: EmailManager, fake_client_factory
):
    """A CoreError subclass raised by the client propagates unchanged."""
    exc = EmailExternalAPIError("spam API error")
    client = fake_client_factory("acct1", move_to_spam_exc=exc)
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="spam API error"):
        manager.move_to_spam("acct1", ["m1"])


def test_move_to_spam_unexpected_exception_wraps(
    manager: EmailManager, fake_client_factory
):
    """A RuntimeError from the client is wrapped in EmailExternalAPIError."""
    client = fake_client_factory("acct1", move_to_spam_exc=RuntimeError("unexpected"))
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="unexpected"):
        manager.move_to_spam("acct1", ["m1"])


# ------------------------------------------------------------------
# restore_from_spam
# ------------------------------------------------------------------


def test_restore_from_spam_delegates_to_correct_client(
    manager: EmailManager, fake_client_factory
):
    """restore_from_spam forwards message_ids to the right client and returns results."""
    from core.email.email_client import SpamMoveResult

    client = fake_client_factory("acct1")
    manager.add_client(client)

    result = manager.restore_from_spam("acct1", ["m1", "m2"])

    assert len(result) == 2
    assert all(isinstance(r, SpamMoveResult) for r in result)
    assert result[0].old_id == "m1"
    assert len(client.restore_from_spam_calls) == 1
    assert client.restore_from_spam_calls[0] == ["m1", "m2"]


def test_restore_from_spam_account_not_found_raises(
    manager: EmailManager,
):
    """Calling restore_from_spam with a non-existent label raises EmailAccountNotFoundError."""
    from core.email.errors import EmailAccountNotFoundError

    with pytest.raises(EmailAccountNotFoundError):
        manager.restore_from_spam("nonexistent", ["m1"])


def test_restore_from_spam_core_error_propagates(
    manager: EmailManager, fake_client_factory
):
    """A CoreError subclass raised by the client propagates unchanged."""
    exc = EmailExternalAPIError("restore API error")
    client = fake_client_factory("acct1", restore_from_spam_exc=exc)
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="restore API error"):
        manager.restore_from_spam("acct1", ["m1"])


def test_restore_from_spam_unexpected_exception_wraps(
    manager: EmailManager, fake_client_factory
):
    """A RuntimeError from the client is wrapped in EmailExternalAPIError."""
    client = fake_client_factory("acct1", restore_from_spam_exc=RuntimeError("kaboom"))
    manager.add_client(client)

    with pytest.raises(EmailExternalAPIError, match="kaboom"):
        manager.restore_from_spam("acct1", ["m1"])
