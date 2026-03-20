"""Shared fake email client and metadata builder used by tests."""

from __future__ import annotations

from datetime import datetime

from core.email import EmailClient, EmailMetadata, LabelUpdate, SyncResult


DEFAULT_RECEIVED_AT = datetime(2024, 1, 1, 12, 0, 0)
DEFAULT_SYNC_CURSOR = "fake_cursor_12345"


def build_metadata(
    provider_message_id: str = "m1",
    thread_id: str = "t1",
    from_email: str = "sender@example.com",
    from_name: str = "Sender",
    subject: str = "subject",
    received_at: datetime | None = None,
    is_read: bool = False,
    box: str = "ALL_MAIL",
    account_id: str = "",
) -> EmailMetadata:
    """Build a normalized ``EmailMetadata`` with sensible defaults."""
    if received_at is None:
        received_at = DEFAULT_RECEIVED_AT
    return EmailMetadata(
        provider_message_id=provider_message_id,
        thread_id=thread_id,
        from_email=from_email,
        from_name=from_name,
        subject=subject,
        received_at=received_at,
        is_read=is_read,
        box=box,
        account_id=account_id,
    )


class FakeEmailClient(EmailClient):
    """In-memory fake that can simulate provider successes and failures."""

    def __init__(
        self,
        account_label: str,
        *,
        auth_exc: Exception | None = None,
        auth_silent_exc: Exception | None = None,
        fetch_exc: Exception | None = None,
        send_exc: Exception | None = None,
        verify_exc: Exception | None = None,
        delete_exc: Exception | None = None,
        restore_exc: Exception | None = None,
        move_to_trash_exc: Exception | None = None,
        fetch_messages_metadata_exc: Exception | None = None,
        metadata: list[EmailMetadata] | None = None,
        sync_cursor_return: str = DEFAULT_SYNC_CURSOR,
        auth_return: dict | None = None,
        auth_silent_return: dict | None = None,
        deletes: list[str] | None = None,
        label_updates: list[LabelUpdate] | None = None,
        existing_message_ids: list[str] | None = None,
        is_full_sync: bool = False,
        delete_return: list[str] | None = None,
        restore_return: dict[str, str] | None = None,
        move_to_trash_return: dict[str, str] | None = None,
        fetch_messages_metadata_return: list[EmailMetadata] | None = None,
    ) -> None:
        self._account_label = account_label
        self._auth_exc = auth_exc
        self._auth_silent_exc = auth_silent_exc
        self._fetch_exc = fetch_exc
        self._send_exc = send_exc
        self._verify_exc = verify_exc
        self._delete_exc = delete_exc
        self._restore_exc = restore_exc
        self._move_to_trash_exc = move_to_trash_exc
        self._fetch_messages_metadata_exc = fetch_messages_metadata_exc
        self._metadata = list(metadata or [])
        self._sync_cursor_return = sync_cursor_return
        self._auth_return = auth_return
        self._auth_silent_return = auth_silent_return
        self._deletes = list(deletes or [])
        self._label_updates = list(label_updates or [])
        self._existing_message_ids = set(existing_message_ids or [])
        self._is_full_sync = is_full_sync
        self._delete_return = delete_return
        self._restore_return = restore_return
        self._move_to_trash_return = move_to_trash_return
        self._fetch_messages_metadata_return = fetch_messages_metadata_return
        self.authenticate_calls = 0
        self.authenticate_silent_calls = 0
        self.fetch_calls = 0
        self.verify_calls = 0
        self.delete_calls = 0
        self.restore_calls = 0
        self.move_to_trash_calls = 0
        self.fetch_messages_metadata_calls = 0
        self.sent_emails: list[tuple[str, str, list[str]]] = []
        self.deleted_message_ids: list[str] = []
        self.restored_items: list[dict] = []
        self.trashed_items: list[dict[str, str]] = []
        self.last_app_credentials = None
        self.last_user_tokens = None
        self.last_sync_cursor = None

    def authenticate(self, app_credentials=None) -> dict | None:
        self.authenticate_calls += 1
        self.last_app_credentials = app_credentials
        if self._auth_exc:
            raise self._auth_exc
        return self._auth_return

    def authenticate_silent(self, app_credentials=None, user_tokens=None) -> dict | None:
        self.authenticate_silent_calls += 1
        self.last_app_credentials = app_credentials
        self.last_user_tokens = user_tokens
        if self._auth_silent_exc:
            raise self._auth_silent_exc
        return self._auth_silent_return

    def fetch_email_metadata(
        self,
        sync_cursor: str | None = None,
        max_total: int = 500,
    ) -> SyncResult:
        self.fetch_calls += 1
        self.last_sync_cursor = sync_cursor
        if self._fetch_exc:
            raise self._fetch_exc
        return SyncResult(
            upserts=list(self._metadata),
            new_cursor=self._sync_cursor_return,
            deletes=list(self._deletes),
            label_updates=list(self._label_updates),
            is_full_sync=self._is_full_sync,
        )

    def verify_message_existence(self, message_ids: list[str]) -> list[str]:
        self.verify_calls += 1
        if self._verify_exc:
            raise self._verify_exc
        return [mid for mid in message_ids if mid in self._existing_message_ids]

    def delete_messages(self, message_ids: list[str]) -> list[str]:
        self.delete_calls += 1
        if self._delete_exc:
            raise self._delete_exc
        result = self._delete_return if self._delete_return is not None else list(message_ids)
        self.deleted_message_ids.extend(result)
        return result

    def restore_from_trash(self, items: dict[str, str | None]) -> dict[str, str]:
        self.restore_calls += 1
        if self._restore_exc:
            raise self._restore_exc
        result = self._restore_return if self._restore_return is not None else {k: k for k in items}
        self.restored_items.append(dict(items))
        return result

    def fetch_messages_metadata(self, message_ids: list[str]) -> list[EmailMetadata]:
        self.fetch_messages_metadata_calls += 1
        if self._fetch_messages_metadata_exc:
            raise self._fetch_messages_metadata_exc
        if self._fetch_messages_metadata_return is not None:
            return list(self._fetch_messages_metadata_return)
        return []

    def move_to_trash(self, message_ids: list[str]) -> dict[str, str]:
        self.move_to_trash_calls += 1
        if self._move_to_trash_exc:
            raise self._move_to_trash_exc
        result = self._move_to_trash_return if self._move_to_trash_return is not None else {mid: mid for mid in message_ids}
        self.trashed_items.append(dict(result))
        return result

    def send_email(self, subject: str, body: str, recipients: list[str]) -> EmailMetadata:
        if self._send_exc:
            raise self._send_exc
        self.sent_emails.append((subject, body, list(recipients)))
        return build_metadata(
            provider_message_id="sent_m1",
            subject=subject,
            box="SENT",
            is_read=True,
        )

    def get_account_label(self) -> str:
        return self._account_label
