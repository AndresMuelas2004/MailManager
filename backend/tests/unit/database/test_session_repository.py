from __future__ import annotations

from datetime import datetime, timezone

import psycopg2
import psycopg2.errors
import pytest

from database.repositories import session_repository as session_module
from database.errors.exceptions import ConnectionPoolError, QueryError
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error


def _fake_row(
    session_id: str = "sess1",
    user_id: str = "u1",
) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "expires_at": datetime(2025, 2, 1, tzinfo=timezone.utc),
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }


# ===== create =====


def test_create_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, session_module, [cursor])

    result = session_module.session_store.create(
        {"session_id": "sess1", "user_id": "u1", "expires_at": "2025-02-01T00:00:00+00:00"}
    )
    assert result["session_id"] == "sess1"
    assert isinstance(result["expires_at"], str)


def test_create_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="Failed to create session"):
        session_module.session_store.create(
            {"session_id": "sess1", "user_id": "u1", "expires_at": "2025-02-01"}
        )


def test_create_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        session_module.session_store.create(
            {"session_id": "sess1", "user_id": "u1", "expires_at": "2025-02-01"}
        )


def test_create_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, session_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        session_module.session_store.create(
            {"session_id": "sess1", "user_id": "u1", "expires_at": "2025-02-01"}
        )


# ===== get =====


def test_get_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, session_module, [cursor])

    result = session_module.session_store.get("sess1")
    assert result["session_id"] == "sess1"
    assert result["user_id"] == "u1"


def test_get_returns_none_when_not_found(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    patch_connection(monkeypatch, session_module, [cursor])

    assert session_module.session_store.get("sess1") is None


def test_get_returns_none_on_invalid_text(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, session_module, [cursor])

    assert session_module.session_store.get("not-a-uuid") is None


def test_get_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="Failed to get session"):
        session_module.session_store.get("sess1")


def test_get_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        session_module.session_store.get("sess1")


# ===== delete =====


def test_delete_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, session_module, [cursor])

    session_module.session_store.delete("sess1")
    assert len(cursor.executed) == 1


def test_delete_noop_on_invalid_text(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, session_module, [cursor])

    session_module.session_store.delete("not-a-uuid")


def test_delete_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="Failed to delete session"):
        session_module.session_store.delete("sess1")


def test_delete_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("unexpected"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        session_module.session_store.delete("sess1")


# ===== delete_expired =====


def test_delete_expired_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, session_module, [cursor])

    session_module.session_store.delete_expired()
    assert len(cursor.executed) == 1


def test_delete_expired_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="Failed to delete expired sessions"):
        session_module.session_store.delete_expired()


def test_delete_expired_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, session_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        session_module.session_store.delete_expired()
