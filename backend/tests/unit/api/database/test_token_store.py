from __future__ import annotations

import contextlib

import pytest

from api.database.security import token_store as token_store_module
from api.errors.exceptions import AccountNotConnected, DatabaseError

Fernet = pytest.importorskip("cryptography.fernet").Fernet


class _FakeCursor:
    def __init__(self, *, fetchone_results=None, rowcounts=None):
        self._fetchone_results = list(fetchone_results or [])
        self._rowcounts = list(rowcounts or [])
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._rowcounts:
            self.rowcount = self._rowcounts.pop(0)

    def fetchone(self):
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, cursors):
        self._cursors = list(cursors)

    def cursor(self, *args, **kwargs):
        if not self._cursors:
            raise AssertionError("No fake cursor available.")
        return self._cursors.pop(0)


def _patch_connection(monkeypatch, cursors):
    conn = _FakeConnection(cursors)

    @contextlib.contextmanager
    def _get_connection():
        yield conn

    monkeypatch.setattr(token_store_module.connection, "get_connection", _get_connection)


def test_load_tokens_dual_read_plaintext_then_backfill(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "v1")

    select_cursor = _FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": "plain-access",
                "refresh_token": "plain-refresh",
                "access_token_encrypted": None,
                "refresh_token_encrypted": None,
                "encryption_key_id": None,
                "expiry": None,
                "scopes": ["scope-a"],
            }
        ]
    )
    backfill_cursor = _FakeCursor()
    _patch_connection(monkeypatch, [select_cursor, backfill_cursor])

    payload = token_store_module.load_account_tokens("mb1", "acc1", "GMAIL")

    assert payload["access_token"] == "plain-access"
    assert payload["refresh_token"] == "plain-refresh"
    assert payload["scopes"] == ["scope-a"]
    assert len(backfill_cursor.executed) == 1
    _, backfill_params = backfill_cursor.executed[0]
    assert backfill_params["provider"] == "gmail"
    assert backfill_params["access_token_encrypted"] is not None
    assert backfill_params["refresh_token_encrypted"] is not None


def test_load_tokens_plaintext_disallowed(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "false")

    select_cursor = _FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": "plain-access",
                "refresh_token": "plain-refresh",
                "access_token_encrypted": None,
                "refresh_token_encrypted": None,
                "encryption_key_id": None,
                "expiry": None,
                "scopes": None,
            }
        ]
    )
    _patch_connection(monkeypatch, [select_cursor])

    with pytest.raises(AccountNotConnected):
        token_store_module.load_account_tokens("mb1", "acc1", "gmail")


def test_save_tokens_requires_context_match(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "v1")

    save_cursor = _FakeCursor(rowcounts=[0])
    _patch_connection(monkeypatch, [save_cursor])

    with pytest.raises(DatabaseError):
        token_store_module.save_account_tokens(
            mailbox_id="mb1",
            account_id="acc1",
            provider="gmail",
            token_data={
                "access_token": "at",
                "refresh_token": "rt",
                "expiry": None,
                "scopes": ["scope-a"],
            },
        )


def test_load_tokens_uses_encrypted_columns(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "false")

    encrypted_access = token_store_module.token_crypto.encrypt_token("enc-access")
    encrypted_refresh = token_store_module.token_crypto.encrypt_token("enc-refresh")
    select_cursor = _FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": None,
                "refresh_token": None,
                "access_token_encrypted": encrypted_access,
                "refresh_token_encrypted": encrypted_refresh,
                "encryption_key_id": "v1",
                "expiry": None,
                "scopes": None,
            }
        ]
    )
    _patch_connection(monkeypatch, [select_cursor])

    payload = token_store_module.load_account_tokens("mb1", "acc1", "gmail")
    assert payload["access_token"] == "enc-access"
    assert payload["refresh_token"] == "enc-refresh"
