from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from api.services import accounts_service, emails_service, mailboxes_service, services_helpers
from api.storage import json_store
from core.email.email_manager import EmailManager

_UNIT_CONFTEST_PATH = (
    Path(__file__).resolve().parents[1] / "unit" / "core" / "conftest.py"
)


def _load_unit_conftest():
    spec = spec_from_file_location("tests_unit_conftest", _UNIT_CONFTEST_PATH)
    module = module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Unable to load unit conftest module.")
    spec.loader.exec_module(module)
    return module


_unit_conftest = _load_unit_conftest()
FakeEmailClient = _unit_conftest.FakeEmailClient


@pytest.fixture(scope="session")
def fake_client_class():
    return FakeEmailClient


@pytest.fixture
def test_client(test_client_base, sample_messages, monkeypatch):
    def _build_manager(accounts):
        manager = EmailManager()
        for account in accounts:
            mailbox_id = str(account.get("mailbox_id") or "")
            account_id = str(account.get("account_id") or "")
            label = f"{mailbox_id}__{account_id}"
            manager.add_client(
                FakeEmailClient(
                    label,
                    unread_messages=sample_messages,
                    auth_return={"access_token": "tok", "refresh_token": "ref"},
                )
            )
        return manager

    _fake_app_creds = {"client_id": "fake", "client_secret": SecretStr("fake")}
    _fake_account_tokens = {
        "access_token": SecretStr("tok"),
        "refresh_token": SecretStr("ref"),
    }

    monkeypatch.setattr(services_helpers, "build_manager_for_accounts", _build_manager)
    monkeypatch.setattr(accounts_service, "build_manager_for_accounts", _build_manager)
    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager)

    # Fake credential / token helpers so tests never hit disk or env vars.
    monkeypatch.setattr(
        services_helpers, "load_wrapped_app_credentials", lambda _provider: _fake_app_creds,
    )
    monkeypatch.setattr(
        services_helpers, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: _fake_account_tokens,
    )
    monkeypatch.setattr(
        accounts_service, "load_wrapped_app_credentials", lambda _provider: _fake_app_creds,
    )
    monkeypatch.setattr(
        emails_service, "load_wrapped_app_credentials", lambda _provider: _fake_app_creds,
    )
    monkeypatch.setattr(
        emails_service, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: _fake_account_tokens,
    )

    # No-op token persistence and cleanup.
    monkeypatch.setattr(accounts_service, "save_account_tokens", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        accounts_service, "delete_account_tokens_for_records", lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(emails_service, "save_account_tokens", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        mailboxes_service, "delete_account_tokens_for_records", lambda *_a, **_kw: None,
    )

    return test_client_base


@pytest.fixture
def failing_test_client(test_client_base, sample_messages, monkeypatch, request):
    """Test client whose FakeEmailClients are configured with failure kwargs.

    Use via ``@pytest.mark.parametrize("failing_test_client", [kwargs], indirect=True)``
    where *kwargs* is a dict forwarded to every ``FakeEmailClient`` constructor
    (e.g. ``{"auth_exc": SomeError(...)}``, ``{"fetch_exc": ...}``).
    """
    client_kwargs = getattr(request, "param", {})

    def _build_manager(accounts):
        manager = EmailManager()
        for account in accounts:
            mailbox_id = str(account.get("mailbox_id") or "")
            account_id = str(account.get("account_id") or "")
            label = f"{mailbox_id}__{account_id}"
            manager.add_client(
                FakeEmailClient(
                    label,
                    unread_messages=sample_messages,
                    auth_return={"access_token": "tok", "refresh_token": "ref"},
                    **client_kwargs,
                )
            )
        return manager

    _fake_app_creds = {"client_id": "fake", "client_secret": SecretStr("fake")}
    _fake_account_tokens = {
        "access_token": SecretStr("tok"),
        "refresh_token": SecretStr("ref"),
    }

    monkeypatch.setattr(services_helpers, "build_manager_for_accounts", _build_manager)
    monkeypatch.setattr(accounts_service, "build_manager_for_accounts", _build_manager)
    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager)

    monkeypatch.setattr(
        services_helpers, "load_wrapped_app_credentials", lambda _provider: _fake_app_creds,
    )
    monkeypatch.setattr(
        services_helpers, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: _fake_account_tokens,
    )
    monkeypatch.setattr(
        accounts_service, "load_wrapped_app_credentials", lambda _provider: _fake_app_creds,
    )
    monkeypatch.setattr(
        emails_service, "load_wrapped_app_credentials", lambda _provider: _fake_app_creds,
    )
    monkeypatch.setattr(
        emails_service, "load_wrapped_account_tokens",
        lambda _mb, _acc, _prov: _fake_account_tokens,
    )

    monkeypatch.setattr(accounts_service, "save_account_tokens", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        accounts_service, "delete_account_tokens_for_records", lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(emails_service, "save_account_tokens", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        mailboxes_service, "delete_account_tokens_for_records", lambda *_a, **_kw: None,
    )

    return test_client_base


@pytest.fixture
def storage_path(temp_base_dir):
    return Path(temp_base_dir) / "test_storage.json"


@pytest.fixture
def mailbox_store():
    return json_store.mailbox_store


@pytest.fixture
def account_store():
    return json_store.account_store


@pytest.fixture
def token_path_dir(temp_base_dir, monkeypatch):
    token_dir = Path(temp_base_dir) / f"tokens_{uuid4().hex}"
    token_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MIA_GMAIL_TOKEN_PATH", str(token_dir))
    return token_dir


@pytest.fixture(autouse=True)
def isolated_storage(temp_base_dir, monkeypatch):
    original_mailboxes_path = json_store._MAILBOXES_PATH
    original_accounts_path = json_store._ACCOUNTS_PATH

    original_mailboxes = (
        original_mailboxes_path.read_text(encoding="utf-8")
        if original_mailboxes_path.exists()
        else None
    )
    original_accounts = (
        original_accounts_path.read_text(encoding="utf-8")
        if original_accounts_path.exists()
        else None
    )

    temp_root = Path(temp_base_dir) / f"storage_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_mailboxes = temp_root / "mailboxes.json"
    temp_accounts = temp_root / "accounts.json"

    temp_mailboxes.write_text(original_mailboxes or "[]", encoding="utf-8")
    temp_accounts.write_text(original_accounts or "[]", encoding="utf-8")

    monkeypatch.setattr(json_store, "_MAILBOXES_PATH", temp_mailboxes)
    monkeypatch.setattr(json_store, "_ACCOUNTS_PATH", temp_accounts)

    yield

    if original_mailboxes is not None and original_mailboxes_path.exists():
        current = original_mailboxes_path.read_text(encoding="utf-8")
        if current != original_mailboxes:
            original_mailboxes_path.write_text(original_mailboxes, encoding="utf-8")

    if original_accounts is not None and original_accounts_path.exists():
        current = original_accounts_path.read_text(encoding="utf-8")
        if current != original_accounts:
            original_accounts_path.write_text(original_accounts, encoding="utf-8")
