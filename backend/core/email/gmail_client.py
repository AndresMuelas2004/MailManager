from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .email_client import EmailClient, EmailMessage
from .errors import (
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from .helpers import (
    parse_expiry,
    unwrap_app_credentials,
    unwrap_user_tokens,
    wrap_account_tokens,
)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _parse_headers_from_raw(raw_b64url: str) -> dict[str, str]:
    """Decode the raw RFC822 message and extract normalized email headers."""
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

    headers: dict[str, str] = {}
    for line in unfolded:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()
    return headers


class GmailClient(EmailClient):
    """
    Concrete implementation of EmailClient for Gmail accounts.
    This class will be responsible for talking to the official Gmail API.
    """

    def __init__(self, account_label: str = "gmail") -> None:
        self._account_label = account_label
        self.service = None

    def authenticate(
        self,
        app_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Authenticate the Gmail client using OAuth2.
        """
        credentials_payload = unwrap_app_credentials(app_credentials)
        if not credentials_payload:
            raise EmailMissingAppCredentialsError()

        client_config = self._build_client_config(credentials_payload)
        flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
        try:
            creds = flow.run_local_server(port=0)
        except Exception as exc:
            raise EmailExternalAPIError(f"Gmail failed to execute OAuth flow: {exc}") from exc

        token_record = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
            "scopes": creds.scopes,
        }
        return wrap_account_tokens(token_record)

    def authenticate_silent(
        self,
        app_credentials: dict[str, Any] | None = None,
        user_tokens: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Authenticate the Gmail client without starting an interactive OAuth flow.
        """
        credentials_payload = unwrap_app_credentials(app_credentials)
        if not credentials_payload:
            raise EmailMissingAppCredentialsError()

        token_payload = unwrap_user_tokens(user_tokens)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise EmailMissingTokenError()

        refresh_token = token_payload.get("refresh_token")
        expiry = parse_expiry(token_payload.get("expiry"))

        token_uri = credentials_payload.get("token_uri")
        client_id = credentials_payload.get("client_id")
        client_secret = credentials_payload.get("client_secret")
        if not token_uri or not client_id or not client_secret:
            raise EmailMissingAppCredentialsError("Missing required app credentials.")

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=token_payload.get("scopes") or GMAIL_SCOPES,
            expiry=expiry,
        )
        refreshed = False
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError as exc:
                raise EmailRefreshFailedError(f"Gmail failed to refresh access token: {exc}") from exc
        elif creds.expired and not creds.refresh_token:
            raise EmailMissingRefreshTokenError()

        self.service = build("gmail", "v1", credentials=creds)
        if refreshed:
            token_record = {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
                "scopes": creds.scopes,
            }
            return wrap_account_tokens(token_record)
        return None

    def _build_client_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "installed" in payload or "web" in payload:
            return payload
        return {"installed": payload}

    def fetch_unread_emails(self, max_total: int = 200, page_size: int = 50) -> list[EmailMessage]:
        """
        Fetch unread Gmail messages, normalize them into EmailMessage objects
        and return them as a list.
        """
        if self.service is None:
            raise EmailNotAuthenticatedError()

        unread_emails: list[EmailMessage] = []

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

            try:
                response = self.service.users().messages().list(**list_kwargs).execute()
            except Exception as exc:
                raise EmailExternalAPIError(f"Gmail failed to fetch message list: {exc}") from exc
            messages.extend(response.get("messages", []))

            if len(messages) >= max_total:
                messages = messages[:max_total]
                break

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        # Retrieve each full email from Gmail in raw format using the previously collected IDs.
        for message_meta in messages:
            message_id = message_meta["id"]

            try:
                message = self.service.users().messages().get(
                    userId="me",
                    id=message_id,
                    format="raw",
                ).execute()
            except Exception as exc:
                raise EmailExternalAPIError(f"Gmail failed to fetch message {message_id}: {exc}") from exc

            raw_rfc822_b64url = message.get("raw", "")
            raw_headers = _parse_headers_from_raw(raw_rfc822_b64url)

            subject = raw_headers.get("Subject", "")
            sender = raw_headers.get("From", "")
            to_header = raw_headers.get("To", "")
            recipients = [to_header] if to_header else []
            body = message.get("snippet", "")

            date_value = raw_headers.get("Date", "")
            if date_value:
                sent_at = parsedate_to_datetime(date_value)
            else:
                internal_date = message.get("internalDate")
                if internal_date:
                    sent_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
                else:
                    sent_at = datetime.now(timezone.utc)

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
        recipients: list[str],
    ) -> None:
        """
        Send a plain text email using the Gmail API.
        """
        if self.service is None:
            raise EmailNotAuthenticatedError()

        if not recipients:
            raise EmailRecipientsMissingError()

        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = ", ".join(recipients)
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        payload = {"raw": raw_message}

        try:
            self.service.users().messages().send(userId="me", body=payload).execute()
        except Exception as exc:
            raise EmailExternalAPIError(f"Gmail failed to send email: {exc}") from exc

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Gmail account inside the app.
        """
        return self._account_label
