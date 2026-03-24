from __future__ import annotations

from datetime import datetime, timezone

import psycopg2
import psycopg2.errors
import pytest

from database.repositories import mailbox_repository as mailbox_module
from database.errors.exceptions import ConnectionPoolError, QueryError
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error


def _fake_row(
    mailbox_id: str = "mb1",
    display_name: str = "My Mailbox",
    owner_user_id: str = "user1",
) -> dict:
    return {
        "mailbox_id": mailbox_id,
        "display_name": display_name,
        "owner_user_id": owner_user_id,
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }


# ===== create =====


def test_create_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, mailbox_module, [cursor])

    result = mailbox_module.mailbox_store.create(
        {"mailbox_id": "mb1", "display_name": "My Mailbox", "owner_user_id": "user1"}
    )
    assert result["mailbox_id"] == "mb1"
    assert result["owner_user_id"] == "user1"
    assert isinstance(result["created_at"], str)


def test_create_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("connection lost"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="Failed to create mailbox"):
        mailbox_module.mailbox_store.create({"mailbox_id": "mb1", "display_name": "x", "owner_user_id": "u"})


def test_create_raises_query_error_on_generic_exception(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("unexpected"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        mailbox_module.mailbox_store.create({"mailbox_id": "mb1", "display_name": "x", "owner_user_id": "u"})


def test_create_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, mailbox_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        mailbox_module.mailbox_store.create({"mailbox_id": "mb1", "display_name": "x", "owner_user_id": "u"})


# ===== list_by_owner =====


def test_list_by_owner_happy_path(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[_fake_row(), _fake_row(mailbox_id="mb2")]])
    patch_connection(monkeypatch, mailbox_module, [cursor])

    result = mailbox_module.mailbox_store.list_by_owner("user1")
    assert len(result) == 2
    assert result[0]["mailbox_id"] == "mb1"
    assert result[1]["mailbox_id"] == "mb2"


def test_list_by_owner_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list mailboxes"):
        mailbox_module.mailbox_store.list_by_owner("user1")


def test_list_by_owner_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        mailbox_module.mailbox_store.list_by_owner("user1")


def test_list_by_owner_returns_empty_on_invalid_text_representation(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, mailbox_module, [cursor])

    assert mailbox_module.mailbox_store.list_by_owner("not-a-uuid") == []


# ===== get =====


def test_get_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, mailbox_module, [cursor])

    result = mailbox_module.mailbox_store.get("mb1")
    assert result["mailbox_id"] == "mb1"


def test_get_returns_none_when_not_found(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    patch_connection(monkeypatch, mailbox_module, [cursor])

    assert mailbox_module.mailbox_store.get("mb1") is None


def test_get_returns_none_on_invalid_text_representation(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, mailbox_module, [cursor])

    assert mailbox_module.mailbox_store.get("not-a-uuid") is None


def test_get_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="Failed to get mailbox"):
        mailbox_module.mailbox_store.get("mb1")


def test_get_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, mailbox_module, ConnectionPoolError("no pool"))

    with pytest.raises(ConnectionPoolError, match="no pool"):
        mailbox_module.mailbox_store.get("mb1")


# ===== delete =====


def test_delete_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, mailbox_module, [cursor])

    mailbox_module.mailbox_store.delete("mb1")
    assert len(cursor.executed) == 1


def test_delete_noop_on_invalid_text_representation(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, mailbox_module, [cursor])

    mailbox_module.mailbox_store.delete("not-a-uuid")


def test_delete_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="Failed to delete mailbox"):
        mailbox_module.mailbox_store.delete("mb1")


def test_delete_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("unexpected"))
    patch_connection(monkeypatch, mailbox_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        mailbox_module.mailbox_store.delete("mb1")
