"""
Unit tests for PgEmailContentStore.

Follows the same pattern as test_email_metadata_repository.py:
monkeypatch get_connection to inject FakeCursors.
"""

from __future__ import annotations

import psycopg2
import psycopg2.errors
import pytest

from database.repositories import email_content_repository as ec_module
from database.errors.exceptions import ConnectionPoolError, QueryError
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error


# ===== get =====


def test_get_happy_path(monkeypatch):
    row = {"html_body": "<p>hello</p>", "text_body": "hello", "fetched_at": "2024-01-01"}
    cursor = FakeCursor(fetchone_results=[row])
    patch_connection(monkeypatch, ec_module, [cursor])

    result = ec_module.email_content_store.get("acc1", "m1")
    assert result is not None
    assert result["html_body"] == "<p>hello</p>"
    assert result["text_body"] == "hello"
    assert len(cursor.executed) == 1


def test_get_returns_none_when_no_row(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    patch_connection(monkeypatch, ec_module, [cursor])

    result = ec_module.email_content_store.get("acc1", "m1")
    assert result is None


def test_get_invalid_uuid_returns_none(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, ec_module, [cursor])

    result = ec_module.email_content_store.get("not-a-uuid", "m1")
    assert result is None


def test_get_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, ec_module, [cursor])

    with pytest.raises(QueryError, match="Failed to get email content"):
        ec_module.email_content_store.get("acc1", "m1")


def test_get_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, ec_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        ec_module.email_content_store.get("acc1", "m1")


def test_get_propagates_database_error(monkeypatch):
    patch_connection_error(monkeypatch, ec_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        ec_module.email_content_store.get("acc1", "m1")


# ===== upsert =====


def test_upsert_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, ec_module, [cursor])

    ec_module.email_content_store.upsert("acc1", "m1", "<p>hi</p>", "hi")
    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert params["account_id"] == "acc1"
    assert params["provider_message_id"] == "m1"
    assert params["html_body"] == "<p>hi</p>"
    assert params["text_body"] == "hi"


def test_upsert_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, ec_module, [cursor])

    with pytest.raises(QueryError, match="Failed to upsert email content"):
        ec_module.email_content_store.upsert("acc1", "m1", None, None)


def test_upsert_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, ec_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        ec_module.email_content_store.upsert("acc1", "m1", None, None)


def test_upsert_propagates_database_error(monkeypatch):
    patch_connection_error(monkeypatch, ec_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        ec_module.email_content_store.upsert("acc1", "m1", None, None)
