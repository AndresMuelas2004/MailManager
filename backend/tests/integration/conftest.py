import contextlib
import os
from pathlib import Path

import psycopg2
import pytest
from pydantic import SecretStr

from api.database import connection as connection_module
from api.database.migrations.runner import ensure_schema_at_head
from api.database.repositories import account_repository as account_repo_module
from api.database.repositories import mailbox_repository as mailbox_repo_module
from api.database.security import token_store as token_store_impl_module
from api.services import accounts_service, emails_service, services_helpers
from core.email.email_manager import EmailManager
from tests.shared.email_fakes import FakeEmailClient

_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "api" / "database" / "alembic.ini"


try:
    from alembic import command
    from alembic.config import Config
except ModuleNotFoundError:  # pragma: no cover - fallback for offline environments
    command = None
    Config = None


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
    """Create schema via Alembic once per test session."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL is not set.")

    existing_tables = False
    has_alembic_version = False
    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    to_regclass('public.mailboxes') IS NOT NULL,
                    to_regclass('public.accounts') IS NOT NULL,
                    to_regclass('public.tokens') IS NOT NULL
                """
            )
            mailbox_exists, account_exists, token_exists = cur.fetchone()
            existing_tables = bool(mailbox_exists and account_exists and token_exists)

            cur.execute("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            has_alembic_version = bool(cur.fetchone()[0])
    finally:
        conn.close()

    if command is None or Config is None:
        ensure_schema_at_head(dsn)
        return

    cfg = Config(str(_ALEMBIC_INI_PATH))
    if existing_tables and not has_alembic_version:
        command.stamp(cfg, "0001_initial_schema")
    command.upgrade(cfg, "head")


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

    monkeypatch.setattr(connection_module, "get_connection", _get_conn)
    monkeypatch.setattr(mailbox_repo_module.connection, "get_connection", _get_conn)
    monkeypatch.setattr(account_repo_module.connection, "get_connection", _get_conn)
    monkeypatch.setattr(token_store_impl_module.connection, "get_connection", _get_conn)

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
