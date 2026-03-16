"""
E2E test fixtures — nothing faked, real providers and real APIs.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from database.migrations.runner import ensure_schema_at_head

from .e2e_config import TEST_USER_ID

_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "database" / "alembic.ini"

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
def e2e_client():
    """Real FastAPI TestClient — no fakes, no monkeypatching of providers."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def created_resources() -> dict[str, list[str]]:
    """Track temp resources for safety-net cleanup."""
    return {"mailbox_ids": [], "session_ids": []}


@pytest.fixture(autouse=True, scope="module")
def e2e_session(e2e_client, created_resources):
    """Create a real session in DB for the pre-existing test user, set cookie."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL is not set.")

    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    conn = psycopg2.connect(dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (session_id, user_id, expires_at)
                VALUES (%(session_id)s, %(user_id)s, %(expires_at)s)
                """,
                {
                    "session_id": session_id,
                    "user_id": TEST_USER_ID,
                    "expires_at": expires_at,
                },
            )
        conn.commit()
    finally:
        conn.close()

    created_resources["session_ids"].append(session_id)
    e2e_client.cookies.set("session_id", session_id)

    yield session_id

    # Safety-net cleanup: delete temp mailboxes and the test session
    cleanup_conn = psycopg2.connect(dsn=dsn)
    try:
        with cleanup_conn.cursor() as cur:
            for mid in created_resources["mailbox_ids"]:
                cur.execute("DELETE FROM mailboxes WHERE mailbox_id = %s", (mid,))
            for sid in created_resources["session_ids"]:
                cur.execute("DELETE FROM sessions WHERE session_id = %s", (sid,))
        cleanup_conn.commit()
    finally:
        cleanup_conn.close()


@pytest.fixture(scope="module")
def flow_state() -> dict[str, str]:
    """Shared dict for passing state between ordered tests."""
    return {}
