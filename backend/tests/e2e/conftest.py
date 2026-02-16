"""
E2E test fixtures — nothing faked, real providers and real APIs.
"""

from __future__ import annotations

import contextlib
import os

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.database import db as db_module
from api.database import repository as repo_module
from api.database import token_store as token_store_module


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
            from pathlib import Path

            if not Path(value).is_file():
                pytest.skip(f"E2E credentials not configured: {var} does not point to a file")


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session")
def e2e_client(monkeypatch_session):
    """Real FastAPI TestClient — no fakes, no monkeypatching of providers."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True, scope="session")
def isolated_e2e_db(monkeypatch_session):
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

    monkeypatch_session.setattr(db_module, "get_connection", _get_conn)
    monkeypatch_session.setattr(repo_module, "get_connection", _get_conn)
    monkeypatch_session.setattr(token_store_module, "get_connection", _get_conn)

    yield

    conn.rollback()
    conn.close()
