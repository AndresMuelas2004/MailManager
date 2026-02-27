"""
Database lifecycle helpers used during app startup.
"""

from __future__ import annotations

import psycopg2

from api.database.connection import get_connection
from api.database.migrations.runner import ensure_schema_at_head
from api.database.settings import (
    get_database_url,
    get_alembic_ini_path,
    is_startup_auto_migrate_enabled,
)
from api.errors.exceptions import ApiError, DatabaseConnectionError, DatabaseMigrationError


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
            ensure_schema_at_head(get_database_url())
            return True

        cfg = Config(str(get_alembic_ini_path()))
        command.upgrade(cfg, "head")
    except ApiError:
        raise
    except Exception as exc:
        raise DatabaseMigrationError(
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
    except ApiError:
        raise
    except psycopg2.Error as exc:
        raise DatabaseConnectionError(
            "Failed to warm up database connection."
        ) from exc
    except Exception as exc:
        raise DatabaseConnectionError(
            f"Unexpected warmup error ({type(exc).__name__}): {exc}"
        ) from exc
