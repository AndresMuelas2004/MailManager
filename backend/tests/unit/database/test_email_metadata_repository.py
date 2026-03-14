"""
Unit tests for PgEmailMetadataStore.

Follows the same pattern as test_mailbox_repository.py / test_account_repository.py:
monkeypatch get_connection to inject FakeCursors.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg2
import psycopg2.errors
import pytest

from database.repositories import email_metadata_repository as em_module
from database.errors.exceptions import ConnectionPoolError, QueryError
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error


def _stub_execute_values(cur, sql, rows, **kwargs):
    """Stub for psycopg2.extras.execute_values that records the call."""
    cur.executed.append((sql, rows))
    cur.rowcount = len(rows)


# ===== upsert_batch =====


def test_upsert_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("m1", "acc1", "t1", "a@b.com", "A", "subj", datetime.now(timezone.utc), False, "ALL_MAIL")]
    result = em_module.email_metadata_store.upsert_batch("acc1", rows)
    assert result == 1
    assert len(cursor.executed) == 1


def test_upsert_batch_empty_rows_returns_zero(monkeypatch):
    result = em_module.email_metadata_store.upsert_batch("acc1", [])
    assert result == 0


def test_upsert_batch_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("connection lost")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to upsert email metadata"):
        em_module.email_metadata_store.upsert_batch("acc1", [("m1",)])


def test_upsert_batch_generic_exception_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.upsert_batch("acc1", [("m1",)])


def test_upsert_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.upsert_batch("acc1", [("m1",)])


# ===== list_by_account =====


def test_list_by_account_happy_path(monkeypatch):
    rows = [
        {"provider_message_id": "m1", "account_id": "acc1", "thread_id": "t1",
         "from_email": "a@b.com", "from_name": "A", "subject": "s",
         "received_at": datetime.now(timezone.utc), "is_read": False, "box": "ALL_MAIL"},
    ]
    cursor = FakeCursor(fetchall_results=[rows])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.list_by_account("acc1")
    assert len(result) == 1
    assert result[0]["provider_message_id"] == "m1"


def test_list_by_account_invalid_text_returns_empty(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.list_by_account("not-a-uuid") == []


def test_list_by_account_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list email metadata"):
        em_module.email_metadata_store.list_by_account("acc1")


def test_list_by_account_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.list_by_account("acc1")


def test_list_by_account_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.list_by_account("acc1")


# ===== delete_by_account =====


def test_delete_by_account_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    em_module.email_metadata_store.delete_by_account("acc1")
    assert len(cursor.executed) == 1


def test_delete_by_account_invalid_text_noop(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    em_module.email_metadata_store.delete_by_account("not-a-uuid")


def test_delete_by_account_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to delete email metadata"):
        em_module.email_metadata_store.delete_by_account("acc1")


def test_delete_by_account_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.delete_by_account("acc1")


def test_delete_by_account_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.delete_by_account("acc1")


# ===== delete_batch_by_message_ids =====


def test_delete_batch_happy_path(monkeypatch):
    cursor = FakeCursor(rowcounts=[3])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.delete_batch_by_message_ids("acc1", ["m1", "m2", "m3"])
    assert result == 3


def test_delete_batch_empty_returns_zero(monkeypatch):
    assert em_module.email_metadata_store.delete_batch_by_message_ids("acc1", []) == 0


def test_delete_batch_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to delete email metadata batch"):
        em_module.email_metadata_store.delete_batch_by_message_ids("acc1", ["m1"])


def test_delete_batch_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.delete_batch_by_message_ids("acc1", ["m1"])


def test_delete_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.delete_batch_by_message_ids("acc1", ["m1"])


# ===== update_labels_batch =====


def test_update_labels_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("m1", "acc1", True, "INBOX")]
    result = em_module.email_metadata_store.update_labels_batch("acc1", rows)
    assert result == 1
    assert len(cursor.executed) == 1


def test_update_labels_batch_empty_returns_zero(monkeypatch):
    assert em_module.email_metadata_store.update_labels_batch("acc1", []) == 0


def test_update_labels_batch_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("connection lost")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to update email metadata labels"):
        em_module.email_metadata_store.update_labels_batch("acc1", [("m1",)])


def test_update_labels_batch_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.update_labels_batch("acc1", [("m1",)])


def test_update_labels_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.update_labels_batch("acc1", [("m1",)])


# ===== list_provider_message_ids =====


def test_list_provider_message_ids_happy_path(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[("m1",), ("m2",)]])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.list_provider_message_ids("acc1")
    assert result == ["m1", "m2"]
    assert len(cursor.executed) == 1


def test_list_provider_message_ids_empty_result(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[]])
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.list_provider_message_ids("acc1") == []


def test_list_provider_message_ids_invalid_text_returns_empty(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.list_provider_message_ids("not-a-uuid") == []


def test_list_provider_message_ids_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list provider message IDs"):
        em_module.email_metadata_store.list_provider_message_ids("acc1")


def test_list_provider_message_ids_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.list_provider_message_ids("acc1")
