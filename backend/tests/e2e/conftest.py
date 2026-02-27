"""
E2E test fixtures — nothing faked, real providers and real APIs.
"""

from __future__ import annotations

import contextlib
import json
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
from api.database.repositories import session_repository as session_repo_module
from api.database.repositories import user_repository as user_repo_module
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


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(autouse=True, scope="module")
def _setup_google_client_id(monkeypatch_module):
    """Derive GOOGLE_CLIENT_ID from Gmail credentials for real OIDC verification."""
    creds_path = os.environ.get("MIA_GMAIL_CREDENTIALS_PATH", "")
    if not creds_path:
        return
    with open(creds_path) as f:
        creds_data = json.load(f)
    block = creds_data.get("installed") or creds_data.get("web") or creds_data
    client_id = block.get("client_id", "")
    if client_id:
        monkeypatch_module.setenv("GOOGLE_CLIENT_ID", client_id)


@pytest.fixture(scope="module")
def google_id_token():
    """Obtain a real Google id_token via interactive browser OAuth flow."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = os.environ["MIA_GMAIL_CREDENTIALS_PATH"]
    with open(creds_path) as f:
        creds_data = json.load(f)

    if "installed" not in creds_data and "web" not in creds_data:
        client_config = {"installed": creds_data}
    else:
        client_config = creds_data

    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=["openid", "email", "profile"],
    )
    flow.run_local_server(port=0)

    raw_id_token = flow.oauth2session.token.get("id_token")
    if not raw_id_token:
        pytest.fail("OAuth flow did not return an id_token. Ensure 'openid' scope is supported.")
    return raw_id_token


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
    monkeypatch_module.setattr(user_repo_module.connection, "get_connection", _get_conn)
    monkeypatch_module.setattr(session_repo_module.connection, "get_connection", _get_conn)

    yield

    conn.rollback()
    conn.close()
