from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

logger = logging.getLogger(__name__)

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .email_client import EmailClient, EmailMetadata, LabelUpdate, SyncResult
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
    http_error_detail,
    parse_expiry,
    unwrap_app_credentials,
    unwrap_user_tokens,
    wrap_account_tokens,
)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_BATCH_SIZE = 100
_BATCH_MAX_RETRIES = 3
_BATCH_RETRY_DELAY = 1.0  # seconds


def _log_skipped_messages(
    operation: str, skipped_ids: list[str], message_ids: list[str],
) -> None:
    if skipped_ids:
        logger.warning(
            "Gmail %s: %d/%d messages could not be fetched: %s",
            operation, len(skipped_ids), len(message_ids), skipped_ids[:10],
        )


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
    ) -> SyncResult:
        """
        Fetch email metadata from Gmail.

        Returns a SyncResult with upserts, deletes, label_updates and new_cursor.
        """
        if self.service is None:
            raise EmailNotAuthenticatedError("Gmail fetch_email_metadata requires authentication.")

        if sync_cursor is not None:
            # ------ Path 2: Incremental sync via users.history.list ------
            try:
                return self._incremental_email_metadata(sync_cursor)
            except EmailExternalAPIError:
                pass  # Fallback to bootstrap (e.g. cursor expired / 404 / 410)

        # ------ Path 1: Bootstrap (full fetch) ------
        return self._bootstrap_email_metadata(max_total)

    def _bootstrap_email_metadata(
        self,
        max_total: int,
    ) -> SyncResult:
        """Path 1: Full bootstrap fetch of message metadata."""
        history_id = self._get_current_history_id()
        message_ids = self._list_message_ids(max_total)
        metadata_list = self._batch_fetch_metadata(message_ids)
        return SyncResult(upserts=metadata_list, new_cursor=history_id)

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
                status, reason = http_error_detail(exc)
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

    def _execute_batch_get(
        self,
        message_ids: list[str],
        *,
        fmt: str,
        error_context: str,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Execute a batched messages.get call; returns {msg_id: response}."""
        all_results: dict[str, dict[str, Any]] = {}

        for chunk_start in range(0, len(message_ids), _BATCH_SIZE):
            chunk = message_ids[chunk_start:chunk_start + _BATCH_SIZE]
            chunk_results: dict[str, dict[str, Any]] = {}
            pending_ids = list(chunk)
            resolved_extra = extra_kwargs or {}

            for attempt in range(_BATCH_MAX_RETRIES + 1):
                failed_in_attempt: list[str] = []

                # Default args: _r (shared, accumulates successes) and _f (per-attempt failures).
                def _callback(
                    request_id: str, response: Any, exception: Any,
                    _r: dict[str, dict[str, Any]] = chunk_results,
                    _f: list[str] = failed_in_attempt,
                ) -> None:
                    if exception is not None:
                        _f.append(request_id)
                        return
                    _r[request_id] = response

                try:
                    batch = self.service.new_batch_http_request(callback=_callback)
                    for msg_id in pending_ids:
                        get_kwargs: dict[str, Any] = {
                            "userId": "me", "id": msg_id, "format": fmt,
                            **resolved_extra,
                        }
                        batch.add(
                            self.service.users().messages().get(**get_kwargs),
                            request_id=msg_id,
                        )
                    batch.execute()
                except HttpError as exc:
                    status, reason = http_error_detail(exc)
                    raise EmailExternalAPIError(
                        f"Gmail {error_context} failed (HTTP {status}: {reason})."
                    ) from exc
                except Exception as exc:
                    raise EmailExternalAPIError(
                        f"Gmail unexpected {error_context} error ({type(exc).__name__}): {exc}"
                    ) from exc

                if not failed_in_attempt:
                    if attempt > 0:
                        logger.warning(
                            "Gmail batch: all %d messages recovered (attempt %d/%d)",
                            len(pending_ids), attempt + 1, _BATCH_MAX_RETRIES + 1,
                        )
                    else:
                        logger.info(
                            "Gmail batch: %d messages OK (first attempt)",
                            len(chunk),
                        )
                    break

                if attempt < _BATCH_MAX_RETRIES:
                    logger.warning(
                        "Gmail batch: %d/%d messages failed (attempt %d/%d), retrying in %.1fs",
                        len(failed_in_attempt), len(pending_ids),
                        attempt + 1, _BATCH_MAX_RETRIES + 1, _BATCH_RETRY_DELAY,
                    )
                    time.sleep(_BATCH_RETRY_DELAY)
                    pending_ids = failed_in_attempt
                else:
                    logger.warning(
                        "Gmail batch: %d messages lost after %d attempts: %s",
                        len(failed_in_attempt), _BATCH_MAX_RETRIES + 1,
                        failed_in_attempt[:10],
                    )

            all_results.update(chunk_results)

        return all_results

    def _batch_fetch_metadata(self, message_ids: list[str]) -> list[EmailMetadata]:
        """Fetch metadata for message IDs using Gmail BatchHttpRequest."""
        raw = self._execute_batch_get(
            message_ids,
            fmt="metadata",
            error_context="batch metadata fetch",
            extra_kwargs={"metadataHeaders": ["From", "Subject"]},
        )
        results: list[EmailMetadata] = []
        skipped_ids: list[str] = []
        for msg_id in message_ids:
            msg = raw.get(msg_id)
            if msg is None:
                skipped_ids.append(msg_id)
                continue
            try:
                results.append(self._parse_metadata_response(msg))
            except Exception:
                skipped_ids.append(msg_id)
        _log_skipped_messages("metadata sync", skipped_ids, message_ids)
        return results

    @staticmethod
    def _resolve_labels(label_ids: list[str]) -> tuple[bool, str]:
        """Map Gmail label IDs to (is_read, box)."""
        labels = set(label_ids)
        is_read = "UNREAD" not in labels
        if "SPAM" in labels:
            box = "SPAM"
        elif "TRASH" in labels:
            box = "TRASH"
        else:
            box = "ALL_MAIL"
        return is_read, box

    @staticmethod
    def _parse_metadata_response(msg: dict[str, Any]) -> EmailMetadata:
        """Parse a Gmail message response (format=metadata) into EmailMetadata."""
        headers = {}
        for h in (msg.get("payload") or {}).get("headers", []):
            name = h.get("name")
            if name:
                headers[name] = h.get("value", "")

        from_header = headers.get("From", "")
        from_name, from_email = parseaddr(from_header)

        is_read, box = GmailClient._resolve_labels(msg.get("labelIds") or [])

        internal_date = msg.get("internalDate")
        if internal_date:
            try:
                received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                received_at = datetime.now(timezone.utc)
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
            status, reason = http_error_detail(exc)
            raise EmailExternalAPIError(
                f"Gmail failed to fetch profile for historyId (HTTP {status}: {reason})."
            ) from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Gmail unexpected getProfile error ({type(exc).__name__}): {exc}"
            ) from exc

    def _incremental_email_metadata(
        self, sync_cursor: str,
    ) -> SyncResult:
        """Path 2: Incremental sync via Gmail History API."""
        # Step 1 — Paginate history.list and classify events into 3 sets
        need_get_ids: set[str] = set()
        pending_delete_ids: set[str] = set()
        label_change_ids: set[str] = set()
        new_history_id = sync_cursor

        page_token: str | None = None
        while True:
            list_kwargs: dict[str, Any] = {
                "userId": "me",
                "startHistoryId": sync_cursor,
                "maxResults": 500,
            }
            if page_token:
                list_kwargs["pageToken"] = page_token

            try:
                response = (
                    self.service.users().history().list(**list_kwargs).execute()
                )
            except HttpError as exc:
                status, reason = http_error_detail(exc)
                raise EmailExternalAPIError(
                    f"Gmail history.list failed (HTTP {status}: {reason})."
                ) from exc
            except Exception as exc:
                raise EmailExternalAPIError(
                    f"Gmail unexpected history.list error ({type(exc).__name__}): {exc}"
                ) from exc

            new_history_id = str(response.get("historyId", new_history_id))

            for record in response.get("history", []):
                for added in record.get("messagesAdded", []):
                    msg_id = str(added.get("message", {}).get("id") or "").strip()
                    if msg_id:
                        need_get_ids.add(msg_id)

                for deleted in record.get("messagesDeleted", []):
                    msg_id = str(deleted.get("message", {}).get("id") or "").strip()
                    if msg_id:
                        pending_delete_ids.add(msg_id)

                for label_event in record.get("labelsAdded", []):
                    msg_id = str(label_event.get("message", {}).get("id") or "").strip()
                    if msg_id:
                        label_change_ids.add(msg_id)

                for label_event in record.get("labelsRemoved", []):
                    msg_id = str(label_event.get("message", {}).get("id") or "").strip()
                    if msg_id:
                        label_change_ids.add(msg_id)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        # Step 2 — Resolve pending deletes: batch probe in groups of 100
        probe_ids = list(pending_delete_ids - need_get_ids)
        confirmed_deletes: list[str] = []
        if probe_ids:
            raw = self._execute_batch_get(
                probe_ids, fmt="minimal", error_context="delete probe",
            )
            for msg_id in probe_ids:
                if msg_id in raw:
                    need_get_ids.add(msg_id)
                else:
                    confirmed_deletes.append(msg_id)

        # Step 3 — Filter label changes: exclude messages already in get/delete
        label_only_ids = label_change_ids - need_get_ids - set(confirmed_deletes)

        # Step 4 — Batch fetch full metadata for need_get
        upserts = self._batch_fetch_metadata(list(need_get_ids)) if need_get_ids else []

        # Step 5 — Batch fetch label updates for label-only changes
        label_updates = (
            self._batch_fetch_label_updates(list(label_only_ids))
            if label_only_ids
            else []
        )

        return SyncResult(
            upserts=upserts,
            new_cursor=new_history_id,
            deletes=confirmed_deletes,
            label_updates=label_updates,
        )

    def _batch_fetch_label_updates(self, message_ids: list[str]) -> list[LabelUpdate]:
        """Fetch current labelIds for messages and build LabelUpdate objects."""
        raw = self._execute_batch_get(
            message_ids,
            fmt="minimal",
            error_context="batch label fetch",
        )
        results: list[LabelUpdate] = []
        skipped_ids: list[str] = []
        for msg_id in message_ids:
            msg = raw.get(msg_id)
            if msg is None:
                skipped_ids.append(msg_id)
                continue
            is_read, box = self._resolve_labels(msg.get("labelIds") or [])
            results.append(LabelUpdate(
                provider_message_id=msg.get("id", msg_id),
                is_read=is_read,
                box=box,
            ))
        _log_skipped_messages("label sync", skipped_ids, message_ids)
        return results

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
            status, reason = http_error_detail(exc)
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
