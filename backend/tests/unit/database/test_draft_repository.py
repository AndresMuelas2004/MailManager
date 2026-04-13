"""
Unit tests for draft_repository (PgDraftStore).

Covers the 7 public methods (create, get, update, delete, list_by_account,
list_by_mailbox, replace_all_for_account) including the DatabaseError
propagation guard added in Bloque 1.2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import psycopg2
import psycopg2.errors
import pytest

from database.repositories import draft_repository as draft_module
from database.errors.exceptions import ConnectionPoolError, QueryError
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error


def _fake_draft_row(
    provider_draft_id: str = "draft_1",
    account_id: str = "acc-1",
    subject: str = "Hello",
) -> dict:
    return {
        "provider_draft_id": provider_draft_id,
        "account_id": account_id,
        "to_recipients": ["to@example.com"],
        "cc_recipients": [],
        "bcc_recipients": [],
        "subject": subject,
        "body_html": "<p>body</p>",
        "created_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }


# =====================================================================
# PgDraftStore.create
# =====================================================================


class TestPgDraftStoreCreate:

    def test_create_happy_path(self, monkeypatch):
        cursor = FakeCursor(fetchone_results=[_fake_draft_row()])
        patch_connection(monkeypatch, draft_module, [cursor])

        result = draft_module.draft_store.create({
            "provider_draft_id": "draft_1",
            "account_id": "acc-1",
            "to_recipients": ["to@example.com"],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": "Hello",
            "body_html": "<p>body</p>",
        })
        assert result["provider_draft_id"] == "draft_1"
        assert result["account_id"] == "acc-1"
        assert result["subject"] == "Hello"
        # None recipients are coalesced to []
        assert result["cc_recipients"] == []
        assert result["bcc_recipients"] == []

    def test_create_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("connection lost"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Failed to create draft"):
            draft_module.draft_store.create({"provider_draft_id": "d1", "account_id": "a1"})

    def test_create_raises_query_error_on_generic_exception(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("unexpected"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="RuntimeError"):
            draft_module.draft_store.create({"provider_draft_id": "d1", "account_id": "a1"})

    def test_create_propagates_database_error(self, monkeypatch):
        # Validates Bloque 1.2 fix: ConnectionPoolError (a DatabaseError subclass)
        # from connection.get_connection() must propagate unchanged, not be
        # re-wrapped as QueryError.
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.create({"provider_draft_id": "d1", "account_id": "a1"})


# =====================================================================
# PgDraftStore.list_by_account
# =====================================================================


# =====================================================================
# PgDraftStore.get
# =====================================================================


class TestPgDraftStoreGet:

    def test_get_happy_path(self, monkeypatch):
        cursor = FakeCursor(fetchone_results=[_fake_draft_row()])
        patch_connection(monkeypatch, draft_module, [cursor])

        result = draft_module.draft_store.get("draft_1", "acc-1")
        assert result is not None
        assert result["provider_draft_id"] == "draft_1"
        assert result["account_id"] == "acc-1"

    def test_get_returns_none_when_row_missing(self, monkeypatch):
        cursor = FakeCursor(fetchone_results=[None])
        patch_connection(monkeypatch, draft_module, [cursor])

        assert draft_module.draft_store.get("missing", "acc-1") is None

    def test_get_returns_none_on_invalid_text_representation(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
        patch_connection(monkeypatch, draft_module, [cursor])

        assert draft_module.draft_store.get("draft_1", "not-a-uuid") is None

    def test_get_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Failed to get draft"):
            draft_module.draft_store.get("draft_1", "acc-1")

    def test_get_raises_query_error_on_generic(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="RuntimeError"):
            draft_module.draft_store.get("draft_1", "acc-1")

    def test_get_propagates_database_error(self, monkeypatch):
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.get("draft_1", "acc-1")


# =====================================================================
# PgDraftStore.update
# =====================================================================


class TestPgDraftStoreUpdate:

    def _sample_row(self) -> dict:
        return {
            "provider_draft_id": "draft_1",
            "account_id": "acc-1",
            "to_recipients": ["to@example.com"],
            "cc_recipients": [],
            "bcc_recipients": [],
            "subject": "Updated",
            "body_html": "<p>new</p>",
        }

    def test_update_happy_path(self, monkeypatch):
        returned = _fake_draft_row(subject="Updated")
        cursor = FakeCursor(fetchone_results=[returned])
        patch_connection(monkeypatch, draft_module, [cursor])

        result = draft_module.draft_store.update(self._sample_row())
        assert result["provider_draft_id"] == "draft_1"
        assert result["subject"] == "Updated"
        assert result["account_id"] == "acc-1"

    def test_update_row_missing_raises_query_error(self, monkeypatch):
        cursor = FakeCursor(fetchone_results=[None])
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Draft row to update not found"):
            draft_module.draft_store.update(self._sample_row())

    def test_update_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Failed to update draft"):
            draft_module.draft_store.update(self._sample_row())

    def test_update_raises_query_error_on_generic(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="RuntimeError"):
            draft_module.draft_store.update(self._sample_row())

    def test_update_propagates_database_error(self, monkeypatch):
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.update(self._sample_row())


# =====================================================================
# PgDraftStore.list_by_account
# =====================================================================


class TestPgDraftStoreListByAccount:

    def test_list_happy_path(self, monkeypatch):
        cursor = FakeCursor(fetchall_results=[[
            _fake_draft_row(provider_draft_id="d1"),
            _fake_draft_row(provider_draft_id="d2"),
        ]])
        patch_connection(monkeypatch, draft_module, [cursor])

        result = draft_module.draft_store.list_by_account("acc-1")
        assert len(result) == 2
        assert result[0]["provider_draft_id"] == "d1"
        assert result[1]["provider_draft_id"] == "d2"

    def test_list_returns_empty_on_invalid_text_representation(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
        patch_connection(monkeypatch, draft_module, [cursor])

        assert draft_module.draft_store.list_by_account("not-a-uuid") == []

    def test_list_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Failed to list drafts by account"):
            draft_module.draft_store.list_by_account("acc-1")

    def test_list_raises_query_error_on_generic(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="RuntimeError"):
            draft_module.draft_store.list_by_account("acc-1")

    def test_list_propagates_database_error(self, monkeypatch):
        # Validates Bloque 1.2 fix.
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.list_by_account("acc-1")


# =====================================================================
# PgDraftStore.list_by_mailbox
# =====================================================================


class TestPgDraftStoreListByMailbox:

    def test_list_happy_path(self, monkeypatch):
        cursor = FakeCursor(fetchall_results=[[
            _fake_draft_row(provider_draft_id="d1"),
            _fake_draft_row(provider_draft_id="d2"),
        ]])
        patch_connection(monkeypatch, draft_module, [cursor])

        result = draft_module.draft_store.list_by_mailbox("mb1")
        assert len(result) == 2
        assert result[0]["provider_draft_id"] == "d1"

    def test_list_returns_empty_on_invalid_text_representation(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
        patch_connection(monkeypatch, draft_module, [cursor])

        assert draft_module.draft_store.list_by_mailbox("not-a-uuid") == []

    def test_list_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Failed to list drafts by mailbox"):
            draft_module.draft_store.list_by_mailbox("mb1")

    def test_list_raises_query_error_on_generic(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="RuntimeError"):
            draft_module.draft_store.list_by_mailbox("mb1")

    def test_list_propagates_database_error(self, monkeypatch):
        # Validates Bloque 1.2 fix.
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.list_by_mailbox("mb1")


# =====================================================================
# PgDraftStore.replace_all_for_account
# =====================================================================


class TestPgDraftStoreReplaceAllForAccount:

    def _sample_drafts(self) -> list[dict]:
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return [
            {
                "provider_draft_id": "d1",
                "to_recipients": ["to@example.com"],
                "cc_recipients": [],
                "bcc_recipients": [],
                "subject": "s1",
                "body_html": "<p>b1</p>",
                "created_at": ts,
                "updated_at": ts,
            },
            {
                "provider_draft_id": "d2",
                "to_recipients": [],
                "cc_recipients": ["cc@example.com"],
                "bcc_recipients": [],
                "subject": "s2",
                "body_html": "<p>b2</p>",
                "created_at": ts,
                "updated_at": ts,
            },
        ]

    def test_replace_happy_path_upserts_and_deletes(self, monkeypatch):
        cursor = FakeCursor()
        patch_connection(monkeypatch, draft_module, [cursor])

        with patch.object(
            draft_module.psycopg2.extras, "execute_values",
        ) as mock_exec_values:
            result = draft_module.draft_store.replace_all_for_account(
                "acc-1", self._sample_drafts(),
            )
            assert result == 2
            # UPSERT executed once with the batch
            assert mock_exec_values.call_count == 1
            _cur_arg, query_arg, rows_arg = mock_exec_values.call_args[0]
            assert "INSERT INTO drafts" in query_arg
            assert "ON CONFLICT" in query_arg
            assert len(rows_arg) == 2
            # DELETE executed to clear missing drafts (keep_ids = ["d1", "d2"])
            executed_sqls = [call[0] for call in cursor.executed]
            assert any("DELETE FROM drafts" in sql for sql in executed_sqls)
            delete_params = next(
                params for sql, params in cursor.executed if "DELETE FROM drafts" in sql
            )
            assert delete_params == {"account_id": "acc-1", "keep_ids": ["d1", "d2"]}

    def test_replace_empty_drafts_deletes_all(self, monkeypatch):
        # When drafts is empty, UPSERT is skipped and DELETE runs with keep_ids=[]
        # which intentionally deletes every row for the account.
        cursor = FakeCursor()
        patch_connection(monkeypatch, draft_module, [cursor])

        with patch.object(
            draft_module.psycopg2.extras, "execute_values",
        ) as mock_exec_values:
            result = draft_module.draft_store.replace_all_for_account("acc-1", [])
            assert result == 0
            mock_exec_values.assert_not_called()
            assert len(cursor.executed) == 1
            sql, params = cursor.executed[0]
            assert "DELETE FROM drafts" in sql
            assert params == {"account_id": "acc-1", "keep_ids": []}

    def test_replace_returns_len_drafts(self, monkeypatch):
        cursor = FakeCursor()
        patch_connection(monkeypatch, draft_module, [cursor])

        with patch.object(draft_module.psycopg2.extras, "execute_values"):
            result = draft_module.draft_store.replace_all_for_account(
                "acc-1", self._sample_drafts(),
            )
            assert result == 2

    def test_replace_invalid_account_id_raises_query_error(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
        patch_connection(monkeypatch, draft_module, [cursor])

        with patch.object(draft_module.psycopg2.extras, "execute_values"):
            with pytest.raises(QueryError, match="Invalid account_id format"):
                draft_module.draft_store.replace_all_for_account(
                    "not-a-uuid", self._sample_drafts(),
                )

    def test_replace_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with patch.object(draft_module.psycopg2.extras, "execute_values"):
            with pytest.raises(QueryError, match="Failed to replace drafts"):
                draft_module.draft_store.replace_all_for_account(
                    "acc-1", self._sample_drafts(),
                )

    def test_replace_raises_query_error_on_generic(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with patch.object(draft_module.psycopg2.extras, "execute_values"):
            with pytest.raises(QueryError, match="RuntimeError"):
                draft_module.draft_store.replace_all_for_account(
                    "acc-1", self._sample_drafts(),
                )

    def test_replace_propagates_database_error(self, monkeypatch):
        # Validates Bloque 1.2 fix.
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.replace_all_for_account(
                "acc-1", self._sample_drafts(),
            )


# =====================================================================
# PgDraftStore.delete
# =====================================================================


class TestPgDraftStoreDelete:

    def test_delete_happy_path(self, monkeypatch):
        cursor = FakeCursor(fetchone_results=[("draft-1",)])
        patch_connection(monkeypatch, draft_module, [cursor])

        draft_module.draft_store.delete("draft-1", "acc-1")
        executed_sqls = [call[0] for call in cursor.executed]
        assert any("DELETE FROM drafts" in sql for sql in executed_sqls)

    def test_delete_not_found_raises_query_error(self, monkeypatch):
        cursor = FakeCursor(fetchone_results=[None])
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Draft row to delete not found"):
            draft_module.draft_store.delete("missing", "acc-1")

    def test_delete_raises_query_error_on_psycopg2(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="Failed to delete draft"):
            draft_module.draft_store.delete("draft-1", "acc-1")

    def test_delete_raises_query_error_on_generic(self, monkeypatch):
        cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
        patch_connection(monkeypatch, draft_module, [cursor])

        with pytest.raises(QueryError, match="RuntimeError"):
            draft_module.draft_store.delete("draft-1", "acc-1")

    def test_delete_propagates_database_error(self, monkeypatch):
        patch_connection_error(monkeypatch, draft_module, ConnectionPoolError("pool down"))

        with pytest.raises(ConnectionPoolError, match="pool down"):
            draft_module.draft_store.delete("draft-1", "acc-1")
