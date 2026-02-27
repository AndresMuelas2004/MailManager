from __future__ import annotations

import contextlib
from collections.abc import Iterator

import psycopg2
import pytest

from database import lifecycle as lifecycle_module
from database.errors.exceptions import ConnectionPoolError, MigrationError
from tests.shared.database_fakes import FakeCursor


def test_warmup_raises_connection_pool_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("connection refused"))

    class _FakeConn:
        def cursor(self, *a, **kw):
            return cursor

    @contextlib.contextmanager
    def _get_connection() -> Iterator[_FakeConn]:
        yield _FakeConn()

    monkeypatch.setattr(lifecycle_module, "get_connection", _get_connection)

    with pytest.raises(ConnectionPoolError, match="Failed to warm up"):
        lifecycle_module.warmup_connection()


def test_warmup_raises_connection_pool_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("unexpected"))

    class _FakeConn:
        def cursor(self, *a, **kw):
            return cursor

    @contextlib.contextmanager
    def _get_connection() -> Iterator[_FakeConn]:
        yield _FakeConn()

    monkeypatch.setattr(lifecycle_module, "get_connection", _get_connection)

    with pytest.raises(ConnectionPoolError, match="RuntimeError"):
        lifecycle_module.warmup_connection()


def test_migration_failure_raises_migration_error(monkeypatch):
    monkeypatch.setenv("DB_AUTO_MIGRATE", "true")
    monkeypatch.setattr(
        lifecycle_module,
        "ensure_schema_at_head",
        lambda dsn: (_ for _ in ()).throw(RuntimeError("migration boom")),
    )

    import sys
    monkeypatch.setitem(sys.modules, "alembic", None)
    monkeypatch.setitem(sys.modules, "alembic.command", None)
    monkeypatch.setitem(sys.modules, "alembic.config", None)

    with pytest.raises(MigrationError, match="Failed to run startup database migrations"):
        lifecycle_module.run_startup_migrations_if_enabled()
