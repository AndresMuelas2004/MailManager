"""
PostgreSQL user repository.
"""

from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from database import connection
from database.contracts import UserStore
from database.queries import auth
from database.errors.exceptions import DatabaseError, QueryError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if result.get("user_id") is not None:
        result["user_id"] = str(result["user_id"])
    if result.get("created_at") is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result


class PgUserStore(UserStore):
    """
    PostgreSQL-backed user persistence.
    """

    def upsert(self, user: dict[str, Any]) -> dict[str, Any]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(auth.UPSERT_USER, user)
                    row = cur.fetchone()
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to upsert user.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected user upsert error ({type(exc).__name__}): {exc}"
            ) from exc
        return _row_to_dict(row)

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(auth.GET_USER_BY_ID, {"user_id": user_id})
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get user.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected user get error ({type(exc).__name__}): {exc}"
            ) from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def get_by_google_sub(self, google_sub: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(auth.GET_USER_BY_GOOGLE_SUB, {"google_sub": google_sub})
                    row = cur.fetchone()
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get user by google_sub.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected user get_by_google_sub error ({type(exc).__name__}): {exc}"
            ) from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def delete(self, user_id: str) -> bool:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(auth.DELETE_USER, {"user_id": user_id})
                    return cur.rowcount > 0
        except psycopg2.errors.InvalidTextRepresentation:
            return False
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete user.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected user delete error ({type(exc).__name__}): {exc}"
            ) from exc


user_store = PgUserStore()
