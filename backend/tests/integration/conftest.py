from __future__ import annotations

import contextlib
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest
from pydantic import SecretStr

from database import connection as connection_module
from database.migrations.runner import ensure_schema_at_head
from database.repositories import account_repository as account_repo_module
from database.repositories import email_metadata_repository as email_metadata_repo_module
from database.repositories import mailbox_repository as mailbox_repo_module
from database.repositories import session_repository as session_repo_module
from database.repositories import user_repository as user_repo_module
from api.routers.routers_helpers import require_session
from api.services import accounts_service, emails_service, services_helpers
from core.email import EmailManager
from tests.shared.email_fakes import FakeEmailClient, build_metadata

_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "database" / "alembic.ini"

TEST_USER_ID = "00000000-0000-4000-a000-000000000001"
TEST_USER_GOOGLE_SUB = "google-sub-test-user"
TEST_USER_EMAIL = "testuser@example.com"


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
                    to_regclass('public.accounts') IS NOT NULL
                """
            )
            mailbox_exists, account_exists = cur.fetchone()
            existing_tables = bool(mailbox_exists and account_exists)

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
    monkeypatch.setattr(user_repo_module.connection, "get_connection", _get_conn)
    monkeypatch.setattr(session_repo_module.connection, "get_connection", _get_conn)
    monkeypatch.setattr(email_metadata_repo_module.connection, "get_connection", _get_conn)

    yield conn

    conn.rollback()
    conn.close()


@pytest.fixture(autouse=True)
def _seed_test_user(isolated_db):
    """Seed a test user in the database so mailbox ownership works."""
    with isolated_db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, google_sub, email, name)
            VALUES (%(user_id)s, %(google_sub)s, %(email)s, %(name)s)
            ON CONFLICT (google_sub) DO UPDATE SET email = EXCLUDED.email
            """,
            {
                "user_id": TEST_USER_ID,
                "google_sub": TEST_USER_GOOGLE_SUB,
                "email": TEST_USER_EMAIL,
                "name": "Test User",
            },
        )


@pytest.fixture(scope="session", autouse=True)
def _override_require_session(app):
    """Override the require_session dependency for all integration tests."""
    app.dependency_overrides[require_session] = lambda: TEST_USER_ID
    yield
    app.dependency_overrides.pop(require_session, None)


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

    _noop_upsert = lambda *_a, **_kw: None
    monkeypatch.setattr(accounts_service.account_store, "upsert_tokens", _noop_upsert)
    monkeypatch.setattr(emails_service.account_store, "upsert_tokens", _noop_upsert)


@pytest.fixture
def test_client(test_client_base, sample_metadata, monkeypatch):
    def _build_manager(accounts):
        manager = EmailManager()
        for account in accounts:
            mailbox_id = str(account.get("mailbox_id") or "")
            account_id = str(account.get("account_id") or "")
            label = f"{mailbox_id}__{account_id}"
            manager.add_client(
                FakeEmailClient(
                    label,
                    metadata=sample_metadata,
                    auth_return={"access_token": "tok", "refresh_token": "ref"},
                )
            )
        return manager

    _apply_test_monkeypatches(monkeypatch, _build_manager)
    return test_client_base


@pytest.fixture
def failing_test_client(test_client_base, sample_metadata, monkeypatch, request):
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
                    metadata=sample_metadata,
                    auth_return={"access_token": "tok", "refresh_token": "ref"},
                    **client_kwargs,
                )
            )
        return manager

    _apply_test_monkeypatches(monkeypatch, _build_manager)
    return test_client_base
