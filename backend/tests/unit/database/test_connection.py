from __future__ import annotations

import psycopg2
import pytest
from unittest.mock import MagicMock, patch

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


# ==================================================================
# get_connection — getconn errors and transaction semantics
# ==================================================================


class TestGetConnection:

    def test_getconn_psycopg2_error(self, monkeypatch):
        fake_pool = MagicMock()
        fake_pool.getconn.side_effect = psycopg2.OperationalError("exhausted")
        monkeypatch.setattr(connection_module, "_get_pool", lambda: fake_pool)

        with pytest.raises(ConnectionPoolError, match="Failed to get connection"):
            with connection_module.get_connection():
                pass

    def test_getconn_generic_error(self, monkeypatch):
        fake_pool = MagicMock()
        fake_pool.getconn.side_effect = RuntimeError("boom")
        monkeypatch.setattr(connection_module, "_get_pool", lambda: fake_pool)

        with pytest.raises(ConnectionPoolError, match="Unexpected pool error"):
            with connection_module.get_connection():
                pass

    def test_commits_on_success(self, monkeypatch):
        fake_pool = MagicMock()
        fake_conn = MagicMock()
        fake_pool.getconn.return_value = fake_conn
        monkeypatch.setattr(connection_module, "_get_pool", lambda: fake_pool)

        with connection_module.get_connection() as conn:
            pass

        fake_conn.commit.assert_called_once()
        fake_pool.putconn.assert_called_once_with(fake_conn)

    def test_rollback_on_exception(self, monkeypatch):
        fake_pool = MagicMock()
        fake_conn = MagicMock()
        fake_pool.getconn.return_value = fake_conn
        monkeypatch.setattr(connection_module, "_get_pool", lambda: fake_pool)

        with pytest.raises(ValueError):
            with connection_module.get_connection() as conn:
                raise ValueError("user error")

        fake_conn.rollback.assert_called_once()
        fake_pool.putconn.assert_called_once_with(fake_conn)


# ==================================================================
# close_pool
# ==================================================================


class TestClosePool:

    def test_closes_and_resets(self, monkeypatch):
        fake_pool = MagicMock()
        monkeypatch.setattr(connection_module, "_pool", fake_pool)
        connection_module.close_pool()
        fake_pool.closeall.assert_called_once()
        assert connection_module._pool is None

    def test_noop_when_none(self, monkeypatch):
        monkeypatch.setattr(connection_module, "_pool", None)
        connection_module.close_pool()
        assert connection_module._pool is None
