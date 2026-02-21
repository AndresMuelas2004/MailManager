"""
Shared PostgreSQL connection-pool utilities.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import psycopg2
from psycopg2 import pool

from api.database.settings import get_database_settings
from api.errors.exceptions import DatabaseError


_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        cfg = get_database_settings()
        try:
            _pool = pool.ThreadedConnectionPool(
                minconn=cfg.pool_min_conn,
                maxconn=cfg.pool_max_conn,
                dsn=cfg.database_url,
                connect_timeout=cfg.connect_timeout_seconds,
                application_name=cfg.application_name,
            )
        except psycopg2.Error as exc:
            raise DatabaseError("Failed to create database connection pool.") from exc
    return _pool


@contextlib.contextmanager
def get_connection() -> Iterator:
    """
    Yield one pooled connection and wrap operation in a transaction.
    """
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def close_pool() -> None:
    """
    Close all pooled connections.
    """
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None

