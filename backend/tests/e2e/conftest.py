"""
E2E test fixtures — nothing faked, real providers and real APIs.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.database import connection as connection_module
from api.database.migrations.runner import ensure_schema_at_head
from api.database.repositories import account_repository as account_repo_module
from api.database.repositories import mailbox_repository as mailbox_repo_module
from api.database.security import token_store as token_store_impl_module


_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "api" / "database" / "alembic.ini"

try:
    from alembic import command
    from alembic.config import Config
except ModuleNotFoundError:  # pragma: no cover - fallback for offline environments
    command = None
    Config = None


@pytest.fixture(autouse=True, scope="session")
def skip_without_credentials():
    """Skip the entire E2E suite when credential env vars are missing."""
    required_env = {
        "MIA_GMAIL_CREDENTIALS_PATH": "file",
        "MIA_OUTLOOK_CREDENTIALS_PATH": "file",
        "DATABASE_URL": "any",
    }
    for var, kind in required_env.items():
        value = os.environ.get(var)
        if not value:
            pytest.skip(f"E2E credentials not configured: {var} not set")
        if kind == "file":
            if not Path(value).is_file():
                pytest.skip(f"E2E credentials not configured: {var} does not point to a file")


@pytest.fixture(autouse=True, scope="session")
def create_e2e_schema():
    """Ensure schema is at latest migration before E2E execution."""
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


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def e2e_client(isolated_e2e_db):
    """Real FastAPI TestClient — no fakes, no monkeypatching of providers."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True, scope="module")
def isolated_e2e_db(monkeypatch_module):
    """Redirect database operations to a transaction that is rolled back at teardown."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL is not set.")

    conn = psycopg2.connect(dsn=dsn)
    conn.autocommit = False

    @contextlib.contextmanager
    def _get_conn():
        try:
            yield conn
        except Exception:
            raise

    monkeypatch_module.setattr(connection_module, "get_connection", _get_conn)
    monkeypatch_module.setattr(mailbox_repo_module.connection, "get_connection", _get_conn)
    monkeypatch_module.setattr(account_repo_module.connection, "get_connection", _get_conn)
    monkeypatch_module.setattr(token_store_impl_module.connection, "get_connection", _get_conn)

    yield

    conn.rollback()
    conn.close()
