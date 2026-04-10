"""
PostgreSQL draft repository.
"""
from __future__ import annotations

from typing import Any

import psycopg2.errors
import psycopg2.extras

from database import connection
from database.contracts import DraftStore
from database.queries import drafts as queries
from database.errors import QueryError


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a psycopg2 RealDict row into a serializable dict."""
    result = dict(row)
    if result.get("account_id") is not None:
        result["account_id"] = str(result["account_id"])
    for key in ("to_recipients", "cc_recipients", "bcc_recipients"):
        if result.get(key) is None:
            result[key] = []
    return result


class PgDraftStore(DraftStore):
    """
    PostgreSQL-backed draft persistence.
    """

    def create(self, draft: dict[str, Any]) -> dict[str, Any]:
        try:
            with connection.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(queries.INSERT_DRAFT, draft)
                    row = cur.fetchone()
        except psycopg2.Error as exc:
            raise QueryError("Failed to create draft.") from exc
        except Exception as exc:
            raise QueryError(
                f"Unexpected draft create error ({type(exc).__name__}): {exc}"
            ) from exc
        return _row_to_dict(row)


draft_store = PgDraftStore()
