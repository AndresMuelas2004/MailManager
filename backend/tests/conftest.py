import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_PATH = Path(__file__).resolve().parents[1]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from api.app import create_app
from tests.shared.email_fakes import build_metadata


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def test_client_base(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_metadata():
    return [
        build_metadata(provider_message_id="m1"),
        build_metadata(provider_message_id="m2"),
        build_metadata(provider_message_id="m3"),
    ]
