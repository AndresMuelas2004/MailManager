"""
E2E test fixtures — nothing faked, real providers and real APIs.
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.storage import json_store


@pytest.fixture(autouse=True, scope="session")
def skip_without_credentials():
    """Skip the entire E2E suite when credential env vars are missing."""
    required_env = {
        "MIA_GMAIL_CREDENTIALS_PATH": "file",
        "MIA_OUTLOOK_CREDENTIALS_PATH": "file",
        "MIA_TOKEN_PATH": "dir",
    }
    for var, kind in required_env.items():
        value = os.environ.get(var)
        if not value:
            pytest.skip(f"E2E credentials not configured: {var} not set")
        path = Path(value)
        if kind == "file" and not path.is_file():
            pytest.skip(f"E2E credentials not configured: {var} does not point to a file")
        if kind == "dir" and not path.is_dir():
            pytest.skip(f"E2E credentials not configured: {var} does not point to a directory")


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
def isolated_e2e_storage(monkeypatch_session):
    """Redirect JSON storage to a temp dir so real data files are never touched."""
    with TemporaryDirectory() as tempdir:
        temp_root = Path(tempdir) / f"e2e_storage_{uuid4().hex}"
        temp_root.mkdir(parents=True, exist_ok=True)

        temp_mailboxes = temp_root / "mailboxes.json"
        temp_accounts = temp_root / "accounts.json"
        temp_mailboxes.write_text("[]", encoding="utf-8")
        temp_accounts.write_text("[]", encoding="utf-8")

        monkeypatch_session.setattr(json_store, "_MAILBOXES_PATH", temp_mailboxes)
        monkeypatch_session.setattr(json_store, "_ACCOUNTS_PATH", temp_accounts)

        yield
