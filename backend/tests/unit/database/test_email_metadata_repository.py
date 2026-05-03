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
from database.repositories.email_metadata_repository import _escape_like
from database.errors.exceptions import ConnectionPoolError, QueryError
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error


def _stub_execute_values(cur, sql, rows, **kwargs):
    """Stub for psycopg2.extras.execute_values that records the call."""
    cur.executed.append((sql, rows))
    cur.rowcount = len(rows)


# ===== _escape_like =====


def test_escape_like_passes_normal_text_unchanged():
    assert _escape_like("hello") == "hello"
    assert _escape_like("Sprint planning") == "Sprint planning"


def test_escape_like_handles_empty_string():
    assert _escape_like("") == ""


def test_escape_like_escapes_percent():
    assert _escape_like("50%") == "50\\%"


def test_escape_like_escapes_underscore():
    assert _escape_like("a_b") == "a\\_b"


def test_escape_like_escapes_backslash_first():
    # The backslash must be escaped first; otherwise %/_ escapes get re-escaped.
    assert _escape_like("a\\b") == "a\\\\b"


def test_escape_like_escapes_combined_metacharacters():
    # All three metacharacters present at once: backslash → \\, then % → \%, then _ → \_
    assert _escape_like("a\\b%c_d") == "a\\\\b\\%c\\_d"


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


# ===== list_filtered =====


def _row(**overrides):
    base = {
        "provider_message_id": "m1", "account_id": "acc1", "thread_id": "t1",
        "from_email": "a@b.com", "from_name": "A", "subject": "s",
        "received_at": datetime.now(timezone.utc), "is_read": False, "box": "ALL_MAIL",
    }
    base.update(overrides)
    return base


def test_list_filtered_empty_account_ids_returns_empty_without_db_call(monkeypatch):
    # If account_ids is empty, the repository must short-circuit BEFORE touching
    # the connection — otherwise a misconfigured deployment could leak rows of
    # an unauthorized mailbox. Inject an exploding connection to assert no
    # cursor is requested.
    def _explode():
        raise AssertionError("get_connection must not be called for empty account_ids")

    monkeypatch.setattr(em_module.connection, "get_connection", _explode)
    assert em_module.email_metadata_store.list_filtered([], "ALL_MAIL", [], 200, 0) == []


def test_list_filtered_no_tokens_omits_search_predicate(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[_row()]])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.list_filtered(
        ["acc1"], "ALL_MAIL", [], 200, 0,
    )
    assert len(result) == 1
    sql, params = cursor.executed[0]
    # No search predicate when tokens are empty: ILIKE/unaccent must not appear.
    assert "ILIKE" not in sql
    assert "unaccent" not in sql
    # Base predicate parameters are passed through as named placeholders.
    assert params["account_ids"] == ["acc1"]
    assert params["box"] == "ALL_MAIL"
    assert params["limit"] == 200
    assert params["offset"] == 0
    # No search-token placeholders.
    assert "tok0" not in params


def test_list_filtered_with_tokens_builds_and_block_with_named_placeholders(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[]])
    patch_connection(monkeypatch, em_module, [cursor])

    em_module.email_metadata_store.list_filtered(
        ["acc1", "acc2"], "ALL_MAIL", ["foo", "bar"], 50, 10,
    )
    sql, params = cursor.executed[0]
    # Per-token placeholders must follow the tok0/tok1/... naming scheme.
    assert params["tok0"] == "%foo%"
    assert params["tok1"] == "%bar%"
    # Each token contributes a 3-column OR block joined by AND.
    assert sql.count("ILIKE") == 6  # 3 columns × 2 tokens
    assert sql.count("unaccent(lower(coalesce(subject, '')))") == 2
    assert sql.count("unaccent(lower(coalesce(from_email, '')))") == 2
    assert sql.count("unaccent(lower(coalesce(from_name, '')))") == 2
    # Tokens are AND-combined: there must be exactly two parenthesised blocks
    # joined by " AND " inside the generated predicate.
    assert " AND " in sql


def test_list_filtered_escapes_token_metacharacters_before_wrapping(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[]])
    patch_connection(monkeypatch, em_module, [cursor])

    em_module.email_metadata_store.list_filtered(
        ["acc1"], "ALL_MAIL", ["50%_off\\bar"], 200, 0,
    )
    _, params = cursor.executed[0]
    # The token is wrapped with % on both sides AFTER escaping. The original
    # %, _ and \ inside the user input must arrive at the DB pre-escaped so
    # they do not act as ILIKE metacharacters.
    assert params["tok0"] == "%50\\%\\_off\\\\bar%"


def test_list_filtered_invalid_text_returns_empty(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.list_filtered(
        ["not-a-uuid"], "ALL_MAIL", [], 200, 0,
    ) == []


def test_list_filtered_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list filtered email metadata"):
        em_module.email_metadata_store.list_filtered(["acc1"], "ALL_MAIL", [], 200, 0)


def test_list_filtered_generic_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.list_filtered(["acc1"], "ALL_MAIL", [], 200, 0)


def test_list_filtered_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.list_filtered(["acc1"], "ALL_MAIL", [], 200, 0)


def test_list_filtered_returns_dicts_for_each_row(monkeypatch):
    rows = [
        _row(provider_message_id="m1", account_id="acc1", box="SPAM"),
        _row(provider_message_id="m2", account_id="acc2", box="SPAM"),
    ]
    cursor = FakeCursor(fetchall_results=[rows])
    patch_connection(monkeypatch, em_module, [cursor])

    result = em_module.email_metadata_store.list_filtered(
        ["acc1", "acc2"], "SPAM", [], 200, 0,
    )
    assert len(result) == 2
    assert result[0]["provider_message_id"] == "m1"
    assert result[1]["provider_message_id"] == "m2"
    # The repository normalises rows to plain dicts even when the cursor returns
    # RealDictRow / mapping-like objects.
    assert all(isinstance(r, dict) for r in result)


# ===== exists =====


def test_exists_returns_true_when_row_present(monkeypatch):
    cursor = FakeCursor(fetchone_results=[(1,)])
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.exists("acc1", "m1") is True
    assert len(cursor.executed) == 1


def test_exists_returns_false_when_row_absent(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.exists("acc1", "m-missing") is False


def test_exists_invalid_uuid_returns_false(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, em_module, [cursor])

    assert em_module.email_metadata_store.exists("not-a-uuid", "m1") is False


def test_exists_psycopg2_error_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="Failed to check email metadata existence"):
        em_module.email_metadata_store.exists("acc1", "m1")


def test_exists_generic_exception_raises_query_error(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, em_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        em_module.email_metadata_store.exists("acc1", "m1")


def test_exists_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, em_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        em_module.email_metadata_store.exists("acc1", "m1")
