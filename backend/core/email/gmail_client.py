from __future__ import annotations
import base64
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from .email_client import EmailClient, EmailMessage
from google.auth.exceptions import RefreshError
from typing import List
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient(EmailClient):
    """
    Concrete implementation of EmailClient for Gmail accounts.
    This class will be responsible for talking to the official Gmail API.
    """

    def __init__(self, account_label: str = "gmail") -> None:
        self._account_label = account_label
        self.service = None

    def authenticate(self) -> None:
        """
        Authenticate the Gmail client using OAuth2.
        """
        creds = None

        credentials_path = os.getenv("MIA_GMAIL_CREDENTIALS_PATH")
        token_dir = os.getenv("MIA_GMAIL_TOKEN_PATH")

        if not credentials_path:
            raise ValueError("MIA_GMAIL_CREDENTIALS_PATH is not set.")

        if not token_dir:
            raise ValueError("MIA_GMAIL_TOKEN_PATH is not set (must be a directory).")

        token_path = os.path.join(token_dir, f"gmail_token_{self._account_label}.json")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError:
                    if os.path.exists(token_path):
                        os.remove(token_path)
                    creds = None

            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path,
                    GMAIL_SCOPES,
                )
                creds = flow.run_local_server(port=0)

            os.makedirs(token_dir, exist_ok=True)
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)

    def authenticate_silent(self) -> None:
        """
        Authenticate the Gmail client without starting an interactive OAuth flow.
        """
        creds = None

        token_dir = os.getenv("MIA_GMAIL_TOKEN_PATH")
        if not token_dir:
            # Missing token directory means silent auth cannot proceed.
            raise ValueError("MIA_GMAIL_TOKEN_PATH is not set (must be a directory).")

        token_path = os.path.join(token_dir, f"gmail_token_{self._account_label}.json")
        if not os.path.exists(token_path):
            # No saved token means the account has not been connected yet.
            raise ValueError("missing_token")

        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    # Refresh tokens allow non-interactive renewal.
                    creds.refresh(Request())
                except RefreshError as exc:
                    if os.path.exists(token_path):
                        os.remove(token_path)
                    raise ValueError("refresh_failed") from exc
            else:
                # Without a refresh token, silent recovery is impossible.
                raise ValueError("missing_refresh_token")

            os.makedirs(token_dir, exist_ok=True)
            # Persist refreshed credentials for future calls.
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)

    def fetch_unread_emails(self, max_total: int = 200, page_size: int = 50) -> List[EmailMessage]:
        """
        Fetch unread Gmail messages, normalize them into EmailMessage objects
        and return them as a list.
        """
        if self.service is None:
            raise RuntimeError("GmailClient is not authenticated. Call authenticate() first.")

        unread_emails: List[EmailMessage] = []

        messages = []
        page_token = None

        # Fetch unread email message IDs from Gmail using pagination and enforce a global max limit.
        while True:
            list_kwargs = {
                "userId": "me",
                "q": "in:inbox is:unread category:primary",
                "maxResults": page_size,
            }
            if page_token:
                list_kwargs["pageToken"] = page_token

            response = self.service.users().messages().list(**list_kwargs).execute()
            messages.extend(response.get("messages", []))

            if len(messages) >= max_total:
                messages = messages[:max_total]
                break

            page_token = response.get("nextPageToken")
            if not page_token:
                break
        
        # Decode the raw RFC822 message and extract normalized email headers from it.
        def parse_headers_from_raw(raw_b64url: str) -> dict:
            if not raw_b64url:
                return {}
            try:
                raw_bytes = base64.urlsafe_b64decode(raw_b64url.encode("utf-8"))
            except Exception:
                return {}

            raw_text = raw_bytes.decode("utf-8", errors="replace")
            header_lines = []
            for line in raw_text.splitlines():
                if line == "":
                    break
                header_lines.append(line)

            unfolded = []
            current = ""
            for line in header_lines:
                if line.startswith((" ", "\t")) and current:
                    current = f"{current} {line.strip()}"
                else:
                    if current:
                        unfolded.append(current)
                    current = line.strip()
            if current:
                unfolded.append(current)

            headers = {}
            for line in unfolded:
                if ":" in line:
                    name, value = line.split(":", 1)
                    headers[name.strip()] = value.strip()
            return headers
        # Retrieve each full email from Gmail in raw format using the previously collected IDs
        for message_meta in messages:
            message_id = message_meta["id"]

            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="raw",
            ).execute()

            raw_rfc822_b64url = message.get("raw", "")
            raw_headers = parse_headers_from_raw(raw_rfc822_b64url)
            # Derive normalized email fields (subject, sender, recipients, body, sent date) with fallbacks.
            def get_header(name: str) -> str:
                return raw_headers.get(name, "")

            subject = get_header("Subject")
            sender = get_header("From")
            to_header = get_header("To")
            recipients = [to_header] if to_header else []
            body = message.get("snippet", "")

            date_value = get_header("Date")
            if date_value:
                sent_at = parsedate_to_datetime(date_value)
            else:
                internal_date = message.get("internalDate")
                if internal_date:
                    sent_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
                else:
                    sent_at = datetime.now(timezone.utc)
            # Build a provider-agnostic EmailMessage object and return the final list of unread emails.
            unread_emails.append(
                EmailMessage(
                    message_id=message_id,
                    thread_id=message.get("threadId"),
                    subject=subject,
                    sender=sender,
                    recipients=recipients,
                    body=body,
                    sent_at=sent_at,
                    is_unread=True,
                    provider="gmail",
                    raw_rfc822_b64url=raw_rfc822_b64url or None,
                )
            )

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
        if self.service is None:
            raise RuntimeError("GmailClient is not authenticated. Call authenticate() first.")

        if not recipients:
            raise ValueError("At least one recipient is required.")

        # Local imports to keep module-level imports unchanged.
        import base64
        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = ", ".join(recipients)
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        payload = {"raw": raw_message}

        self.service.users().messages().send(userId="me", body=payload).execute()

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Gmail account inside the app.
        """
        return self._account_label
