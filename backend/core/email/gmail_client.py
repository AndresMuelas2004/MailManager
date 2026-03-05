from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .email_client import EmailClient, EmailMetadata
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

_BATCH_SIZE = 100


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
            raise EmailMissingAppCredentialsError("Gmail interactive auth requires app credentials.")

        client_config = self._build_client_config(credentials_payload)
        try:
            flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
        except Exception as exc:
            raise EmailMissingAppCredentialsError(
                f"Gmail failed to build OAuth flow from app credentials: {exc}"
            ) from exc
        try:
            creds = flow.run_local_server(port=0)
        except OSError as exc:
            raise EmailExternalAPIError(
                f"Gmail failed to start local OAuth callback server: {exc}"
            ) from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Gmail unexpected OAuth flow error ({type(exc).__name__}): {exc}"
            ) from exc

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
            raise EmailMissingAppCredentialsError("Gmail silent auth requires app credentials.")

        token_payload = unwrap_user_tokens(user_tokens)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise EmailMissingTokenError("Gmail silent auth requires access_token.")

        refresh_token = token_payload.get("refresh_token")
        expiry = parse_expiry(token_payload.get("expiry"))

        token_uri = credentials_payload.get("token_uri")
        client_id = credentials_payload.get("client_id")
        client_secret = credentials_payload.get("client_secret")
        missing_fields = [
            field for field in ("token_uri", "client_id", "client_secret")
            if not credentials_payload.get(field)
        ]
        if missing_fields:
            raise EmailMissingAppCredentialsError(
                f"Missing required app credentials for Gmail silent auth: {', '.join(missing_fields)}."
            )

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
            except TransportError as exc:
                raise EmailRefreshFailedError(f"Gmail token refresh transport error: {exc}") from exc
            except RefreshError as exc:
                raise EmailRefreshFailedError(
                    f"Gmail token refresh rejected by provider: {exc}"
                ) from exc
            except Exception as exc:
                raise EmailRefreshFailedError(
                    f"Gmail unexpected token refresh error ({type(exc).__name__}): {exc}"
                ) from exc
        elif creds.expired and not creds.refresh_token:
            raise EmailMissingRefreshTokenError("Gmail token expired and refresh_token is missing.")

        try:
            self.service = build("gmail", "v1", credentials=creds)
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Gmail failed to initialize API service ({type(exc).__name__}): {exc}"
            ) from exc
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

    # ------------------------------------------------------------------
    # Metadata sync
    # ------------------------------------------------------------------

    def fetch_email_metadata(
        self,
        sync_cursor: str | None = None,
        max_total: int = 500,
    ) -> tuple[list[EmailMetadata], str]:
        """
        Fetch email metadata from Gmail.

        Returns (metadata_list, new_sync_cursor).
        """
        if self.service is None:
            raise EmailNotAuthenticatedError("Gmail fetch_email_metadata requires authentication.")

        if sync_cursor is not None and self._is_sync_cursor_valid(sync_cursor):
            # ------ Path 2: Incremental sync via users.history.list ------
            # TODO: return self._incremental_email_metadata(sync_cursor)
            pass

        # ------ Path 1: Bootstrap (full fetch) ------
        return self._bootstrap_email_metadata(max_total)

    def _bootstrap_email_metadata(
        self,
        max_total: int,
    ) -> tuple[list[EmailMetadata], str]:
        """Path 1: Full bootstrap fetch of message metadata."""
        message_ids = self._list_message_ids(max_total)
        metadata_list = self._batch_fetch_metadata(message_ids)
        history_id = self._get_current_history_id()
        return metadata_list, history_id

    def _list_message_ids(self, max_total: int) -> list[str]:
        """List message IDs using pagination, including spam and trash."""
        ids: list[str] = []
        page_token = None
        page_size = min(max_total, 500)

        while True:
            list_kwargs: dict[str, Any] = {
                "userId": "me",
                "maxResults": page_size,
                "includeSpamTrash": True,
            }
            if page_token:
                list_kwargs["pageToken"] = page_token

            try:
                response = self.service.users().messages().list(**list_kwargs).execute()
            except HttpError as exc:
                status = getattr(exc.resp, "status", "unknown")
                reason = getattr(exc, "reason", "unknown")
                raise EmailExternalAPIError(
                    f"Gmail failed to fetch message list (HTTP {status}: {reason})."
                ) from exc
            except Exception as exc:
                raise EmailExternalAPIError(
                    f"Gmail unexpected fetch message list error ({type(exc).__name__}): {exc}"
                ) from exc

            for msg in response.get("messages", []):
                msg_id = str(msg.get("id") or "").strip()
                if msg_id:
                    ids.append(msg_id)

            if len(ids) >= max_total:
                ids = ids[:max_total]
                break

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return ids

    def _batch_fetch_metadata(self, message_ids: list[str]) -> list[EmailMetadata]:
        """Fetch metadata for message IDs using Gmail BatchHttpRequest."""
        results: list[EmailMetadata] = []

        for chunk_start in range(0, len(message_ids), _BATCH_SIZE):
            chunk = message_ids[chunk_start:chunk_start + _BATCH_SIZE]
            batch_results: dict[str, dict[str, Any]] = {}

            def _callback(request_id: str, response: Any, exception: Any) -> None:
                if exception is not None:
                    return
                batch_results[request_id] = response

            try:
                batch = self.service.new_batch_http_request(callback=_callback)
                for msg_id in chunk:
                    batch.add(
                        self.service.users().messages().get(
                            userId="me",
                            id=msg_id,
                            format="metadata",
                            metadataHeaders=["From", "Subject"],
                        ),
                        request_id=msg_id,
                    )
                batch.execute()
            except HttpError as exc:
                status = getattr(exc.resp, "status", "unknown")
                reason = getattr(exc, "reason", "unknown")
                raise EmailExternalAPIError(
                    f"Gmail batch metadata fetch failed (HTTP {status}: {reason})."
                ) from exc
            except Exception as exc:
                raise EmailExternalAPIError(
                    f"Gmail unexpected batch fetch error ({type(exc).__name__}): {exc}"
                ) from exc

            for msg_id in chunk:
                msg = batch_results.get(msg_id)
                if msg is None:
                    continue
                results.append(self._parse_metadata_response(msg))

        return results

    @staticmethod
    def _parse_metadata_response(msg: dict[str, Any]) -> EmailMetadata:
        """Parse a Gmail message response (format=metadata) into EmailMetadata."""
        headers = {
            h["name"]: h["value"]
            for h in (msg.get("payload") or {}).get("headers", [])
        }

        from_header = headers.get("From", "")
        from_name, from_email = parseaddr(from_header)

        label_ids = msg.get("labelIds") or []
        is_read = "UNREAD" not in label_ids

        if "SPAM" in label_ids:
            box = "SPAM"
        elif "TRASH" in label_ids:
            box = "TRASH"
        else:
            box = "ALL_MAIL"

        internal_date = msg.get("internalDate")
        if internal_date:
            received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
        else:
            received_at = datetime.now(timezone.utc)

        return EmailMetadata(
            provider_message_id=msg.get("id", ""),
            thread_id=msg.get("threadId", ""),
            from_email=from_email or "",
            from_name=from_name or "",
            subject=headers.get("Subject", ""),
            received_at=received_at,
            is_read=is_read,
            box=box,
        )

    def _get_current_history_id(self) -> str:
        """Retrieve the current historyId from the user's Gmail profile."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return str(profile.get("historyId", ""))
        except HttpError as exc:
            status = getattr(exc.resp, "status", "unknown")
            reason = getattr(exc, "reason", "unknown")
            raise EmailExternalAPIError(
                f"Gmail failed to fetch profile for historyId (HTTP {status}: {reason})."
            ) from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Gmail unexpected getProfile error ({type(exc).__name__}): {exc}"
            ) from exc

    def _is_sync_cursor_valid(self, sync_cursor: str) -> bool:
        """Check if historyId is still valid by probing users.history.list."""
        try:
            self.service.users().history().list(
                userId="me", startHistoryId=sync_cursor, maxResults=1,
            ).execute()
            return True
        except HttpError:
            return False
        except Exception:
            return False

    def _incremental_email_metadata(
        self, sync_cursor: str,
    ) -> tuple[list[EmailMetadata], str]:
        """Camino 2: Incremental sync via history.list. NOT YET IMPLEMENTED."""
        raise NotImplementedError("Gmail incremental sync not yet implemented.")

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

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
            raise EmailNotAuthenticatedError("Gmail send_email requires authentication.")

        if not recipients:
            raise EmailRecipientsMissingError("Gmail send_email requires at least one recipient.")

        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = ", ".join(recipients)
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        payload = {"raw": raw_message}

        try:
            self.service.users().messages().send(userId="me", body=payload).execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", "unknown")
            reason = getattr(exc, "reason", "unknown")
            raise EmailExternalAPIError(
                f"Gmail failed to send email (HTTP {status}: {reason})."
            ) from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Gmail unexpected send email error ({type(exc).__name__}): {exc}"
            ) from exc

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Gmail account inside the app.
        """
        return self._account_label
