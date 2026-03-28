"""
Database lifecycle helpers used during app startup.
"""

from __future__ import annotations

import psycopg2

from database.connection import get_connection
from database.migrations.runner import ensure_schema_at_head
from database.settings import (
    get_database_url,
    get_alembic_ini_path,
    is_startup_auto_migrate_enabled,
)
from database.errors import ConnectionPoolError, DatabaseError, MigrationError


def run_startup_migrations_if_enabled() -> bool:
    """
    Run Alembic migrations when DB_AUTO_MIGRATE is explicitly enabled.
    """
    if not is_startup_auto_migrate_enabled():
        return False
    try:
        try:
            from alembic import command
            from alembic.config import Config
        except ModuleNotFoundError:
            # Alembic not installed — fall back to the DDL-based runner.
            ensure_schema_at_head(get_database_url())
            return True

        cfg = Config(str(get_alembic_ini_path()))
        command.upgrade(cfg, "head")
    except DatabaseError:
        raise
    except Exception as exc:
        raise MigrationError(
            "Failed to run startup database migrations."
        ) from exc
    return True


def warmup_connection() -> None:
    """
    Validate DB reachability without mutating schema.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except DatabaseError:
        raise
    except psycopg2.Error as exc:
        raise ConnectionPoolError(
            "Failed to warm up database connection."
        ) from exc
    except Exception as exc:
        raise ConnectionPoolError(
            f"Unexpected warmup error ({type(exc).__name__}): {exc}"
        ) from exc
