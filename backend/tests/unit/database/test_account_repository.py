from __future__ import annotations

from datetime import datetime, timezone

import psycopg2
import psycopg2.errors
import pytest

from database.repositories import account_repository as account_module
from database.security import token_crypto
from database.errors.exceptions import (
    ConnectionPoolError,
    QueryError,
    SettingsError,
    TokenValidationError,
)
from tests.shared.database_fakes import FakeCursor, patch_connection, patch_connection_error

Fernet = pytest.importorskip("cryptography.fernet").Fernet


def _fake_row(
    account_id: str = "acc1",
    mailbox_id: str = "mb1",
    provider: str = "gmail",
    display_label: str = "gmail:acc1",
    config: dict | None = None,
) -> dict:
    return {
        "account_id": account_id,
        "mailbox_id": mailbox_id,
        "provider": provider,
        "display_label": display_label,
        "config": config or {},
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }


# ===== list_by_mailbox =====


def test_list_by_mailbox_happy_path(monkeypatch):
    cursor = FakeCursor(fetchall_results=[[_fake_row(), _fake_row(account_id="acc2")]])
    patch_connection(monkeypatch, account_module, [cursor])

    result = account_module.account_store.list_by_mailbox("mb1")
    assert len(result) == 2
    assert result[0]["account_id"] == "acc1"
    assert result[1]["account_id"] == "acc2"


def test_list_by_mailbox_returns_empty_on_invalid_text(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, account_module, [cursor])

    assert account_module.account_store.list_by_mailbox("not-a-uuid") == []


def test_list_by_mailbox_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to list accounts"):
        account_module.account_store.list_by_mailbox("mb1")


def test_list_by_mailbox_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        account_module.account_store.list_by_mailbox("mb1")


def test_list_by_mailbox_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, account_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        account_module.account_store.list_by_mailbox("mb1")


# ===== get =====


def test_get_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, account_module, [cursor])

    result = account_module.account_store.get("mb1", "acc1")
    assert result["account_id"] == "acc1"
    assert result["provider"] == "gmail"


def test_get_returns_none_when_not_found(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    patch_connection(monkeypatch, account_module, [cursor])

    assert account_module.account_store.get("mb1", "acc1") is None


def test_get_returns_none_on_invalid_text(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, account_module, [cursor])

    assert account_module.account_store.get("mb1", "not-a-uuid") is None


def test_get_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to get account"):
        account_module.account_store.get("mb1", "acc1")


# ===== upsert =====


def test_upsert_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, account_module, [cursor])

    result = account_module.account_store.upsert(
        {
            "account_id": "acc1",
            "mailbox_id": "mb1",
            "provider": "gmail",
            "display_label": "gmail:acc1",
            "config": {"key": "val"},
        }
    )
    assert result["account_id"] == "acc1"


def test_upsert_serializes_config_dict(monkeypatch):
    cursor = FakeCursor(fetchone_results=[_fake_row()])
    patch_connection(monkeypatch, account_module, [cursor])

    account_module.account_store.upsert(
        {
            "account_id": "acc1",
            "mailbox_id": "mb1",
            "provider": "gmail",
            "display_label": "gmail:acc1",
            "config": {"nested": True},
        }
    )
    _, params = cursor.executed[0]
    assert isinstance(params["config"], str)
    assert '"nested"' in params["config"]


def test_upsert_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to upsert account"):
        account_module.account_store.upsert(
            {"account_id": "acc1", "mailbox_id": "mb1", "provider": "gmail", "display_label": "x"}
        )


def test_upsert_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        account_module.account_store.upsert(
            {"account_id": "acc1", "mailbox_id": "mb1", "provider": "gmail", "display_label": "x"}
        )


# ===== delete =====


def test_delete_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, account_module, [cursor])

    account_module.account_store.delete("mb1", "acc1")
    assert len(cursor.executed) == 1


def test_delete_noop_on_invalid_text(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, account_module, [cursor])

    account_module.account_store.delete("mb1", "not-a-uuid")


def test_delete_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to delete account"):
        account_module.account_store.delete("mb1", "acc1")


def test_delete_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("unexpected"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        account_module.account_store.delete("mb1", "acc1")


# ===== get_tokens =====


def test_get_tokens_dual_read_plaintext_then_backfill(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "v1")

    select_cursor = FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": "plain-access",
                "refresh_token": "plain-refresh",
                "access_token_encrypted": None,
                "refresh_token_encrypted": None,
                "encryption_key_id": None,
                "expiry": None,
                "scopes": ["scope-a"],
            }
        ]
    )
    backfill_cursor = FakeCursor()
    patch_connection(monkeypatch, account_module, [select_cursor, backfill_cursor])

    payload = account_module.account_store.get_tokens("mb1", "acc1", "GMAIL")

    assert payload["access_token"] == "plain-access"
    assert payload["refresh_token"] == "plain-refresh"
    assert payload["scopes"] == ["scope-a"]
    assert len(backfill_cursor.executed) == 1
    _, backfill_params = backfill_cursor.executed[0]
    assert backfill_params["provider"] == "gmail"
    assert backfill_params["access_token_encrypted"] is not None
    assert backfill_params["refresh_token_encrypted"] is not None


def test_get_tokens_plaintext_disallowed_returns_none(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "false")

    select_cursor = FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": "plain-access",
                "refresh_token": "plain-refresh",
                "access_token_encrypted": None,
                "refresh_token_encrypted": None,
                "encryption_key_id": None,
                "expiry": None,
                "scopes": None,
            }
        ]
    )
    patch_connection(monkeypatch, account_module, [select_cursor])

    result = account_module.account_store.get_tokens("mb1", "acc1", "gmail")
    assert result is None


def test_get_tokens_uses_encrypted_columns(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "false")

    encrypted_access = token_crypto.encrypt_token("enc-access")
    encrypted_refresh = token_crypto.encrypt_token("enc-refresh")
    select_cursor = FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": None,
                "refresh_token": None,
                "access_token_encrypted": encrypted_access,
                "refresh_token_encrypted": encrypted_refresh,
                "encryption_key_id": "v1",
                "expiry": None,
                "scopes": None,
            }
        ]
    )
    patch_connection(monkeypatch, account_module, [select_cursor])

    payload = account_module.account_store.get_tokens("mb1", "acc1", "gmail")
    assert payload["access_token"] == "enc-access"
    assert payload["refresh_token"] == "enc-refresh"


def test_get_tokens_raises_query_error_on_psycopg2_failure(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("connection lost"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to read token"):
        account_module.account_store.get_tokens("mb1", "acc1", "gmail")


def test_get_tokens_propagates_connection_pool_error(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    patch_connection_error(
        monkeypatch,
        account_module,
        ConnectionPoolError("pool exhausted"),
    )

    with pytest.raises(ConnectionPoolError, match="pool exhausted"):
        account_module.account_store.get_tokens("mb1", "acc1", "gmail")


def test_get_tokens_raises_query_error_on_unexpected_exception(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    cursor = FakeCursor(execute_side_effect=RuntimeError("weird"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        account_module.account_store.get_tokens("mb1", "acc1", "gmail")


def test_get_tokens_returns_none_when_no_row(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    select_cursor = FakeCursor(fetchone_results=[])
    patch_connection(monkeypatch, account_module, [select_cursor])

    result = account_module.account_store.get_tokens("mb1", "acc1", "gmail")
    assert result is None


def test_get_tokens_malformed_key_raises_settings_error(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "true")

    select_cursor = FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": "plain-access",
                "refresh_token": "plain-refresh",
                "access_token_encrypted": "encrypted-blob",
                "refresh_token_encrypted": "encrypted-blob",
                "encryption_key_id": "v1",
                "expiry": None,
                "scopes": None,
            }
        ]
    )
    patch_connection(monkeypatch, account_module, [select_cursor])

    with pytest.raises(SettingsError, match="TOKEN_ENCRYPTION_KEY"):
        account_module.account_store.get_tokens("mb1", "acc1", "gmail")


def test_get_tokens_backfill_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_PLAINTEXT_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "v1")

    select_cursor = FakeCursor(
        fetchone_results=[
            {
                "account_id": "acc1",
                "access_token": "plain-access",
                "refresh_token": "plain-refresh",
                "access_token_encrypted": None,
                "refresh_token_encrypted": None,
                "encryption_key_id": None,
                "expiry": None,
                "scopes": ["scope-a"],
            }
        ]
    )
    backfill_cursor = FakeCursor(
        execute_side_effect=psycopg2.OperationalError("connection lost")
    )
    patch_connection(monkeypatch, account_module, [select_cursor, backfill_cursor])

    payload = account_module.account_store.get_tokens("mb1", "acc1", "gmail")

    assert payload is not None
    assert payload["access_token"] == "plain-access"
    assert payload["refresh_token"] == "plain-refresh"


# ===== upsert_tokens =====


def test_upsert_tokens_requires_context_match(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "v1")

    save_cursor = FakeCursor(rowcounts=[0])
    patch_connection(monkeypatch, account_module, [save_cursor])

    with pytest.raises(TokenValidationError):
        account_module.account_store.upsert_tokens(
            mailbox_id="mb1",
            account_id="acc1",
            provider="gmail",
            token_data={
                "access_token": "at",
                "refresh_token": "rt",
                "expiry": None,
                "scopes": ["scope-a"],
            },
        )


def test_upsert_tokens_raises_token_validation_error_on_invalid_payload(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    with pytest.raises(TokenValidationError, match="Token payload is invalid"):
        account_module.account_store.upsert_tokens(
            mailbox_id="mb1",
            account_id="acc1",
            provider="gmail",
            token_data="not-a-dict",
        )


def test_upsert_tokens_raises_token_validation_error_on_empty_provider(monkeypatch):
    with pytest.raises(TokenValidationError, match="Provider is required"):
        account_module.account_store.upsert_tokens(
            mailbox_id="mb1",
            account_id="acc1",
            provider="",
            token_data={"access_token": "at"},
        )


def test_upsert_tokens_raises_query_error_on_psycopg2_failure(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_ID", "v1")

    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("connection lost"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to save token"):
        account_module.account_store.upsert_tokens(
            mailbox_id="mb1",
            account_id="acc1",
            provider="gmail",
            token_data={"access_token": "at", "refresh_token": "rt"},
        )


# ===== get_sync_cursor =====


def test_get_sync_cursor_happy_path(monkeypatch):
    cursor = FakeCursor(fetchone_results=[{"sync_cursor": "hist123"}])
    patch_connection(monkeypatch, account_module, [cursor])

    result = account_module.account_store.get_sync_cursor("mb1", "acc1")
    assert result == "hist123"


def test_get_sync_cursor_returns_none_when_no_row(monkeypatch):
    cursor = FakeCursor(fetchone_results=[None])
    patch_connection(monkeypatch, account_module, [cursor])

    assert account_module.account_store.get_sync_cursor("mb1", "acc1") is None


def test_get_sync_cursor_returns_none_on_invalid_text(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.errors.InvalidTextRepresentation())
    patch_connection(monkeypatch, account_module, [cursor])

    assert account_module.account_store.get_sync_cursor("mb1", "not-a-uuid") is None


def test_get_sync_cursor_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to read sync cursor"):
        account_module.account_store.get_sync_cursor("mb1", "acc1")


def test_get_sync_cursor_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        account_module.account_store.get_sync_cursor("mb1", "acc1")


def test_get_sync_cursor_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, account_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        account_module.account_store.get_sync_cursor("mb1", "acc1")


# ===== update_sync_cursor =====


def test_update_sync_cursor_happy_path(monkeypatch):
    cursor = FakeCursor()
    patch_connection(monkeypatch, account_module, [cursor])

    account_module.account_store.update_sync_cursor("mb1", "acc1", "hist456")
    assert len(cursor.executed) == 1


def test_update_sync_cursor_raises_query_error_on_psycopg2(monkeypatch):
    cursor = FakeCursor(execute_side_effect=psycopg2.OperationalError("fail"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="Failed to update sync cursor"):
        account_module.account_store.update_sync_cursor("mb1", "acc1", "hist456")


def test_update_sync_cursor_raises_query_error_on_generic(monkeypatch):
    cursor = FakeCursor(execute_side_effect=RuntimeError("boom"))
    patch_connection(monkeypatch, account_module, [cursor])

    with pytest.raises(QueryError, match="RuntimeError"):
        account_module.account_store.update_sync_cursor("mb1", "acc1", "hist456")


def test_update_sync_cursor_propagates_connection_pool_error(monkeypatch):
    patch_connection_error(monkeypatch, account_module, ConnectionPoolError("pool down"))

    with pytest.raises(ConnectionPoolError, match="pool down"):
        account_module.account_store.update_sync_cursor("mb1", "acc1", "hist456")
