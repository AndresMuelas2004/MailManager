import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

BACKEND_PATH = Path(__file__).resolve().parents[1]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from api.app import create_app
from core.email import EmailManager
from tests.shared.email_fakes import FakeEmailClient, build_message


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def test_client_base(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def temp_base_dir():
    with TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@pytest.fixture
def sample_messages():
    return [
        build_message(message_id="m1"),
        build_message(message_id="m2"),
        build_message(message_id="m3"),
    ]


@pytest.fixture
def fake_email_manager(sample_messages):
    manager = EmailManager()
    manager.add_client(FakeEmailClient("mb1__acc1", unread_messages=sample_messages))
    return manager
