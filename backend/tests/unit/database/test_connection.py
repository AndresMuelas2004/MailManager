from __future__ import annotations

import psycopg2
import pytest

from database import connection as connection_module
from database.errors.exceptions import ConnectionPoolError


def test_psycopg2_error_on_pool_creation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setattr(connection_module, "_pool", None)
    monkeypatch.setattr(
        connection_module.pool,
        "ThreadedConnectionPool",
        _raise_factory(psycopg2.OperationalError("connection refused")),
    )

    with pytest.raises(ConnectionPoolError, match="Failed to create database connection pool"):
        connection_module._get_pool()


def test_generic_error_on_pool_creation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setattr(connection_module, "_pool", None)
    monkeypatch.setattr(
        connection_module.pool,
        "ThreadedConnectionPool",
        _raise_factory(RuntimeError("something unexpected")),
    )

    with pytest.raises(ConnectionPoolError, match="RuntimeError"):
        connection_module._get_pool()


def _raise_factory(exc: Exception):
    """Return a callable that raises *exc* when called with any args."""

    def _raise(*args, **kwargs):
        raise exc

    return _raise
