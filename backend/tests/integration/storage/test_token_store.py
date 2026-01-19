import pytest

from api.errors.exceptions import ProviderNotSupported
from api.storage import token_store


@pytest.mark.integration
def test_token_path_for_gmail_account(token_path_dir):
    record = {
        "mailbox_id": "mb1",
        "account_id": "acc1",
        "provider": "gmail",
    }
    path = token_store.token_path_for_account(record)
    expected = token_path_dir / "gmail_token_mb1__acc1.json"
    assert path == expected


@pytest.mark.integration
def test_delete_account_tokens_removes_file(token_path_dir):
    record = {
        "mailbox_id": "mb1",
        "account_id": "acc1",
        "provider": "gmail",
    }
    path = token_store.token_path_for_account(record)
    path.write_text("token", encoding="utf-8")
    assert path.exists()

    token_store.delete_account_tokens(record)
    assert not path.exists()


@pytest.mark.integration
def test_delete_account_tokens_for_records_ignores_missing_files(token_path_dir):
    records = [
        {"mailbox_id": "mb1", "account_id": "acc1", "provider": "gmail"},
        {"mailbox_id": "mb2", "account_id": "acc2", "provider": "gmail"},
    ]
    token_store.delete_account_tokens_for_records(records)


@pytest.mark.integration
def test_token_path_for_account_unsupported_provider():
    record = {
        "mailbox_id": "mb1",
        "account_id": "acc1",
        "provider": "yahoo",
    }
    with pytest.raises(ProviderNotSupported):
        token_store.token_path_for_account(record)
