import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

BACKEND_PATH = Path(__file__).resolve().parents[1]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from api.app import create_app
from core.email.email_manager import EmailManager

_UNIT_CONFTEST_PATH = (
    Path(__file__).resolve().parent / "unit" / "core" / "conftest.py"
)


def _load_unit_conftest():
    spec = spec_from_file_location("tests_unit_conftest", _UNIT_CONFTEST_PATH)
    module = module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Unable to load unit conftest module.")
    spec.loader.exec_module(module)
    return module


_unit_conftest = _load_unit_conftest()
FakeEmailClient = _unit_conftest.FakeEmailClient
build_message = _unit_conftest.build_message


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
