"""
Shared PostgreSQL connection-pool utilities.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator

import psycopg2
from psycopg2 import pool

from database.settings import get_database_settings
from database.errors import ConnectionPoolError

logger = logging.getLogger(__name__)


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
            raise ConnectionPoolError(
                "Failed to create database connection pool."
            ) from exc
        except Exception as exc:
            raise ConnectionPoolError(
                f"Unexpected connection pool error ({type(exc).__name__}): {exc}"
            ) from exc
    return _pool


@contextlib.contextmanager
def get_connection() -> Iterator:
    """
    Yield one pooled connection and wrap operation in a transaction.
    """
    p = _get_pool()
    try:
        conn = p.getconn()
    except psycopg2.Error as exc:
        raise ConnectionPoolError(
            "Failed to get connection from pool."
        ) from exc
    except Exception as exc:
        raise ConnectionPoolError(
            f"Unexpected pool error ({type(exc).__name__}): {exc}"
        ) from exc
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            logger.warning("Rollback failed", exc_info=True)
        raise
    finally:
        p.putconn(conn)


def close_pool() -> None:
    """
    Close all pooled connections.
    """
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except psycopg2.Error as exc:
            raise ConnectionPoolError(
                "Failed to close database connection pool."
            ) from exc
        except Exception as exc:
            raise ConnectionPoolError(
                f"Unexpected pool close error ({type(exc).__name__}): {exc}"
            ) from exc
        finally:
            _pool = None
