from __future__ import annotations

import json

import pytest

from api.database.security.app_credentials import load_app_credentials
from api.errors.exceptions import AccountMisconfigured, CredentialFileError


def test_gmail_installed_key(monkeypatch, tmp_path):
    creds = {"installed": {"client_id": "cid", "client_secret": "cs"}}
    path = tmp_path / "gmail.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    monkeypatch.setenv("MIA_GMAIL_CREDENTIALS_PATH", str(path))

    result = load_app_credentials("gmail")
    assert result == {"client_id": "cid", "client_secret": "cs"}


def test_gmail_web_key(monkeypatch, tmp_path):
    creds = {"web": {"client_id": "cid"}}
    path = tmp_path / "gmail.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    monkeypatch.setenv("MIA_GMAIL_CREDENTIALS_PATH", str(path))

    result = load_app_credentials("gmail")
    assert result == {"client_id": "cid"}


def test_outlook_flat_dict(monkeypatch, tmp_path):
    creds = {"client_id": "cid", "client_secret": "cs", "tenant": "t"}
    path = tmp_path / "outlook.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    monkeypatch.setenv("MIA_OUTLOOK_CREDENTIALS_PATH", str(path))

    result = load_app_credentials("outlook")
    assert result == creds


def test_missing_file_raises_credential_file_error(monkeypatch):
    monkeypatch.setenv("MIA_GMAIL_CREDENTIALS_PATH", "/nonexistent/path.json")

    with pytest.raises(CredentialFileError, match="Failed to read config storage file"):
        load_app_credentials("gmail")


def test_invalid_json_raises_credential_file_error(monkeypatch, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("MIA_GMAIL_CREDENTIALS_PATH", str(path))

    with pytest.raises(CredentialFileError, match="Failed to read config storage file"):
        load_app_credentials("gmail")


def test_non_dict_data_raises_credential_file_error(monkeypatch, tmp_path):
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    monkeypatch.setenv("MIA_GMAIL_CREDENTIALS_PATH", str(path))

    with pytest.raises(CredentialFileError, match="Config storage file is corrupted"):
        load_app_credentials("gmail")


def test_unknown_provider_raises_account_misconfigured(monkeypatch):
    with pytest.raises(AccountMisconfigured, match="Unknown provider"):
        load_app_credentials("yahoo")
