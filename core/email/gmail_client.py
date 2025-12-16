from __future__ import annotations
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from .email_client import EmailClient, EmailMessage
from google.auth.exceptions import RefreshError
from typing import List
from googleapiclient.errors import HttpError
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

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
                try:
                    creds.refresh(Request())
                except RefreshError:
                    os.remove(token_path)
                    creds = None

            if not creds:
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
        if self.service is None:
            raise RuntimeError("GmailClient is not authenticated. Call authenticate() first.")

        unread_emails: List[EmailMessage] = []

        try:
            # Fetch a limited number of unread message IDs from Gmail inbox
            response = self.service.users().messages().list(
                userId="me",
                q="in:inbox is:unread category:primary",
                maxResults=10,
            ).execute()

            messages = response.get("messages", [])

            for message_meta in messages:
                message_id = message_meta["id"]

                message = self.service.users().messages().get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()

                headers = {
                    header["name"]: header["value"]
                    for header in message.get("payload", {}).get("headers", [])
                }

                subject = headers.get("Subject", "")
                sender = headers.get("From", "")
                recipients = [headers["To"]] if "To" in headers else []
                body_preview = message.get("snippet", "")

                date_value = headers.get("Date")
                sent_at = parsedate_to_datetime(date_value) if date_value else datetime.now(timezone.utc)

                unread_emails.append(
                    EmailMessage(
                        message_id=message_id,
                        subject=subject,
                        sender=sender,
                        recipients=recipients,
                        body=body_preview,
                        sent_at=sent_at,
                        is_unread=True,
                        provider="gmail",
                        raw_payload=message,
                    )
                )

        except HttpError as error:
            print(f"Failed to fetch unread emails from Gmail: {error}")

        return unread_emails
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