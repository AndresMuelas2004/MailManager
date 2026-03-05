"""Shared fake email client and metadata builder used by tests."""

from __future__ import annotations

from datetime import datetime

from core.email import EmailClient, EmailMetadata


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
        metadata: list[EmailMetadata] | None = None,
        sync_cursor_return: str = DEFAULT_SYNC_CURSOR,
        auth_return: dict | None = None,
        auth_silent_return: dict | None = None,
    ) -> None:
        self._account_label = account_label
        self._auth_exc = auth_exc
        self._auth_silent_exc = auth_silent_exc
        self._fetch_exc = fetch_exc
        self._send_exc = send_exc
        self._metadata = list(metadata or [])
        self._sync_cursor_return = sync_cursor_return
        self._auth_return = auth_return
        self._auth_silent_return = auth_silent_return
        self.authenticate_calls = 0
        self.authenticate_silent_calls = 0
        self.fetch_calls = 0
        self.sent_emails: list[tuple[str, str, list[str]]] = []
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
    ) -> tuple[list[EmailMetadata], str]:
        self.fetch_calls += 1
        self.last_sync_cursor = sync_cursor
        if self._fetch_exc:
            raise self._fetch_exc
        return list(self._metadata), self._sync_cursor_return

    def send_email(self, subject: str, body: str, recipients: list[str]) -> None:
        if self._send_exc:
            raise self._send_exc
        self.sent_emails.append((subject, body, list(recipients)))

    def get_account_label(self) -> str:
        return self._account_label
