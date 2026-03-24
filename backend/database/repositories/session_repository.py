"""
PostgreSQL session repository.
"""

from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from database import connection
from database.contracts import SessionStore
from database.queries import auth
from database.errors import DatabaseError, QueryError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if result.get("session_id") is not None:
        result["session_id"] = str(result["session_id"])
    if result.get("user_id") is not None:
        result["user_id"] = str(result["user_id"])
    if result.get("expires_at") is not None:
        result["expires_at"] = result["expires_at"].isoformat()
    if result.get("created_at") is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result


class PgSessionStore(SessionStore):
    """
    PostgreSQL-backed session persistence.
    """

    def create(self, session: dict[str, Any]) -> dict[str, Any]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(auth.INSERT_SESSION, session)
                    row = cur.fetchone()
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to create session.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected session create error ({type(exc).__name__}): {exc}"
            ) from exc
        return _row_to_dict(row)

    def get(self, session_id: str) -> dict[str, Any] | None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(auth.GET_VALID_SESSION, {"session_id": session_id})
                    row = cur.fetchone()
        except psycopg2.errors.InvalidTextRepresentation:
            return None
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to get session.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected session get error ({type(exc).__name__}): {exc}"
            ) from exc
        if row is None:
            return None
        return _row_to_dict(row)

    def delete(self, session_id: str) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(auth.DELETE_SESSION, {"session_id": session_id})
        except psycopg2.errors.InvalidTextRepresentation:
            return
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete session.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected session delete error ({type(exc).__name__}): {exc}"
            ) from exc

    def delete_expired(self) -> None:
        try:
            with connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(auth.DELETE_EXPIRED_SESSIONS)
        except DatabaseError:
            raise
        except psycopg2.Error as exc:
            raise QueryError("Failed to delete expired sessions.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected session delete_expired error ({type(exc).__name__}): {exc}"
            ) from exc


session_store = PgSessionStore()
