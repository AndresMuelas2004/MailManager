from __future__ import annotations

import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

logger = logging.getLogger(__name__)

import google_auth_httplib2
import httplib2
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
_BATCH_MAX_RETRIES = 4
_BATCH_RETRY_DELAY = 1.0  # seconds
_INCREMENTAL_EVENT_THRESHOLD = 100


def _parse_max_workers() -> int:
    raw = os.environ.get("GMAIL_BATCH_MAX_WORKERS", "5")
    try:
        return max(int(raw), 1)
    except (ValueError, TypeError):
        logger.warning("Invalid GMAIL_BATCH_MAX_WORKERS=%r, defaulting to 5", raw)
        return 5

_PARALLEL_MAX_WORKERS = _parse_max_workers()

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exception: Any) -> bool:
    """Classify whether a batch callback exception is worth retrying.

    Returns True for rate-limit (429), server errors (5xx), and non-HTTP
    exceptions (network timeouts, connection resets).  Returns False for
    client errors like 404, 400, 403, 410 — those are permanent failures.
    """
    if isinstance(exception, HttpError):
        status = getattr(getattr(exception, "resp", None), "status", None)
        return status in _RETRYABLE_STATUS_CODES
    return True


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
        self._credentials: Credentials | None = None
        self._sender_email: str | None = None

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

        self._credentials = creds
        self.service = build("gmail", "v1", credentials=creds)

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
        self._credentials = creds
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
        return SyncResult(upserts=metadata_list, new_cursor=history_id, is_full_sync=True)

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

    def _execute_single_chunk(
        self,
        chunk_ids: list[str],
        chunk_index: int,
        *,
        fmt: str,
        extra_kwargs: dict[str, Any] | None = None,
        credentials: Credentials,
    ) -> tuple[dict[str, dict[str, Any]], list[str], list[str], float]:
        """Execute a single batch.execute() for one chunk of IDs.

        Each call builds its own thread-local HTTP transport and service
        because httplib2 is not thread-safe. Never raises — chunk-level
        errors mark all IDs as failed.

        Returns (successes, retryable_failed_ids, permanent_failed_ids, elapsed_seconds).
        """
        t0 = time.perf_counter()
        successes: dict[str, dict[str, Any]] = {}
        failed: list[str] = []
        permanent_failed: list[str] = []

        def _callback(
            request_id: str, response: Any, exception: Any,
            _s: dict[str, dict[str, Any]] = successes,
            _f: list[str] = failed,
            _pf: list[str] = permanent_failed,
        ) -> None:
            if exception is not None:
                if _is_retryable(exception):
                    _f.append(request_id)
                else:
                    _pf.append(request_id)
                return
            _s[request_id] = response

        try:
            thread_http = google_auth_httplib2.AuthorizedHttp(
                credentials, http=httplib2.Http(),
            )
            thread_service = build("gmail", "v1", http=thread_http)

            batch = thread_service.new_batch_http_request(callback=_callback)
            for msg_id in chunk_ids:
                get_kwargs: dict[str, Any] = {
                    "userId": "me", "id": msg_id, "format": fmt,
                    **(extra_kwargs or {}),
                }
                batch.add(
                    thread_service.users().messages().get(**get_kwargs),
                    request_id=msg_id,
                )
            batch.execute()
        except HttpError as exc:
            status, reason = http_error_detail(exc)
            if _is_retryable(exc):
                logger.warning(
                    "Chunk %d: batch.execute() HttpError (HTTP %s: %s) — all %d IDs marked retryable",
                    chunk_index, status, reason, len(chunk_ids),
                )
                return {}, list(chunk_ids), [], time.perf_counter() - t0
            logger.warning(
                "Chunk %d: batch.execute() HttpError (HTTP %s: %s) — all %d IDs marked permanently failed",
                chunk_index, status, reason, len(chunk_ids),
            )
            return {}, [], list(chunk_ids), time.perf_counter() - t0
        except Exception as exc:
            logger.warning(
                "Chunk %d: batch.execute() %s: %s — all %d IDs marked retryable",
                chunk_index, type(exc).__name__, exc, len(chunk_ids),
            )
            return {}, list(chunk_ids), [], time.perf_counter() - t0

        return successes, failed, permanent_failed, time.perf_counter() - t0

    def _execute_batch_get_sequential(
        self,
        message_ids: list[str],
        *,
        fmt: str,
        error_context: str,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Fallback: sequential batch execution using self.service directly."""
        all_results: dict[str, dict[str, Any]] = {}

        for chunk_start in range(0, len(message_ids), _BATCH_SIZE):
            chunk = message_ids[chunk_start:chunk_start + _BATCH_SIZE]
            chunk_results: dict[str, dict[str, Any]] = {}
            pending_ids = list(chunk)
            resolved_extra = extra_kwargs or {}

            for attempt in range(_BATCH_MAX_RETRIES + 1):
                failed_in_attempt: list[str] = []

                def _callback(
                    request_id: str, response: Any, exception: Any,
                    _r: dict[str, dict[str, Any]] = chunk_results,
                    _f: list[str] = failed_in_attempt,
                ) -> None:
                    if exception is not None:
                        if _is_retryable(exception):
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
                    break

                if attempt < _BATCH_MAX_RETRIES:
                    logger.warning(
                        "Gmail batch: %d/%d messages failed (attempt %d/%d), retrying",
                        len(failed_in_attempt), len(pending_ids),
                        attempt + 1, _BATCH_MAX_RETRIES + 1,
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

    def _execute_batch_get(
        self,
        message_ids: list[str],
        *,
        fmt: str,
        error_context: str,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Execute a batched messages.get call; returns {msg_id: response}.

        When credentials are available, chunks run in parallel via
        ThreadPoolExecutor. Falls back to sequential execution otherwise.
        """
        if not message_ids:
            return {}

        if self._credentials is None:
            return self._execute_batch_get_sequential(
                message_ids, fmt=fmt, error_context=error_context,
                extra_kwargs=extra_kwargs,
            )

        all_results: dict[str, dict[str, Any]] = {}
        chunks: list[list[str]] = [
            message_ids[i:i + _BATCH_SIZE]
            for i in range(0, len(message_ids), _BATCH_SIZE)
        ]
        num_chunks = len(chunks)
        workers = min(_PARALLEL_MAX_WORKERS, num_chunks)

        pending_per_chunk: dict[int, list[str]] = {
            i: list(chunk) for i, chunk in enumerate(chunks)
        }
        creds = self._credentials

        logger.info(
            "Gmail parallel batch: %d chunk(s), %d worker(s), %d total IDs",
            num_chunks, workers, len(message_ids),
        )

        for attempt in range(_BATCH_MAX_RETRIES + 1):
            active_chunks = {
                i: ids for i, ids in pending_per_chunk.items() if ids
            }
            if not active_chunks:
                break

            if attempt > 0:
                logger.warning(
                    "Gmail parallel batch: retry %d/%d — %d IDs pending across %d chunk(s)",
                    attempt, _BATCH_MAX_RETRIES,
                    sum(len(ids) for ids in active_chunks.values()),
                    len(active_chunks),
                )
                time.sleep(_BATCH_RETRY_DELAY)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        self._execute_single_chunk,
                        ids, chunk_idx,
                        fmt=fmt,
                        extra_kwargs=extra_kwargs, credentials=creds,
                    ): chunk_idx
                    for chunk_idx, ids in active_chunks.items()
                }
                for future in as_completed(futures):
                    chunk_idx = futures[future]
                    successes, failed, permanent_failed, _elapsed = future.result()
                    all_results.update(successes)
                    pending_per_chunk[chunk_idx] = failed
                    if permanent_failed:
                        logger.warning(
                            "Gmail parallel batch: %d permanent failures in chunk %d: %s",
                            len(permanent_failed), chunk_idx, permanent_failed[:10],
                        )

            total_pending = sum(len(ids) for ids in pending_per_chunk.values())
            if total_pending == 0:
                break

            if attempt == _BATCH_MAX_RETRIES:
                lost_ids = [
                    msg_id
                    for ids in pending_per_chunk.values()
                    for msg_id in ids
                ]
                logger.warning(
                    "Gmail parallel batch: %d messages lost after %d attempts: %s",
                    len(lost_ids), _BATCH_MAX_RETRIES + 1, lost_ids[:10],
                )

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
        if "TRASH" in labels:
            box = "TRASH"
        elif "SPAM" in labels:
            box = "SPAM"
        elif "SENT" in labels:
            box = "SENT"
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

    def _fetch_sender_email(self) -> str:
        """Best-effort fetch of the authenticated user's email address (cached)."""
        if self._sender_email is not None:
            return self._sender_email
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            self._sender_email = profile.get("emailAddress", "")
        except Exception:
            self._sender_email = ""
        return self._sender_email

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

        # Threshold check — abort if too many events (Step 1 is cheap, Steps 2-5 are not)
        total_event_ids = len(need_get_ids | pending_delete_ids | label_change_ids)
        if total_event_ids > _INCREMENTAL_EVENT_THRESHOLD:
            logger.info(
                "Gmail incremental: %d event IDs exceed threshold %d, falling back to bootstrap.",
                total_event_ids, _INCREMENTAL_EVENT_THRESHOLD,
            )
            raise EmailExternalAPIError(
                f"Gmail incremental sync has {total_event_ids} events, exceeding threshold."
            )

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
    ) -> EmailMetadata:
        """
        Send a plain text email using the Gmail API.
        Returns metadata of the sent message.
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
            response = self.service.users().messages().send(userId="me", body=payload).execute()
        except HttpError as exc:
            status, reason = http_error_detail(exc)
            raise EmailExternalAPIError(
                f"Gmail failed to send email (HTTP {status}: {reason})."
            ) from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Gmail unexpected send email error ({type(exc).__name__}): {exc}"
            ) from exc

        message_id = response.get("id", "")
        if message_id:
            try:
                fetched = self._batch_fetch_metadata([message_id])
                if fetched:
                    result = fetched[0]
                    if not result.subject:
                        result.subject = subject
                    if not result.from_email:
                        result.from_email = self._fetch_sender_email()
                    if not result.from_name:
                        result.from_name = result.from_email
                    return result
            except Exception as exc:
                logger.warning(
                    "Gmail failed to fetch metadata for sent message %s (%s): %s",
                    message_id, type(exc).__name__, exc,
                )

        # Fallback: build minimal metadata from the send response
        sender_email = self._fetch_sender_email()
        return EmailMetadata(
            provider_message_id=message_id,
            thread_id=response.get("threadId") or "",
            from_email=sender_email,
            from_name=sender_email,
            subject=subject,
            received_at=datetime.now(timezone.utc),
            is_read=True,
            box="SENT",
        )

    def verify_message_existence(self, message_ids: list[str]) -> list[str]:
        if self.service is None:
            raise EmailNotAuthenticatedError("Gmail verify_message_existence requires authentication.")
        if not message_ids:
            return []
        raw = self._execute_batch_get(
            message_ids, fmt="minimal", error_context="message existence verification",
        )
        return [msg_id for msg_id in message_ids if msg_id in raw]

    # ------------------------------------------------------------------
    # Read status
    # ------------------------------------------------------------------

    def update_read_status(self, message_ids: list[str], is_read: bool) -> list[str]:
        """Mark messages as read/unread via Gmail label modification. Returns IDs successfully updated."""
        if self.service is None:
            raise EmailNotAuthenticatedError("Gmail update_read_status requires authentication.")
        if not message_ids:
            return []
        if is_read:
            return self._batch_modify_labels(message_ids, remove_labels=["UNREAD"])
        else:
            return self._batch_modify_labels(message_ids, add_labels=["UNREAD"])

    def _batch_modify_labels(
        self,
        message_ids: list[str],
        *,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> list[str]:
        """Batch-modify labels on messages. Returns list of successfully modified IDs."""
        body: dict[str, Any] = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        all_updated: list[str] = []

        for chunk_start in range(0, len(message_ids), _BATCH_SIZE):
            chunk = message_ids[chunk_start:chunk_start + _BATCH_SIZE]
            pending_ids = list(chunk)

            for attempt in range(_BATCH_MAX_RETRIES + 1):
                chunk_updated: list[str] = []
                failed_in_attempt: list[str] = []

                def _callback(
                    request_id: str, response: Any, exception: Any,
                    _u: list[str] = chunk_updated,
                    _f: list[str] = failed_in_attempt,
                ) -> None:
                    if exception is not None:
                        if _is_retryable(exception):
                            _f.append(request_id)
                        # Non-retryable (404, 400, etc.) → silently skip
                        return
                    _u.append(request_id)

                try:
                    batch = self.service.new_batch_http_request(callback=_callback)
                    for msg_id in pending_ids:
                        batch.add(
                            self.service.users().messages().modify(
                                userId="me", id=msg_id, body=body,
                            ),
                            request_id=msg_id,
                        )
                    batch.execute()
                except EmailExternalAPIError:
                    raise
                except HttpError as exc:
                    status, reason = http_error_detail(exc)
                    raise EmailExternalAPIError(
                        f"Gmail batch label modify failed (HTTP {status}: {reason})."
                    ) from exc
                except Exception as exc:
                    raise EmailExternalAPIError(
                        f"Gmail unexpected batch label modify error ({type(exc).__name__}): {exc}"
                    ) from exc

                all_updated.extend(chunk_updated)

                if not failed_in_attempt:
                    break

                if attempt < _BATCH_MAX_RETRIES:
                    logger.warning(
                        "Gmail batch modify: %d/%d messages failed (attempt %d/%d), retrying",
                        len(failed_in_attempt), len(pending_ids),
                        attempt + 1, _BATCH_MAX_RETRIES + 1,
                    )
                    time.sleep(_BATCH_RETRY_DELAY)
                    pending_ids = failed_in_attempt
                else:
                    logger.warning(
                        "Gmail batch modify: %d messages lost after %d attempts: %s",
                        len(failed_in_attempt), _BATCH_MAX_RETRIES + 1,
                        failed_in_attempt[:10],
                    )

        return all_updated

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Gmail account inside the app.
        """
        return self._account_label
