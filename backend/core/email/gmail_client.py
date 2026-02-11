from __future__ import annotations
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, List

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import SecretStr

from .email_client import EmailClient, EmailMessage
from .errors import (
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


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
        credentials_payload = self._unwrap_app_credentials(app_credentials)
        if not credentials_payload:
            raise EmailMissingAppCredentialsError()

        client_config = self._build_client_config(credentials_payload)
        flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
        creds = flow.run_local_server(port=0)

        token_record = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
            "scopes": creds.scopes,
        }
        return self._wrap_account_tokens(token_record)

    def authenticate_silent(
        self,
        app_credentials: dict[str, Any] | None = None,
        user_tokens: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Authenticate the Gmail client without starting an interactive OAuth flow.
        """
        credentials_payload = self._unwrap_app_credentials(app_credentials)
        if not credentials_payload:
            raise EmailMissingAppCredentialsError()

        token_payload = self._unwrap_user_tokens(user_tokens)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise EmailMissingTokenError()

        refresh_token = token_payload.get("refresh_token")
        expiry = self._parse_expiry(token_payload.get("expiry"))

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
                raise EmailRefreshFailedError() from exc
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
            return self._wrap_account_tokens(token_record)
        return None

    def _unwrap_app_credentials(
        self, app_credentials: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload = dict(app_credentials or {})
        secret = payload.get("client_secret")
        if isinstance(secret, SecretStr):
            payload["client_secret"] = secret.get_secret_value()
        return payload

    def _unwrap_user_tokens(
        self, user_tokens: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload = dict(user_tokens or {})
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if isinstance(access_token, SecretStr):
            payload["access_token"] = access_token.get_secret_value()
        if isinstance(refresh_token, SecretStr):
            payload["refresh_token"] = refresh_token.get_secret_value()
        return payload

    def _build_client_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "installed" in payload or "web" in payload:
            return payload
        return {"installed": payload}

    def _wrap_account_tokens(self, token_data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(token_data or {})
        if "access_token" in payload:
            payload["access_token"] = SecretStr(str(payload.get("access_token")))
        if "refresh_token" in payload:
            payload["refresh_token"] = SecretStr(str(payload.get("refresh_token")))
        return payload

    def _parse_expiry(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return None

    def fetch_unread_emails(self, max_total: int = 200, page_size: int = 50) -> List[EmailMessage]:
        """
        Fetch unread Gmail messages, normalize them into EmailMessage objects
        and return them as a list.
        """
        if self.service is None:
            raise EmailNotAuthenticatedError()

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
            raise EmailNotAuthenticatedError()

        if not recipients:
            raise EmailRecipientsMissingError()

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
