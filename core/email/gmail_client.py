from __future__ import annotations
import os
from typing import List
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from .email_client import EmailClient, EmailMessage

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient(EmailClient):
    """
    Concrete implementation of EmailClient for Gmail accounts.
    This class will be responsible for talking to the official Gmail API.
    """

    def __init__(self, account_label: str = "gmail") -> None:
        self.account_label = account_label
        self.service = None

    def authenticate(self) -> None:
        """
        Initialize or refresh the Gmail API client using OAuth2.
        This method will be implemented using the Google client libraries.
        """
        creds = None

        credentials_path = os.getenv("MIA_GMAIL_CREDENTIALS_PATH")
        token_path = os.getenv("MIA_GMAIL_TOKEN_PATH")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, GMAIL_SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)

    def fetch_unread_emails(self) -> List[EmailMessage]:
        """
        Fetch unread Gmail messages, normalize them into EmailMessage objects
        and return them as a list.
        """
        # TODO: Call the Gmail API to list unread messages,
        #       then transform them into EmailMessage instances.
        raise NotImplementedError("GmailClient.fetch_unread_emails() not implemented yet.")

    def send_email(
        self,
        subject: str,
        body: str,
        recipients: List[str],
    ) -> None:
        """
        Send a plain text email using the Gmail API.
        """
        # TODO: Build a MIME message and send it via the Gmail API.
        raise NotImplementedError("GmailClient.send_email() not implemented yet.")

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Gmail account inside the app.
        """
        return self._account_label