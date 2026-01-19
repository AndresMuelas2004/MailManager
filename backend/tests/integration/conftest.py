from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest

from api.services import accounts_service, emails_service, services_helpers
from api.storage import json_store
from core.email.email_manager import EmailManager

_UNIT_CONFTEST_PATH = (
    Path(__file__).resolve().parents[1] / "unit" / "core" / "conftest.py"
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


@pytest.fixture(scope="session")
def fake_client_class():
    return FakeEmailClient


@pytest.fixture
def test_client(test_client_base, sample_messages, monkeypatch):
    def _build_manager(accounts):
        manager = EmailManager()
        for account in accounts:
            mailbox_id = str(account.get("mailbox_id") or "")
            account_id = str(account.get("account_id") or "")
            label = f"{mailbox_id}__{account_id}"
            manager.add_client(
                FakeEmailClient(label, unread_messages=sample_messages)
            )
        return manager

    monkeypatch.setattr(services_helpers, "build_manager_for_accounts", _build_manager)
    monkeypatch.setattr(accounts_service, "build_manager_for_accounts", _build_manager)
    monkeypatch.setattr(emails_service, "build_manager_for_accounts", _build_manager)
    return test_client_base


@pytest.fixture
def storage_path(temp_base_dir):
    return Path(temp_base_dir) / "test_storage.json"


@pytest.fixture
def mailbox_store():
    return json_store.mailbox_store


@pytest.fixture
def account_store():
    return json_store.account_store


@pytest.fixture
def token_path_dir(temp_base_dir, monkeypatch):
    token_dir = Path(temp_base_dir) / f"tokens_{uuid4().hex}"
    token_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MIA_GMAIL_TOKEN_PATH", str(token_dir))
    return token_dir


@pytest.fixture(autouse=True)
def isolated_storage(temp_base_dir, monkeypatch):
    original_mailboxes_path = json_store._MAILBOXES_PATH
    original_accounts_path = json_store._ACCOUNTS_PATH

    original_mailboxes = (
        original_mailboxes_path.read_text(encoding="utf-8")
        if original_mailboxes_path.exists()
        else None
    )
    original_accounts = (
        original_accounts_path.read_text(encoding="utf-8")
        if original_accounts_path.exists()
        else None
    )

    temp_root = Path(temp_base_dir) / f"storage_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_mailboxes = temp_root / "mailboxes.json"
    temp_accounts = temp_root / "accounts.json"

    temp_mailboxes.write_text(original_mailboxes or "[]", encoding="utf-8")
    temp_accounts.write_text(original_accounts or "[]", encoding="utf-8")

    monkeypatch.setattr(json_store, "_MAILBOXES_PATH", temp_mailboxes)
    monkeypatch.setattr(json_store, "_ACCOUNTS_PATH", temp_accounts)

    yield

    if original_mailboxes is not None and original_mailboxes_path.exists():
        current = original_mailboxes_path.read_text(encoding="utf-8")
        if current != original_mailboxes:
            original_mailboxes_path.write_text(original_mailboxes, encoding="utf-8")

    if original_accounts is not None and original_accounts_path.exists():
        current = original_accounts_path.read_text(encoding="utf-8")
        if current != original_accounts:
            original_accounts_path.write_text(original_accounts, encoding="utf-8")
