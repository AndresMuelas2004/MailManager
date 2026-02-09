import sys
from pathlib import Path

BACKEND_PATH = Path(__file__).resolve().parents[4]
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

import pytest

import core.email.gmail_client as gmail_module
from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient
from core.email.errors import (
    EmailAccountNotFoundError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from google.auth.exceptions import RefreshError


def test_manager_connect_account_not_found_raises_error(manager: EmailManager):
    with pytest.raises(EmailAccountNotFoundError):
        manager.connect_account("unknown")


def test_manager_send_email_not_found_raises_error(manager: EmailManager):
    with pytest.raises(EmailAccountNotFoundError):
        manager.send_email_from_account("unknown", "s", "b", ["a@example.com"])


def test_gmail_authenticate_requires_app_credentials():
    client = GmailClient()
    with pytest.raises(EmailMissingAppCredentialsError):
        client.authenticate(None)


def test_gmail_authenticate_silent_requires_app_credentials():
    client = GmailClient()
    with pytest.raises(EmailMissingAppCredentialsError):
        client.authenticate_silent(None, {})


def test_gmail_authenticate_silent_requires_access_token():
    client = GmailClient()
    app_credentials = {"token_uri": "uri", "client_id": "cid", "client_secret": "secret"}
    with pytest.raises(EmailMissingTokenError):
        client.authenticate_silent(app_credentials, {})


def test_gmail_authenticate_silent_missing_required_app_fields():
    client = GmailClient()
    app_credentials = {"client_id": "cid"}  # missing token_uri and client_secret
    tokens = {"access_token": "tok"}
    with pytest.raises(EmailMissingAppCredentialsError):
        client.authenticate_silent(app_credentials, tokens)


def test_gmail_authenticate_silent_missing_refresh_token(monkeypatch):
    class FakeCredentials:
        def __init__(
            self,
            token=None,
            refresh_token=None,
            token_uri=None,
            client_id=None,
            client_secret=None,
            scopes=None,
            expiry=None,
        ):
            self.token = token
            self.refresh_token = refresh_token
            self.token_uri = token_uri
            self.client_id = client_id
            self.client_secret = client_secret
            self.scopes = scopes
            self.expiry = expiry
            self.expired = True

        def refresh(self, request):
            self.expired = False

    monkeypatch.setattr(gmail_module, "Credentials", FakeCredentials)

    client = GmailClient()
    app_credentials = {"token_uri": "uri", "client_id": "cid", "client_secret": "secret"}
    tokens = {"access_token": "tok"}
    with pytest.raises(EmailMissingRefreshTokenError):
        client.authenticate_silent(app_credentials, tokens)


def test_gmail_authenticate_silent_refresh_error(monkeypatch):
    class FakeCredentials:
        def __init__(
            self,
            token=None,
            refresh_token=None,
            token_uri=None,
            client_id=None,
            client_secret=None,
            scopes=None,
            expiry=None,
        ):
            self.token = token
            self.refresh_token = refresh_token
            self.token_uri = token_uri
            self.client_id = client_id
            self.client_secret = client_secret
            self.scopes = scopes
            self.expiry = expiry
            self.expired = True

        def refresh(self, request):
            raise RefreshError("refresh failed")

    monkeypatch.setattr(gmail_module, "Credentials", FakeCredentials)
    monkeypatch.setattr(gmail_module, "Request", lambda: object())

    client = GmailClient()
    app_credentials = {"token_uri": "uri", "client_id": "cid", "client_secret": "secret"}
    tokens = {"access_token": "tok", "refresh_token": "ref"}
    with pytest.raises(EmailRefreshFailedError):
        client.authenticate_silent(app_credentials, tokens)


def test_gmail_fetch_unread_requires_authentication():
    client = GmailClient()
    with pytest.raises(EmailNotAuthenticatedError):
        client.fetch_unread_emails()


def test_gmail_send_email_requires_authentication():
    client = GmailClient()
    with pytest.raises(EmailNotAuthenticatedError):
        client.send_email("s", "b", ["a@example.com"])


def test_gmail_send_email_requires_recipients():
    client = GmailClient()
    client.service = object()  # mark as authenticated
    with pytest.raises(EmailRecipientsMissingError):
        client.send_email("s", "b", [])
