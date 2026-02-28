"""Shared fake email client and message builder used by tests."""

from __future__ import annotations

from datetime import datetime

from core.email import EmailClient, EmailMessage


DEFAULT_SENT_AT = datetime(2024, 1, 1, 12, 0, 0)


def build_message(
    message_id: str = "m1",
    subject: str = "subject",
    sender: str = "sender@example.com",
    recipients: list[str] | None = None,
    body: str = "body",
    sent_at: datetime | None = None,
    is_unread: bool = True,
    provider: str = "fake",
    thread_id: str | None = None,
    raw_rfc822_b64url: str | None = None,
) -> EmailMessage:
    """Build a normalized ``EmailMessage`` with sensible defaults."""
    if recipients is None:
        recipients = ["recipient@example.com"]
    if sent_at is None:
        sent_at = DEFAULT_SENT_AT
    return EmailMessage(
        message_id=message_id,
        subject=subject,
        sender=sender,
        recipients=recipients,
        body=body,
        sent_at=sent_at,
        is_unread=is_unread,
        provider=provider,
        thread_id=thread_id,
        raw_rfc822_b64url=raw_rfc822_b64url,
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
        unread_messages: list[EmailMessage] | None = None,
        auth_return: dict | None = None,
        auth_silent_return: dict | None = None,
    ) -> None:
        self._account_label = account_label
        self._auth_exc = auth_exc
        self._auth_silent_exc = auth_silent_exc
        self._fetch_exc = fetch_exc
        self._send_exc = send_exc
        self._unread_messages = list(unread_messages or [])
        self._auth_return = auth_return
        self._auth_silent_return = auth_silent_return
        self.authenticate_calls = 0
        self.authenticate_silent_calls = 0
        self.fetch_calls = 0
        self.sent_emails: list[tuple[str, str, list[str]]] = []
        self.last_app_credentials = None
        self.last_user_tokens = None

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

    def fetch_unread_emails(self) -> list[EmailMessage]:
        self.fetch_calls += 1
        if self._fetch_exc:
            raise self._fetch_exc
        return list(self._unread_messages)

    def send_email(self, subject: str, body: str, recipients: list[str]) -> None:
        if self._send_exc:
            raise self._send_exc
        self.sent_emails.append((subject, body, list(recipients)))

    def get_account_label(self) -> str:
        return self._account_label

