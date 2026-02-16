"""
PostgreSQL connection pool and database initialization.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import psycopg2
from psycopg2 import pool

from api.database.config import get_database_url
from api.errors.exceptions import StorageError

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        try:
            _pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=get_database_url(),
            )
        except psycopg2.Error as exc:
            raise StorageError("Failed to create database connection pool.") from exc
    return _pool


@contextlib.contextmanager
def get_connection():
    """
    Yield a connection from the pool. Commits on success, rolls back on error.
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


def init_db() -> None:
    """
    Execute schema.sql to create tables if they do not exist.
    """
    ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)


def close_pool() -> None:
    """
    Close all connections in the pool. Call on application shutdown.
    """
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
