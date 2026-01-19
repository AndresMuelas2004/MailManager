import sys
from datetime import datetime
from pathlib import Path

import pytest

BACKEND_PATH = Path(__file__).resolve().parents[4]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from core.email.email_client import EmailClient, EmailMessage
from core.email.email_manager import EmailManager


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
    def __init__(
        self,
        account_label: str,
        *,
        auth_exc: Exception | None = None,
        auth_silent_exc: Exception | None = None,
        fetch_exc: Exception | None = None,
        unread_messages: list[EmailMessage] | None = None,
    ) -> None:
        self._account_label = account_label
        self._auth_exc = auth_exc
        self._auth_silent_exc = auth_silent_exc
        self._fetch_exc = fetch_exc
        self._unread_messages = list(unread_messages or [])
        self.authenticate_calls = 0
        self.authenticate_silent_calls = 0
        self.fetch_calls = 0
        self.sent_emails: list[tuple[str, str, list[str]]] = []

    def authenticate(self) -> None:
        self.authenticate_calls += 1
        if self._auth_exc:
            raise self._auth_exc

    def authenticate_silent(self) -> None:
        self.authenticate_silent_calls += 1
        if self._auth_silent_exc:
            raise self._auth_silent_exc

    def fetch_unread_emails(self) -> list[EmailMessage]:
        self.fetch_calls += 1
        if self._fetch_exc:
            raise self._fetch_exc
        return list(self._unread_messages)

    def send_email(self, subject: str, body: str, recipients: list[str]) -> None:
        self.sent_emails.append((subject, body, list(recipients)))

    def get_account_label(self) -> str:
        return self._account_label


@pytest.fixture
def manager() -> EmailManager:
    return EmailManager()


@pytest.fixture
def message_factory():
    def _factory(**kwargs):
        return build_message(**kwargs)

    return _factory


@pytest.fixture
def sample_messages(message_factory):
    return [
        message_factory(message_id="m1"),
        message_factory(message_id="m2"),
        message_factory(message_id="m3"),
    ]


@pytest.fixture
def fake_client_ok(sample_messages):
    return FakeEmailClient("acct_ok", unread_messages=[sample_messages[0]])


@pytest.fixture
def fake_client_ok_2(sample_messages):
    return FakeEmailClient("acct_ok_2", unread_messages=[sample_messages[1]])


@pytest.fixture
def fake_client_fail_auth():
    return FakeEmailClient("acct_fail_auth", auth_exc=Exception("boom"))


@pytest.fixture
def fake_client_fail_auth_silent():
    return FakeEmailClient("acct_fail_auth_silent", auth_silent_exc=Exception("boom"))


@pytest.fixture
def fake_client_fail_fetch():
    return FakeEmailClient("acct_fail_fetch", fetch_exc=Exception("boom"))


@pytest.fixture
def fake_client_factory():
    def _factory(label: str, **kwargs):
        return FakeEmailClient(label, **kwargs)

    return _factory
