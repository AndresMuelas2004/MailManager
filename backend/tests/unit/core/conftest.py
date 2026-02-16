import sys
from pathlib import Path

import pytest

BACKEND_PATH = Path(__file__).resolve().parents[3]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from core.email.email_manager import EmailManager
from tests.shared.email_fakes import FakeEmailClient, build_message


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
