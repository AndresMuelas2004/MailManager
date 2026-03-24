"""
Unit tests for services_helpers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import SecretStr

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    ApiError,
    CredentialFileError,
    DatabaseQueryError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
)
from api.services.services_helpers import (
    _wrap_secret,
    build_manager_for_accounts,
    delete_email_metadata_batch,
    ensure_mailbox_access,
    get_trash_emails_by_ids,
    is_auth_error,
    load_stored_message_ids,
    load_sync_cursors,
    load_wrapped_account_tokens,
    load_wrapped_app_credentials,
    mark_as_deleted_batch,
    move_to_trash_batch,
    persist_email_metadata_batch,
    raise_on_silent_auth_errors,
    restore_from_trash_batch,
    restore_from_trash_discovered_batch,
    translate_connect_error,
    unwrap_secret,
    update_email_metadata_labels_batch,
    update_email_read_status_batch,
    update_email_spam_status_batch,
    update_sync_cursor,
)
from core.email import LabelUpdate, SpamMoveResult
from core.email.errors import (
    CoreError,
    EmailAuthError,
    EmailExternalAPIError,
    EmailMissingTokenError,
)
from database import CredentialReadError, QueryError
from tests.shared.email_fakes import build_metadata


class TestEnsureMailboxAccess:

    def test_null_owner_raises_forbidden(self):
        """A mailbox with owner_user_id=None must be rejected."""
        fake_record = {
            "mailbox_id": "mb-1",
            "display_name": "Orphan",
            "owner_user_id": None,
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = fake_record
            with pytest.raises(Forbidden):
                ensure_mailbox_access("mb-1", "some-user-id")

    def test_mismatched_owner_raises_forbidden(self):
        """A mailbox owned by a different user must be rejected."""
        fake_record = {
            "mailbox_id": "mb-1",
            "display_name": "Other's MB",
            "owner_user_id": "owner-a",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = fake_record
            with pytest.raises(Forbidden):
                ensure_mailbox_access("mb-1", "owner-b")

    def test_matching_owner_returns_record(self):
        """A mailbox owned by the requesting user is returned."""
        fake_record = {
            "mailbox_id": "mb-1",
            "display_name": "My MB",
            "owner_user_id": "owner-a",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = fake_record
            result = ensure_mailbox_access("mb-1", "owner-a")
        assert result == fake_record

    def test_database_error_translated(self):
        """QueryError from mailbox_store.get → DatabaseQueryError."""
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                ensure_mailbox_access("mb-1", "some-user-id")

    def test_generic_exception_raises_api_error(self):
        """RuntimeError from mailbox_store.get → ApiError fallback."""
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to look up mailbox"):
                ensure_mailbox_access("mb-1", "some-user-id")


# ------------------------------------------------------------------
# build_manager_for_accounts — except Exception fallback
# ------------------------------------------------------------------

class TestBuildManagerUnexpectedException:

    def test_unexpected_exception_raises_account_misconfigured(self):
        """A non-CoreError from add_account_record → AccountMisconfigured."""
        account = {"mailbox_id": "mb-1", "account_id": "acc-1", "provider": "gmail"}
        with patch(
            "api.services.services_helpers.EmailManager"
        ) as mock_manager_cls:
            mock_manager_cls.return_value.add_account_record.side_effect = (
                RuntimeError("unexpected boom")
            )
            with pytest.raises(AccountMisconfigured, match="Failed to register account"):
                build_manager_for_accounts([account])


# ------------------------------------------------------------------
# ensure_mailbox_access — store returns None
# ------------------------------------------------------------------

class TestEnsureMailboxAccessNotFound:

    def test_mailbox_not_found_when_store_returns_none(self):
        with patch("api.services.services_helpers.mailbox_store") as mock_store:
            mock_store.get.return_value = None
            with pytest.raises(MailboxNotFound, match="not found"):
                ensure_mailbox_access("mb-1", "some-user-id")


# ------------------------------------------------------------------
# raise_on_silent_auth_errors
# ------------------------------------------------------------------

class TestRaiseOnSilentAuthErrors:

    def test_empty_errors_returns_none(self):
        assert raise_on_silent_auth_errors({}) is None

    def test_single_auth_error_raises_account_not_connected(self):
        errors = {"mb__acc1": EmailAuthError("token expired")}
        with pytest.raises(AccountNotConnected) as exc_info:
            raise_on_silent_auth_errors(errors)
        assert "mb__acc1" in exc_info.value.detail["account_labels"]

    def test_multiple_auth_errors_aggregated(self):
        errors = {
            "mb__acc1": EmailAuthError("expired"),
            "mb__acc2": EmailMissingTokenError("missing"),
        }
        with pytest.raises(AccountNotConnected) as exc_info:
            raise_on_silent_auth_errors(errors)
        labels = exc_info.value.detail["account_labels"]
        assert "mb__acc1" in labels
        assert "mb__acc2" in labels

    def test_non_auth_core_error_translated_and_raised(self):
        errors = {"mb__acc1": EmailExternalAPIError("API fail")}
        with pytest.raises(ExternalAPIError):
            raise_on_silent_auth_errors(errors)

    def test_non_core_error_raises_fallback_api_error(self):
        errors = {"mb__acc1": RuntimeError("something")}
        with pytest.raises(ApiError):
            raise_on_silent_auth_errors(errors)

    def test_reasons_included_in_detail(self):
        errors = {"mb__acc1": EmailAuthError("token expired")}
        with pytest.raises(AccountNotConnected) as exc_info:
            raise_on_silent_auth_errors(errors)
        assert "reasons" in exc_info.value.detail
        assert exc_info.value.detail["reasons"]["mb__acc1"] == "token expired"


# ------------------------------------------------------------------
# translate_connect_error
# ------------------------------------------------------------------

class TestIsAuthError:

    def test_true_for_email_auth_error(self):
        assert is_auth_error(EmailAuthError("x")) is True

    def test_false_for_non_auth_core_error(self):
        assert is_auth_error(EmailExternalAPIError("x")) is False

    def test_false_for_generic_exception(self):
        assert is_auth_error(RuntimeError("x")) is False


class TestTranslateConnectError:

    def test_email_auth_error_returns_account_connect_auth_error(self):
        exc = EmailAuthError("Token rejected.")
        result = translate_connect_error(exc)
        assert isinstance(result, AccountConnectAuthError)
        assert result.detail.get("core_code") == EmailAuthError.code

    def test_other_core_error_uses_standard_mapping(self):
        exc = EmailExternalAPIError("API fail")
        result = translate_connect_error(exc)
        assert isinstance(result, ExternalAPIError)

    def test_non_core_error_uses_fallback(self):
        exc = RuntimeError("unexpected")
        result = translate_connect_error(exc)
        assert isinstance(result, AccountConnectAuthError)


# ------------------------------------------------------------------
# load_wrapped_app_credentials
# ------------------------------------------------------------------

class TestLoadWrappedAppCredentials:

    def test_happy_path_wraps_client_secret(self):
        fake_creds = {"client_id": "cid", "client_secret": "secret"}
        with patch("api.services.services_helpers.load_app_credentials", return_value=fake_creds):
            result = load_wrapped_app_credentials("gmail")
        assert isinstance(result["client_secret"], SecretStr)
        assert result["client_secret"].get_secret_value() == "secret"
        assert result["client_id"] == "cid"

    def test_database_error_translated(self):
        with patch(
            "api.services.services_helpers.load_app_credentials",
            side_effect=CredentialReadError("read fail"),
        ):
            with pytest.raises(CredentialFileError):
                load_wrapped_app_credentials("gmail")

    def test_generic_exception_raises_api_error(self):
        with patch(
            "api.services.services_helpers.load_app_credentials",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(ApiError, match="Failed to load app credentials"):
                load_wrapped_app_credentials("gmail")


# ------------------------------------------------------------------
# load_wrapped_account_tokens
# ------------------------------------------------------------------

class TestLoadWrappedAccountTokens:

    def test_happy_path_wraps_tokens(self):
        fake_tokens = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_tokens.return_value = fake_tokens
            result = load_wrapped_account_tokens("mb-1", "acc-1", "gmail")
        assert isinstance(result["access_token"], SecretStr)
        assert isinstance(result["refresh_token"], SecretStr)
        assert result["expires_in"] == 3600

    def test_none_returns_empty_dict(self):
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_tokens.return_value = None
            result = load_wrapped_account_tokens("mb-1", "acc-1", "gmail")
        assert result == {}

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_tokens.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                load_wrapped_account_tokens("mb-1", "acc-1", "gmail")

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_tokens.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to load account tokens"):
                load_wrapped_account_tokens("mb-1", "acc-1", "gmail")


# ------------------------------------------------------------------
# persist_email_metadata_batch
# ------------------------------------------------------------------

class TestPersistEmailMetadataBatch:

    def test_empty_list_returns_zero(self):
        assert persist_email_metadata_batch("acc-1", []) == 0

    def test_happy_path_converts_and_persists(self):
        metadata = [
            build_metadata(provider_message_id="m1"),
            build_metadata(provider_message_id="m2"),
        ]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.upsert_batch.return_value = 2
            result = persist_email_metadata_batch("acc-1", metadata)
        assert result == 2
        call_args = mock_store.upsert_batch.call_args
        assert call_args[0][0] == "acc-1"
        rows = call_args[0][1]
        assert len(rows) == 2
        assert rows[0][0] == "m1"

    def test_database_error_translated(self):
        metadata = [build_metadata()]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.upsert_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                persist_email_metadata_batch("acc-1", metadata)

    def test_generic_exception_raises_api_error(self):
        metadata = [build_metadata()]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.upsert_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to persist email metadata"):
                persist_email_metadata_batch("acc-1", metadata)


# ------------------------------------------------------------------
# delete_email_metadata_batch
# ------------------------------------------------------------------

class TestDeleteEmailMetadataBatch:

    def test_empty_list_returns_zero(self):
        assert delete_email_metadata_batch("acc-1", []) == 0

    def test_happy_path_returns_deleted_count(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.delete_batch_by_message_ids.return_value = 3
            result = delete_email_metadata_batch("acc-1", ["m1", "m2", "m3"])
        assert result == 3

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.delete_batch_by_message_ids.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                delete_email_metadata_batch("acc-1", ["m1"])

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.delete_batch_by_message_ids.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to delete email metadata"):
                delete_email_metadata_batch("acc-1", ["m1"])


# ------------------------------------------------------------------
# update_email_metadata_labels_batch
# ------------------------------------------------------------------

class TestUpdateEmailMetadataLabelsBatch:

    def test_empty_list_returns_zero(self):
        assert update_email_metadata_labels_batch("acc-1", []) == 0

    def test_happy_path_converts_and_updates(self):
        updates = [
            LabelUpdate(provider_message_id="m1", is_read=True, box="INBOX"),
            LabelUpdate(provider_message_id="m2", is_read=False, box="TRASH"),
        ]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_labels_batch.return_value = 2
            result = update_email_metadata_labels_batch("acc-1", updates)
        assert result == 2
        call_args = mock_store.update_labels_batch.call_args
        rows = call_args[0][1]
        assert len(rows) == 2
        assert rows[0] == ("m1", "acc-1", True, "INBOX")

    def test_database_error_translated(self):
        updates = [LabelUpdate(provider_message_id="m1", is_read=True, box="INBOX")]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_labels_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                update_email_metadata_labels_batch("acc-1", updates)

    def test_generic_exception_raises_api_error(self):
        updates = [LabelUpdate(provider_message_id="m1", is_read=True, box="INBOX")]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_labels_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to update email metadata labels"):
                update_email_metadata_labels_batch("acc-1", updates)


# ------------------------------------------------------------------
# load_stored_message_ids
# ------------------------------------------------------------------

class TestLoadStoredMessageIds:

    def test_happy_path_returns_id_list(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.list_provider_message_ids.return_value = ["m1", "m2"]
            result = load_stored_message_ids("acc-1")
        assert result == ["m1", "m2"]

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.list_provider_message_ids.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                load_stored_message_ids("acc-1")

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.list_provider_message_ids.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to load stored message IDs"):
                load_stored_message_ids("acc-1")


# ------------------------------------------------------------------
# get_trash_emails_by_ids
# ------------------------------------------------------------------

class TestGetTrashEmailsByIds:

    def test_empty_list_returns_empty(self):
        assert get_trash_emails_by_ids("acc-1", []) == []

    def test_happy_path_returns_rows(self):
        fake_rows = [
            {"provider_message_id": "m1", "box": "TRASH", "previous_box": "ALL_MAIL"},
        ]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.get_trash_emails_by_ids.return_value = fake_rows
            result = get_trash_emails_by_ids("acc-1", ["m1"])
        assert result == fake_rows

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.get_trash_emails_by_ids.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                get_trash_emails_by_ids("acc-1", ["m1"])

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.get_trash_emails_by_ids.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to get trash emails"):
                get_trash_emails_by_ids("acc-1", ["m1"])


# ------------------------------------------------------------------
# mark_as_deleted_batch
# ------------------------------------------------------------------

class TestMarkAsDeletedBatch:

    def test_empty_list_returns_zero(self):
        assert mark_as_deleted_batch("acc-1", []) == 0

    def test_happy_path_returns_count(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.mark_as_deleted_batch.return_value = 2
            result = mark_as_deleted_batch("acc-1", ["m1", "m2"])
        assert result == 2

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.mark_as_deleted_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                mark_as_deleted_batch("acc-1", ["m1"])

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.mark_as_deleted_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to mark emails as deleted"):
                mark_as_deleted_batch("acc-1", ["m1"])


# ------------------------------------------------------------------
# restore_from_trash_batch
# ------------------------------------------------------------------

class TestRestoreFromTrashBatch:

    def test_empty_list_returns_zero(self):
        assert restore_from_trash_batch("acc-1", []) == 0

    def test_happy_path_returns_count(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.restore_from_trash_batch.return_value = 2
            result = restore_from_trash_batch("acc-1", [("m1", "m1", "acc-1"), ("m2", "m2", "acc-1")])
        assert result == 2

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.restore_from_trash_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                restore_from_trash_batch("acc-1", [("m1", "m1", "acc-1")])

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.restore_from_trash_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to restore emails from trash"):
                restore_from_trash_batch("acc-1", [("m1", "m1", "acc-1")])


# ------------------------------------------------------------------
# restore_from_trash_discovered_batch
# ------------------------------------------------------------------

class TestRestoreFromTrashDiscoveredBatch:

    def test_empty_list_returns_zero(self):
        assert restore_from_trash_discovered_batch("acc-1", []) == 0

    def test_happy_path_returns_count(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.restore_from_trash_discovered_batch.return_value = 2
            result = restore_from_trash_discovered_batch(
                "acc-1", [("m1", "m1", "acc-1", "SENT"), ("m2", "m2", "acc-1", "SPAM")],
            )
        assert result == 2

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.restore_from_trash_discovered_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                restore_from_trash_discovered_batch("acc-1", [("m1", "m1", "acc-1", "SENT")])

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.restore_from_trash_discovered_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to restore emails with discovered box"):
                restore_from_trash_discovered_batch("acc-1", [("m1", "m1", "acc-1", "SENT")])


# ------------------------------------------------------------------
# move_to_trash_batch
# ------------------------------------------------------------------

class TestMoveToTrashBatch:

    def test_empty_list_returns_zero(self):
        assert move_to_trash_batch("acc-1", []) == 0

    def test_happy_path_returns_count(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.move_to_trash_batch.return_value = 2
            result = move_to_trash_batch("acc-1", [("m1", "m1", "acc-1"), ("m2", "m2", "acc-1")])
        assert result == 2

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.move_to_trash_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                move_to_trash_batch("acc-1", [("m1", "m1", "acc-1")])

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.move_to_trash_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to move emails to trash"):
                move_to_trash_batch("acc-1", [("m1", "m1", "acc-1")])


# ------------------------------------------------------------------
# unwrap_secret
# ------------------------------------------------------------------

class TestUnwrapSecret:

    def test_none_returns_none(self):
        assert unwrap_secret(None) is None

    def test_secret_str_returns_value(self):
        assert unwrap_secret(SecretStr("tok")) == "tok"

    def test_plain_string_returns_as_is(self):
        assert unwrap_secret("plain") == "plain"


# ------------------------------------------------------------------
# _wrap_secret
# ------------------------------------------------------------------

class TestWrapSecret:

    def test_none_returns_none(self):
        assert _wrap_secret(None) is None

    def test_string_wraps_to_secret_str(self):
        result = _wrap_secret("tok")
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "tok"

    def test_int_wraps_to_secret_str(self):
        result = _wrap_secret(42)
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "42"


# ------------------------------------------------------------------
# load_sync_cursors
# ------------------------------------------------------------------

class TestLoadSyncCursors:

    def test_happy_path_returns_cursor_dict(self):
        lookup = {"mb__acc1": ("mb", "acc1", "gmail")}
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_sync_cursor.return_value = "cursor-123"
            result = load_sync_cursors(lookup)
        assert result == {"mb__acc1": "cursor-123"}

    def test_database_error_translated(self):
        lookup = {"mb__acc1": ("mb", "acc1", "gmail")}
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_sync_cursor.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                load_sync_cursors(lookup)

    def test_generic_exception_raises_api_error(self):
        lookup = {"mb__acc1": ("mb", "acc1", "gmail")}
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.get_sync_cursor.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to load sync cursor"):
                load_sync_cursors(lookup)


# ------------------------------------------------------------------
# update_sync_cursor
# ------------------------------------------------------------------

class TestUpdateSyncCursor:

    def test_happy_path_calls_store(self):
        with patch("api.services.services_helpers.account_store") as mock_store:
            update_sync_cursor("mb-1", "acc-1", "cursor-new")
        mock_store.update_sync_cursor.assert_called_once_with("mb-1", "acc-1", "cursor-new")

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.update_sync_cursor.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                update_sync_cursor("mb-1", "acc-1", "cursor-new")

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.account_store") as mock_store:
            mock_store.update_sync_cursor.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to update sync cursor"):
                update_sync_cursor("mb-1", "acc-1", "cursor-new")


# ------------------------------------------------------------------
# update_email_read_status_batch
# ------------------------------------------------------------------

class TestUpdateEmailReadStatusBatch:

    def test_empty_returns_zero(self):
        assert update_email_read_status_batch("acc-1", [], True) == 0

    def test_happy_path_returns_updated_count(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_read_status_batch.return_value = 3
            result = update_email_read_status_batch("acc-1", ["m1", "m2", "m3"], True)
        assert result == 3
        call_args = mock_store.update_read_status_batch.call_args
        assert call_args[0][0] == "acc-1"
        rows = call_args[0][1]
        assert len(rows) == 3
        assert rows[0] == ("m1", "acc-1", True)

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_read_status_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                update_email_read_status_batch("acc-1", ["m1"], False)

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_read_status_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to update email read status"):
                update_email_read_status_batch("acc-1", ["m1"], True)


# ------------------------------------------------------------------
# update_email_spam_status_batch
# ------------------------------------------------------------------

class TestUpdateEmailSpamStatusBatch:

    def test_empty_returns_zero(self):
        assert update_email_spam_status_batch("acc-1", [], "SPAM") == 0

    def test_happy_path_returns_updated_count(self):
        results = [
            SpamMoveResult(old_id="old_m1", new_id="new_m1"),
            SpamMoveResult(old_id="old_m2", new_id="new_m2"),
        ]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_spam_status_batch.return_value = 2
            count = update_email_spam_status_batch("acc-1", results, "SPAM")
        assert count == 2
        call_args = mock_store.update_spam_status_batch.call_args
        assert call_args[0][0] == "acc-1"
        rows = call_args[0][1]
        assert len(rows) == 2
        assert rows[0] == ("old_m1", "acc-1", "new_m1", "SPAM")

    def test_database_error_translated(self):
        results = [SpamMoveResult(old_id="old_m1", new_id="new_m1")]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_spam_status_batch.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                update_email_spam_status_batch("acc-1", results, "SPAM")

    def test_generic_exception_raises_api_error(self):
        results = [SpamMoveResult(old_id="old_m1", new_id="new_m1")]
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.update_spam_status_batch.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to update email spam status"):
                update_email_spam_status_batch("acc-1", results, "SPAM")


# ------------------------------------------------------------------
# load_stored_message_ids
# ------------------------------------------------------------------

class TestLoadStoredMessageIds:

    def test_happy_path_returns_ids(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.list_provider_message_ids.return_value = ["m1", "m2"]
            result = load_stored_message_ids("acc-1")
        assert result == ["m1", "m2"]

    def test_database_error_translated(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.list_provider_message_ids.side_effect = QueryError("DB fail")
            with pytest.raises(DatabaseQueryError):
                load_stored_message_ids("acc-1")

    def test_generic_exception_raises_api_error(self):
        with patch("api.services.services_helpers.email_metadata_store") as mock_store:
            mock_store.list_provider_message_ids.side_effect = RuntimeError("boom")
            with pytest.raises(ApiError, match="Failed to load stored message IDs"):
                load_stored_message_ids("acc-1")


# ------------------------------------------------------------------
# is_auth_error
# ------------------------------------------------------------------

class TestIsAuthError:

    def test_true_for_email_auth_error(self):
        exc = EmailAuthError("token expired")
        assert is_auth_error(exc) is True

    def test_false_for_other_core_error(self):
        exc = EmailExternalAPIError("API fail")
        assert is_auth_error(exc) is False

    def test_false_for_non_core_error(self):
        exc = RuntimeError("something")
        assert is_auth_error(exc) is False


# ------------------------------------------------------------------
# unwrap_secret
# ------------------------------------------------------------------

class TestUnwrapSecret:

    def test_none_returns_none(self):
        assert unwrap_secret(None) is None

    def test_secret_str_returns_unwrapped(self):
        secret = SecretStr("my-secret")
        assert unwrap_secret(secret) == "my-secret"

    def test_plain_value_returns_plain(self):
        assert unwrap_secret("plain-value") == "plain-value"


# ------------------------------------------------------------------
# _wrap_secret
# ------------------------------------------------------------------

class TestWrapSecret:

    def test_none_returns_none(self):
        assert _wrap_secret(None) is None

    def test_value_returns_secret_str(self):
        result = _wrap_secret("my-value")
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "my-value"
