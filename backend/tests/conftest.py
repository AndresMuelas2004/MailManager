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
from tests.shared.email_fakes import FakeEmailClient, build_metadata


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
def sample_metadata():
    return [
        build_metadata(provider_message_id="m1"),
        build_metadata(provider_message_id="m2"),
        build_metadata(provider_message_id="m3"),
    ]


@pytest.fixture
def fake_email_manager(sample_metadata):
    manager = EmailManager()
    manager.add_client(FakeEmailClient("mb1__acc1", metadata=sample_metadata))
    return manager
