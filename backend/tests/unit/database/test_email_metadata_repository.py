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


# ===== get_trash_emails_by_ids =====


def test_get_trash_emails_by_ids_happy_path(monkeypatch):
    rows = [
        {"provider_message_id": "m1", "account_id": "acc1", "box": "TRASH", "previous_box": "ALL_MAIL"},
    ]
    cursor = FakeCursor(fetchall_results=[rows])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.get_trash_emails_by_ids("acc1", ["m1"])
    assert len(result) == 1
    assert result[0]["provider_message_id"] == "m1"


def test_get_trash_emails_by_ids_empty_ids_returns_empty(monkeypatch):
    assert em_module.email_metadata_store.get_trash_emails_by_ids("acc1", []) == []


def test_get_trash_emails_by_ids_invalid_text_returns_empty(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.get_trash_emails_by_ids("not-uuid", ["m1"]) == []


def test_get_trash_emails_by_ids_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to get trash emails"):
        em_module.email_metadata_store.get_trash_emails_by_ids("acc1", ["m1"])


def test_get_trash_emails_by_ids_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.get_trash_emails_by_ids("acc1", ["m1"])


def test_get_trash_emails_by_ids_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.get_trash_emails_by_ids("acc1", ["m1"])


# ===== mark_as_deleted_batch =====


def test_mark_as_deleted_batch_happy_path(monkeypatch):
    cursor = FakeCursor(rowcounts=[2])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.mark_as_deleted_batch("acc1", ["m1", "m2"])
    assert result == 2


def test_mark_as_deleted_batch_empty_returns_zero(monkeypatch):
    assert em_module.email_metadata_store.mark_as_deleted_batch("acc1", []) == 0


def test_mark_as_deleted_batch_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to mark emails as deleted"):
        em_module.email_metadata_store.mark_as_deleted_batch("acc1", ["m1"])


def test_mark_as_deleted_batch_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.mark_as_deleted_batch("acc1", ["m1"])


def test_mark_as_deleted_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.mark_as_deleted_batch("acc1", ["m1"])


# ===== restore_from_trash_batch =====


def test_restore_from_trash_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("old_m1", "new_m1", "acc1")]
    result = em_module.email_metadata_store.restore_from_trash_batch("acc1", rows)
    assert result == 1
    assert len(cursor.executed) == 1


def test_restore_from_trash_batch_empty_returns_zero(monkeypatch):
    assert em_module.email_metadata_store.restore_from_trash_batch("acc1", []) == 0


def test_restore_from_trash_batch_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("connection lost")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to restore emails from trash"):
        em_module.email_metadata_store.restore_from_trash_batch("acc1", [("m1", "m1", "acc1")])


def test_restore_from_trash_batch_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.restore_from_trash_batch("acc1", [("m1", "m1", "acc1")])


def test_restore_from_trash_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.restore_from_trash_batch("acc1", [("m1", "m1", "acc1")])


# ===== restore_from_trash_discovered_batch =====


def test_restore_from_trash_discovered_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("old_m1", "new_m1", "acc1", "SENT")]
    result = em_module.email_metadata_store.restore_from_trash_discovered_batch("acc1", rows)
    assert result == 1
    assert len(cursor.executed) == 1


def test_restore_from_trash_discovered_batch_empty_returns_zero(monkeypatch):
    assert em_module.email_metadata_store.restore_from_trash_discovered_batch("acc1", []) == 0


def test_restore_from_trash_discovered_batch_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("connection lost")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to restore emails with discovered box"):
        em_module.email_metadata_store.restore_from_trash_discovered_batch(
            "acc1", [("m1", "m1", "acc1", "SENT")],
        )


def test_restore_from_trash_discovered_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.restore_from_trash_discovered_batch(
            "acc1", [("m1", "m1", "acc1", "SENT")],
        )


# ===== move_to_trash_batch =====


def test_move_to_trash_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("m1", "m1", "acc1"), ("m2", "m2", "acc1")]
    result = em_module.email_metadata_store.move_to_trash_batch("acc1", rows)
    assert result == 2
    assert len(cursor.executed) == 1


def test_move_to_trash_batch_empty_returns_zero(monkeypatch):
    assert em_module.email_metadata_store.move_to_trash_batch("acc1", []) == 0


def test_move_to_trash_batch_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("fail")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to move emails to trash"):
        em_module.email_metadata_store.move_to_trash_batch("acc1", [("m1", "m1", "acc1")])


def test_move_to_trash_batch_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.move_to_trash_batch("acc1", [("m1", "m1", "acc1")])


def test_move_to_trash_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.move_to_trash_batch("acc1", [("m1", "m1", "acc1")])


# ===== update_read_status_batch =====


def test_update_read_status_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("m1", "acc1", True), ("m2", "acc1", True)]
    result = em_module.email_metadata_store.update_read_status_batch("acc1", rows)
    assert result == 2
    assert len(cursor.executed) == 1


def test_update_read_status_batch_empty_returns_zero(monkeypatch):
    result = em_module.email_metadata_store.update_read_status_batch("acc1", [])
    assert result == 0


def test_update_read_status_batch_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("connection lost")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to update email read status"):
        em_module.email_metadata_store.update_read_status_batch("acc1", [("m1",)])


def test_update_read_status_batch_propagates_database_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.update_read_status_batch("acc1", [("m1",)])


# ===== update_spam_status_batch =====


def test_update_spam_status_batch_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])
    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _stub_execute_values)

    rows = [("old_m1", "acc1", "new_m1", "SPAM"), ("old_m2", "acc1", "new_m2", "SPAM")]
    result = em_module.email_metadata_store.update_spam_status_batch("acc1", rows)
    assert result == 2
    assert len(cursor.executed) == 1


def test_update_spam_status_batch_empty_returns_zero(monkeypatch):
    result = em_module.email_metadata_store.update_spam_status_batch("acc1", [])
    assert result == 0


def test_update_spam_status_batch_psycopg2_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise psycopg2.OperationalError("connection lost")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="Failed to update email spam status"):
        em_module.email_metadata_store.update_spam_status_batch("acc1", [("old_m1",)])


def test_update_spam_status_batch_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, em_module, [cursor])

    def _raise_execute_values(cur, sql, rows, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(em_module.psycopg2.extras, "execute_values", _raise_execute_values)

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.update_spam_status_batch("acc1", [("old_m1",)])


def test_update_spam_status_batch_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.update_spam_status_batch("acc1", [("old_m1",)])


# ===== list_by_account_and_box =====


def test_list_by_account_and_box_happy_path(monkeypatch):
    rows = [
        {"provider_message_id": "m1", "account_id": "acc1", "thread_id": "t1",
         "from_email": "a@b.com", "from_name": "A", "subject": "s",
         "received_at": datetime.now(timezone.utc), "is_read": False, "box": "SENT"},
    ]
    cursor = FakeCursor(fetchall_results=[rows])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.list_by_account_and_box("acc1", "SENT")
    assert len(result) == 1
    assert result[0]["provider_message_id"] == "m1"
    assert result[0]["box"] == "SENT"


def test_list_by_account_and_box_invalid_text_returns_empty(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.list_by_account_and_box("not-a-uuid", "ALL_MAIL") == []


def test_list_by_account_and_box_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list email metadata by account and box"):
        em_module.email_metadata_store.list_by_account_and_box("acc1", "ALL_MAIL")


def test_list_by_account_and_box_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.list_by_account_and_box("acc1", "ALL_MAIL")


def test_list_by_account_and_box_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.list_by_account_and_box("acc1", "ALL_MAIL")


# ===== list_by_mailbox_and_box =====


def test_list_by_mailbox_and_box_happy_path(monkeypatch):
    rows = [
        {"provider_message_id": "m1", "account_id": "acc1", "thread_id": "t1",
         "from_email": "a@b.com", "from_name": "A", "subject": "s",
         "received_at": datetime.now(timezone.utc), "is_read": True, "box": "SPAM"},
        {"provider_message_id": "m2", "account_id": "acc2", "thread_id": "t2",
         "from_email": "c@d.com", "from_name": "C", "subject": "s2",
         "received_at": datetime.now(timezone.utc), "is_read": False, "box": "SPAM"},
    ]
    cursor = FakeCursor(fetchall_results=[rows])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.list_by_mailbox_and_box("mbx1", "SPAM")
    assert len(result) == 2
    assert result[0]["account_id"] == "acc1"
    assert result[1]["account_id"] == "acc2"


def test_list_by_mailbox_and_box_invalid_text_returns_empty(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.list_by_mailbox_and_box("not-a-uuid", "ALL_MAIL") == []


def test_list_by_mailbox_and_box_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list email metadata by mailbox and box"):
        em_module.email_metadata_store.list_by_mailbox_and_box("mbx1", "ALL_MAIL")


def test_list_by_mailbox_and_box_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.list_by_mailbox_and_box("mbx1", "ALL_MAIL")


def test_list_by_mailbox_and_box_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.list_by_mailbox_and_box("mbx1", "ALL_MAIL")
