import contextlib
import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest
from pydantic import SecretStr

from api.database import db as db_module
from api.database import repository as repo_module
from api.database import token_store as token_store_module
from api.services import accounts_service, emails_service, services_helpers
from core.email.email_manager import EmailManager

_UNIT_CONFTEST_PATH = (
    Path(__file__).resolve().parents[1] / "unit" / "core" / "conftest.py"
)

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "api" / "database" / "schema.sql"


def _load_unit_conftest():
    spec = spec_from_file_location("tests_unit_conftest", _UNIT_CONFTEST_PATH)
    module = module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Unable to load unit conftest module.")
    spec.loader.exec_module(module)
    return module


_unit_conftest = _load_unit_conftest()
FakeEmailClient = _unit_conftest.FakeEmailClient


_MAILBOX_URL = "/mailboxes"


def _setup_mailbox_and_account(client, provider: str = "gmail") -> tuple[str, str]:
    """Create a mailbox + account and return ``(mailbox_id, account_id)``."""
    mb = client.post(_MAILBOX_URL, json={"display_name": "Test MB"})
    mailbox_id = mb.json()["mailbox_id"]
    acc = client.post(
        f"{_MAILBOX_URL}/{mailbox_id}/accounts",
        json={"provider": provider, "display_label": f"test-{provider}"},
    )
    account_id = acc.json()["account_id"]
    return mailbox_id, account_id


@pytest.fixture
def setup_mailbox_and_account():
    """Factory fixture: returns a callable that creates a mailbox + account."""
    return _setup_mailbox_and_account


@pytest.fixture(scope="session")
def fake_client_class():
    return FakeEmailClient


@pytest.fixture(scope="session", autouse=True)
def create_test_schema():
    """Create tables once per test session."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL is not set.")
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Use a single transaction per test, rolled back for isolation."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    conn = psycopg2.connect(dsn=dsn)
    conn.autocommit = False

    @contextlib.contextmanager
    def _get_conn():
        try:
            yield conn
        except Exception:
            raise

    monkeypatch.setattr(db_module, "get_connection", _get_conn)
    monkeypatch.setattr(repo_module, "get_connection", _get_conn)
    monkeypatch.setattr(token_store_module, "get_connection", _get_conn)

    yield conn

    conn.rollback()
    conn.close()


def _apply_test_monkeypatches(monkeypatch, build_manager_fn):
    """Wire common monkeypatches shared by ``test_client`` and ``failing_test_client``."""
    _fake_app_creds = {"client_id": "fake", "client_secret": SecretStr("fake")}
    _fake_account_tokens = {
        "access_token": SecretStr("tok"),
        "refresh_token": SecretStr("ref"),
    }

    monkeypatch.setattr(services_helpers, "build_manager_for_accounts", build_manager_fn)
    monkeypatch.setattr(accounts_service, "build_manager_for_accounts", build_manager_fn)
    monkeypatch.setattr(emails_service, "build_manager_for_accounts", build_manager_fn)

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
    monkeypatch.setattr(emails_service, "save_account_tokens", lambda *_a, **_kw: None)


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

    _apply_test_monkeypatches(monkeypatch, _build_manager)
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

    _apply_test_monkeypatches(monkeypatch, _build_manager)
    return test_client_base
