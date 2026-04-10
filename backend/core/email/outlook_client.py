from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from .email_client import DraftMetadata, EmailClient, EmailContent, EmailMetadata, LabelUpdate, SpamMoveResult, SyncResult
from .errors import (
    EmailExternalAPIError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)
from .helpers import (
    parse_expiry,
    unwrap_app_credentials,
    unwrap_user_tokens,
    wrap_account_tokens,
)

OUTLOOK_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

logger = logging.getLogger(__name__)

_DELTA_SELECT_FIELDS = "id,conversationId,from,subject,receivedDateTime,isRead"
_DELTA_PAGE_SIZE = 100

_BOOTSTRAP_SELECT_FIELDS = (
    "id,conversationId,from,subject,receivedDateTime,isRead,parentFolderId"
)

_DELTA_FOLDERS = ("inbox", "sentitems", "drafts", "deleteditems", "junkemail", "archive")

_FOLDER_TO_BOX: dict[str, str] = {
    "deleteditems": "TRASH",
    "junkemail": "SPAM",
    "sentitems": "SENT",
}

_BOX_TO_FOLDER: dict[str, str] = {
    "ALL_MAIL": "inbox",
    "SENT": "sentitems",
    "SPAM": "junkemail",
}


class OutlookClient(EmailClient):
    """
    Concrete implementation of EmailClient for Outlook accounts.
    This class talks to Microsoft Graph API for mail operations
    and to the Microsoft identity platform for OAuth2 authentication.
    """

    def __init__(self, account_label: str = "outlook") -> None:
        self._account_label = account_label
        self._access_token: str | None = None
        self._sender_email: str | None = None
        self._sender_name: str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(
        self,
        app_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Interactive OAuth2 authentication using PKCE and a local callback server.
        Opens the browser for user consent and exchanges the authorization code
        for access and refresh tokens.
        """
        import base64
        import hashlib
        import secrets
        import threading
        import webbrowser
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        credentials_payload = unwrap_app_credentials(app_credentials)
        if not credentials_payload:
            raise EmailMissingAppCredentialsError()

        client_id = str(credentials_payload.get("client_id") or "").strip()
        client_secret = str(credentials_payload.get("client_secret") or "").strip()
        tenant = str(credentials_payload.get("tenant") or "common").strip()
        redirect_uri = str(credentials_payload.get("redirect_uri") or "").strip()
        scopes = self._resolve_scopes(credentials_payload)

        if not client_id or not client_secret or not redirect_uri or not scopes:
            raise EmailMissingAppCredentialsError("Missing required app credentials.")

        parsed_redirect = urllib.parse.urlparse(redirect_uri)
        redirect_host = (parsed_redirect.hostname or "").lower()
        if parsed_redirect.scheme != "http" or redirect_host not in {"localhost", "127.0.0.1"}:
            raise EmailProviderConfigError(
                "Outlook local OAuth redirect_uri must use http://localhost or http://127.0.0.1."
            )

        callback_path = parsed_redirect.path or "/"
        if not callback_path.startswith("/"):
            callback_path = f"/{callback_path}"

        token_url = self._token_url(tenant)

        # PKCE code verifier / challenge
        code_verifier = secrets.token_urlsafe(72)[:128]
        if len(code_verifier) < 43:
            code_verifier = f"{code_verifier}{'x' * (43 - len(code_verifier))}"
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("utf-8")).digest()
            )
            .rstrip(b"=")
            .decode("utf-8")
        )
        state = secrets.token_urlsafe(32)

        authorize_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
        auth_query = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        auth_url = f"{authorize_url}?{urllib.parse.urlencode(auth_query)}"

        # Local HTTP server to capture the OAuth callback.
        callback_result: dict[str, Any] = {}
        callback_event = threading.Event()

        class _OAuthHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != callback_path:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"Not found")
                    return

                params = urllib.parse.parse_qs(parsed.query)
                callback_result["code"] = params.get("code", [None])[0]
                callback_result["state"] = params.get("state", [None])[0]
                callback_result["error"] = params.get("error", [None])[0]
                callback_result["error_description"] = params.get("error_description", [None])[0]

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body><h3>OK, you can close this tab.</h3></body></html>")

                callback_event.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()

        bind_host = "127.0.0.1"
        port = parsed_redirect.port or 80
        try:
            server = ThreadingHTTPServer((bind_host, port), _OAuthHandler)
        except OSError as exc:
            raise EmailExternalAPIError(
                f"Outlook failed to start callback server on {bind_host}:{port}: {exc}"
            ) from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook unexpected callback server error ({type(exc).__name__}): {exc}"
            ) from exc

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            try:
                opened = False
                try:
                    opened = bool(webbrowser.open(auth_url))
                except Exception as exc:
                    logger.debug("Outlook failed to open browser for OAuth: %s", exc)
                    opened = False
                if not opened:
                    print(f"Open this URL in your browser to authenticate Outlook:\n{auth_url}")

                if not callback_event.wait(timeout=300):
                    raise EmailExternalAPIError("Outlook failed to complete OAuth flow: timeout waiting for callback.")
            except EmailExternalAPIError:
                raise
            except Exception as exc:
                raise EmailExternalAPIError(
                    f"Outlook unexpected OAuth callback error ({type(exc).__name__}): {exc}"
                ) from exc
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

        if callback_result.get("error"):
            error = str(callback_result.get("error") or "").strip()
            description = str(callback_result.get("error_description") or "").strip()
            raise EmailExternalAPIError(f"Outlook failed OAuth authorization: {error}. {description}".strip())

        if str(callback_result.get("state") or "") != state:
            raise EmailExternalAPIError("Outlook failed OAuth validation: invalid state received from callback.")

        auth_code = str(callback_result.get("code") or "").strip()
        if not auth_code:
            raise EmailExternalAPIError("Outlook failed OAuth flow: callback did not include authorization code.")

        # Exchange the authorization code for tokens.
        try:
            token_response = self._token_request(token_url, {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": auth_code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "scope": " ".join(scopes),
            })
        except EmailExternalAPIError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook unexpected token exchange error ({type(exc).__name__}): {exc}"
            ) from exc

        access_token = token_response.get("access_token")
        if not access_token:
            raise EmailExternalAPIError("Outlook failed to obtain access token: token response missing access_token.")

        self._access_token = access_token
        email_address, _display_name = self._fetch_sender_profile()

        token_record = {
            "access_token": access_token,
            "refresh_token": token_response.get("refresh_token"),
            "expiry": self._compute_expiry(token_response.get("expires_in")),
            "scopes": scopes,
            "email_address": email_address or None,
        }
        return wrap_account_tokens(token_record)

    def authenticate_silent(
        self,
        app_credentials: dict[str, Any] | None = None,
        user_tokens: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Non-interactive authentication: reuse a valid access token or refresh it.
        Returns updated wrapped tokens when a refresh occurs, None otherwise.
        Microsoft may rotate the refresh token on every refresh, so both the
        access and refresh tokens are persisted whenever a refresh happens.
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

        # Determine whether the current access token has expired.
        is_expired = False
        if expiry is not None:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            is_expired = expiry <= now_utc

        if not is_expired:
            self._access_token = access_token
            return None

        if not refresh_token:
            raise EmailMissingRefreshTokenError()

        client_id = str(credentials_payload.get("client_id") or "").strip()
        client_secret = str(credentials_payload.get("client_secret") or "").strip()
        tenant = str(credentials_payload.get("tenant") or "common").strip()
        scopes = self._resolve_scopes(credentials_payload, token_payload)

        if not client_id or not client_secret:
            raise EmailMissingAppCredentialsError("Missing required app credentials.")

        token_url = self._token_url(tenant)

        try:
            token_response = self._token_request(token_url, {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "scope": " ".join(scopes),
            })
        except EmailExternalAPIError as exc:
            raise EmailRefreshFailedError(f"Outlook failed to refresh access token: {exc}") from exc
        except Exception as exc:
            raise EmailRefreshFailedError(
                f"Outlook unexpected refresh token exchange error ({type(exc).__name__}): {exc}"
            ) from exc

        new_access_token = token_response.get("access_token")
        if not new_access_token:
            raise EmailRefreshFailedError("Outlook failed to refresh access token: response missing access_token.")

        # Microsoft may return a new refresh token (rotating tokens).
        new_refresh_token = token_response.get("refresh_token") or refresh_token

        self._access_token = new_access_token

        token_record = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expiry": self._compute_expiry(token_response.get("expires_in")),
            "scopes": scopes,
        }
        return wrap_account_tokens(token_record)

    # ------------------------------------------------------------------
    # Email operations
    # ------------------------------------------------------------------

    def fetch_email_metadata(
        self,
        sync_cursor: str | None = None,
        max_total: int = 500,
    ) -> SyncResult:
        """Fetch email metadata from Outlook using Microsoft Graph Delta Query."""
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook fetch_email_metadata requires authentication.")

        if sync_cursor is not None:
            try:
                return self._incremental_email_metadata(sync_cursor)
            except EmailExternalAPIError:
                pass  # Fallback to bootstrap (e.g. expired deltaLink)

        return self._bootstrap_email_metadata(max_total)

    # ------------------------------------------------------------------
    # Metadata sync — private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_folder_cursors(folder_cursors: dict[str, str]) -> str:
        """Serialize per-folder deltaLinks into a JSON cursor string."""
        return json.dumps({"v": 1, "folders": folder_cursors})

    @staticmethod
    def _decode_folder_cursors(sync_cursor: str) -> dict[str, str] | None:
        """Deserialize a JSON cursor string. Returns None if invalid or legacy format."""
        try:
            data = json.loads(sync_cursor)
            if isinstance(data, dict) and data.get("v") == 1 and isinstance(data.get("folders"), dict):
                return data["folders"]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _parse_graph_message(msg: dict[str, Any], box: str) -> EmailMetadata:
        """Parse a Microsoft Graph message resource into EmailMetadata."""
        from_obj = msg.get("from") or {}
        email_address = from_obj.get("emailAddress") or {}

        received_raw = msg.get("receivedDateTime", "")
        if received_raw:
            try:
                received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                received_at = datetime.now(timezone.utc)
        else:
            received_at = datetime.now(timezone.utc)

        return EmailMetadata(
            provider_message_id=msg.get("id", ""),
            thread_id=msg.get("conversationId") or "",
            from_email=email_address.get("address") or "",
            from_name=email_address.get("name") or "",
            subject=msg.get("subject") or "",
            received_at=received_at,
            is_read=msg.get("isRead", False),
            box=box,
        )

    def _fetch_folder_delta(
        self,
        folder_name: str,
        url: str,
        upserts: list[EmailMetadata],
        deletes: list[str],
        max_collect: int | None = None,
        label_updates: list[LabelUpdate] | None = None,
    ) -> str:
        """Paginate a single folder's delta query until deltaLink is obtained.

        Appends parsed messages to *upserts* and removed IDs to *deletes*.
        When *label_updates* is provided, partial delta messages (missing
        ``from``) are appended there instead of being parsed as full upserts.
        When *max_collect* is set, stops collecting messages after the limit
        but continues paginating to obtain the deltaLink.
        Returns the deltaLink.
        """
        box = _FOLDER_TO_BOX.get(folder_name, "ALL_MAIL")
        collected_enough = False

        while True:
            response = self._graph_request("GET", url)
            if not collected_enough:
                for msg in response.get("value", []):
                    if max_collect is not None and len(upserts) >= max_collect:
                        collected_enough = True
                        break
                    if msg.get("@removed"):
                        msg_id = msg.get("id", "")
                        if msg_id:
                            deletes.append(msg_id)
                            logger.debug(
                                "Outlook delta [%s] REMOVED id=%s",
                                folder_name, msg_id,
                            )
                    elif "from" not in msg and label_updates is not None:
                        label_updates.append(LabelUpdate(
                            provider_message_id=msg["id"],
                            is_read=msg.get("isRead", False),
                            box=box,
                        ))
                        logger.debug(
                            "Outlook delta [%s] LABEL id=%s is_read=%s",
                            folder_name, msg["id"], msg.get("isRead"),
                        )
                    else:
                        try:
                            upserts.append(self._parse_graph_message(msg, box))
                            logger.debug(
                                "Outlook delta [%s] UPSERT id=%s subject=%r box=%s",
                                folder_name, msg.get("id", "?"),
                                msg.get("subject", "?"), box,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Outlook delta (%s): skipping unparseable message %s: %s",
                                folder_name, msg.get("id", "?"), exc,
                            )

            next_link = response.get("@odata.nextLink")
            delta_link = response.get("@odata.deltaLink")

            if delta_link:
                return delta_link

            if not next_link:
                logger.warning("Outlook delta (%s): response has neither nextLink nor deltaLink", folder_name)
                return ""

            url = next_link

    def _resolve_special_folder_ids(self) -> dict[str, str]:
        """Fetch Graph IDs for sentitems, deleteditems and junkemail.

        Returns a mapping {folder_id: box} so that each message's
        parentFolderId can be classified into SENT, TRASH or SPAM.
        Any folder not in this mapping defaults to ALL_MAIL.
        """
        folder_id_to_box: dict[str, str] = {}
        for folder_name, box in _FOLDER_TO_BOX.items():
            try:
                url = f"{GRAPH_BASE_URL}/me/mailFolders/{folder_name}?$select=id"
                response = self._graph_request("GET", url)
                folder_id = response.get("id", "")
                if folder_id:
                    folder_id_to_box[folder_id] = box
            except EmailExternalAPIError:
                logger.warning(
                    "Outlook bootstrap: failed to resolve folder '%s', skipping.",
                    folder_name,
                )
        return folder_id_to_box

    def _fetch_recent_messages(
        self,
        max_total: int,
        folder_id_to_box: dict[str, str],
    ) -> list[EmailMetadata]:
        """Fetch the most recent messages across all folders via GET /me/messages.

        Uses $orderby=receivedDateTime desc so the API returns messages
        sorted by date (most recent first).  The parentFolderId of each
        message is compared against *folder_id_to_box* to assign the
        correct box value; anything not matched defaults to ALL_MAIL.
        """
        url = (
            f"{GRAPH_BASE_URL}/me/messages"
            f"?$select={_BOOTSTRAP_SELECT_FIELDS}"
            f"&$orderby=receivedDateTime+desc"
            f"&$top={min(max_total, 1000)}"
        )
        upserts: list[EmailMetadata] = []

        while url and len(upserts) < max_total:
            response = self._graph_request("GET", url)
            for msg in response.get("value", []):
                if len(upserts) >= max_total:
                    break
                parent_folder_id = msg.get("parentFolderId", "")
                box = folder_id_to_box.get(parent_folder_id, "ALL_MAIL")
                try:
                    upserts.append(self._parse_graph_message(msg, box))
                except Exception as exc:
                    logger.warning(
                        "Outlook bootstrap: skipping unparseable message %s: %s",
                        msg.get("id", "?"), exc,
                    )
            url = response.get("@odata.nextLink")

        return upserts

    def _bootstrap_email_metadata(self, max_total: int) -> SyncResult:
        """Path 1: Fetch most recent messages across all folders, then init delta cursors."""
        # Step 1: Discover special folder IDs for box classification.
        folder_id_to_box = self._resolve_special_folder_ids()

        # Step 2: Fetch the most recent messages across all folders.
        upserts = self._fetch_recent_messages(max_total, folder_id_to_box)

        # Step 3: Initialize per-folder delta cursors for future incremental syncs.
        folder_cursors: dict[str, str] = {}
        for folder in _DELTA_FOLDERS:
            url = (
                f"{GRAPH_BASE_URL}/me/mailFolders/{folder}/messages/delta"
                f"?$select={_DELTA_SELECT_FIELDS}&$top={_DELTA_PAGE_SIZE}"
            )
            try:
                delta_link = self._fetch_folder_delta(
                    folder, url, [], [],
                    max_collect=0,
                )
                if delta_link:
                    folder_cursors[folder] = delta_link
            except EmailExternalAPIError:
                logger.warning(
                    "Outlook bootstrap: delta init for '%s' failed, skipping.",
                    folder,
                )

        return SyncResult(
            upserts=upserts,
            new_cursor=self._encode_folder_cursors(folder_cursors),
            is_full_sync=True,
        )

    def _incremental_email_metadata(self, sync_cursor: str) -> SyncResult:
        """Path 2: Incremental sync via per-folder stored deltaLinks."""
        folder_cursors = self._decode_folder_cursors(sync_cursor)
        if folder_cursors is None:
            raise EmailExternalAPIError("Outlook: invalid or legacy sync cursor, falling back to bootstrap.")

        upserts: list[EmailMetadata] = []
        deletes: list[str] = []
        label_updates: list[LabelUpdate] = []
        new_cursors: dict[str, str] = {}
        all_failed = True

        for folder, delta_link in folder_cursors.items():
            try:
                new_delta = self._fetch_folder_delta(
                    folder, delta_link, upserts, deletes,
                    label_updates=label_updates,
                )
                new_cursors[folder] = new_delta if new_delta else delta_link
                all_failed = False
            except EmailExternalAPIError:
                logger.warning("Outlook incremental: folder '%s' failed, keeping previous cursor.", folder)
                new_cursors[folder] = delta_link

        if all_failed and folder_cursors:
            raise EmailExternalAPIError("Outlook: all folder delta queries failed.")

        return SyncResult(
            upserts=upserts,
            new_cursor=self._encode_folder_cursors(new_cursors),
            deletes=deletes,
            label_updates=label_updates,
        )

    def send_email(
        self,
        subject: str,
        body: str,
        recipients: list[str],
    ) -> EmailMetadata:
        """
        Send a plain text email using Microsoft Graph API (draft-then-send).
        Returns metadata of the sent message.
        """
        if self._access_token is None:
            raise EmailNotAuthenticatedError()

        if not recipients:
            raise EmailRecipientsMissingError()

        try:
            draft_payload = {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [
                    {"emailAddress": {"address": r}} for r in recipients
                ],
            }

            draft_response = self._graph_request(
                "POST", f"{GRAPH_BASE_URL}/me/messages", body=draft_payload,
            )
            metadata = self._parse_graph_message(draft_response, "SENT")

            draft_id = draft_response.get("id", "")
            try:
                self._graph_request("POST", f"{GRAPH_BASE_URL}/me/messages/{draft_id}/send")
            except EmailExternalAPIError:
                try:
                    self._graph_request("DELETE", f"{GRAPH_BASE_URL}/me/messages/{draft_id}")
                except Exception as exc:
                    logger.warning(
                        "Outlook failed to delete orphan draft %s after send failure: %s",
                        draft_id, exc,
                    )
                raise

            if not metadata.from_email or not metadata.from_name:
                profile_email, profile_name = self._fetch_sender_profile()
                if not metadata.from_email:
                    metadata.from_email = profile_email
                if not metadata.from_name:
                    metadata.from_name = profile_name or profile_email

            return metadata
        except EmailExternalAPIError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook unexpected send_email error ({type(exc).__name__}): {exc}"
            ) from exc

    def create_draft(
        self,
        to_recipients: list[str],
        cc_recipients: list[str],
        bcc_recipients: list[str],
        subject: str,
        body_html: str,
    ) -> DraftMetadata:
        """
        Create a draft in Outlook via POST /me/messages.

        CRITICAL: uses the 'Prefer: IdType="ImmutableId"' header so the
        message ID stays stable across state transitions (e.g. when the
        draft is later sent). Without this header, Outlook may return a
        mutable ID that changes on send, which would break any future
        lookups by provider_draft_id.
        """
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook create_draft requires authentication.")

        payload: dict[str, Any] = {
            "subject": subject or "",
            "body": {"contentType": "HTML", "content": body_html or ""},
            "toRecipients": [{"emailAddress": {"address": r}} for r in to_recipients],
            "ccRecipients": [{"emailAddress": {"address": r}} for r in cc_recipients],
            "bccRecipients": [{"emailAddress": {"address": r}} for r in bcc_recipients],
        }

        try:
            response = self._graph_request(
                "POST",
                f"{GRAPH_BASE_URL}/me/messages",
                body=payload,
                extra_headers={"Prefer": 'IdType="ImmutableId"'},
            )
        except EmailExternalAPIError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook unexpected create_draft error ({type(exc).__name__}): {exc}"
            ) from exc

        provider_draft_id = str(response.get("id", ""))

        def _parse_graph_datetime(value: Any) -> datetime:
            if isinstance(value, str) and value:
                try:
                    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
                    return datetime.fromisoformat(raw)
                except ValueError:
                    pass
            return datetime.now(timezone.utc)

        created_at = _parse_graph_datetime(response.get("createdDateTime"))
        updated_at = _parse_graph_datetime(response.get("lastModifiedDateTime"))

        return DraftMetadata(
            provider_draft_id=provider_draft_id,
            to_recipients=list(to_recipients),
            cc_recipients=list(cc_recipients),
            bcc_recipients=list(bcc_recipients),
            subject=subject,
            body_html=body_html,
            created_at=created_at,
            updated_at=updated_at,
        )

    def delete_messages(self, message_ids: list[str]) -> list[str]:
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook delete_messages requires authentication.")
        if not message_ids:
            return []
        # No-op: permanent deletion is not performed at the provider.
        # The service layer marks these as DELETED locally; the provider
        # retains the messages in Trash until its own retention policy
        # purges them.  See core_guide.md § Trash Management Operations.
        return list(message_ids)

    def restore_from_trash(self, items: dict[str, str | None]) -> dict[str, str]:
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook restore_from_trash requires authentication.")
        if not items:
            return {}
        results: dict[str, str] = {}
        for msg_id, dest_box in items.items():
            folder = _BOX_TO_FOLDER.get(dest_box, "inbox") if dest_box else "inbox"
            try:
                response = self._graph_request(
                    "POST",
                    f"{GRAPH_BASE_URL}/me/messages/{msg_id}/move",
                    body={"destinationId": folder},
                )
                results[msg_id] = response.get("id", msg_id)
            except EmailExternalAPIError:
                logger.warning("Outlook restore_from_trash: failed to restore message %s", msg_id)
        return results

    def move_to_trash(self, message_ids: list[str]) -> dict[str, str]:
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook move_to_trash requires authentication.")
        if not message_ids:
            return {}
        results: dict[str, str] = {}
        for msg_id in message_ids:
            try:
                response = self._graph_request(
                    "POST", f"{GRAPH_BASE_URL}/me/messages/{msg_id}/move",
                    body={"destinationId": "deleteditems"},
                )
                results[msg_id] = response.get("id", msg_id)
            except EmailExternalAPIError:
                logger.warning("Outlook move_to_trash: failed to trash message %s", msg_id)
        return results

    def fetch_messages_metadata(self, message_ids: list[str]) -> list[EmailMetadata]:
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook fetch_messages_metadata requires authentication.")
        if not message_ids:
            return []
        folder_id_to_box = self._resolve_special_folder_ids()
        results: list[EmailMetadata] = []
        for msg_id in message_ids:
            url = f"{GRAPH_BASE_URL}/me/messages/{msg_id}?$select={_BOOTSTRAP_SELECT_FIELDS}"
            try:
                msg = self._graph_request("GET", url)
                parent_folder_id = msg.get("parentFolderId", "")
                box = folder_id_to_box.get(parent_folder_id, "ALL_MAIL")
                results.append(self._parse_graph_message(msg, box))
            except EmailExternalAPIError:
                logger.warning("Outlook fetch_messages_metadata: failed to fetch %s", msg_id)
        return results

    def update_read_status(self, message_ids: list[str], is_read: bool) -> list[str]:
        """Mark messages as read/unread via Microsoft Graph API. Returns IDs successfully updated."""
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook update_read_status requires authentication.")
        if not message_ids:
            return []
        updated: list[str] = []
        for msg_id in message_ids:
            try:
                self._graph_request("PATCH", f"{GRAPH_BASE_URL}/me/messages/{msg_id}", body={"isRead": is_read})
                updated.append(msg_id)
            except EmailExternalAPIError:
                pass  # 404 or other → skip silently (message may not exist)
        return updated

    # ------------------------------------------------------------------
    # Spam operations
    # ------------------------------------------------------------------

    def move_to_spam(self, message_ids: list[str]) -> list[SpamMoveResult]:
        """Move messages to spam via Microsoft Graph API. Returns results for successfully moved messages."""
        return self._move_messages(message_ids, "junkemail", "move_to_spam")

    def restore_from_spam(self, message_ids: list[str]) -> list[SpamMoveResult]:
        """Restore messages from spam via Microsoft Graph API. Returns results for successfully restored messages."""
        return self._move_messages(message_ids, "inbox", "restore_from_spam")

    def _move_messages(
        self,
        message_ids: list[str],
        destination_id: str,
        operation: str,
    ) -> list[SpamMoveResult]:
        """Move messages to a folder via the Graph /move endpoint. Returns results for successfully moved messages."""
        if self._access_token is None:
            raise EmailNotAuthenticatedError(f"Outlook {operation} requires authentication.")
        if not message_ids:
            return []
        results: list[SpamMoveResult] = []
        for msg_id in message_ids:
            try:
                response = self._graph_request(
                    "POST",
                    f"{GRAPH_BASE_URL}/me/messages/{msg_id}/move",
                    body={"destinationId": destination_id},
                )
                new_id = response.get("id", msg_id)
                results.append(SpamMoveResult(old_id=msg_id, new_id=new_id))
            except EmailExternalAPIError:
                pass  # 404 or other → skip silently
        return results

    def verify_message_existence(self, message_ids: list[str]) -> list[str]:
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook verify_message_existence requires authentication.")
        if not message_ids:
            return []
        existing: list[str] = []
        for msg_id in message_ids:
            url = f"{GRAPH_BASE_URL}/me/messages/{msg_id}?$select=id"
            try:
                self._graph_request("GET", url)
                existing.append(msg_id)
            except EmailExternalAPIError:
                pass  # 404 or other error = not found
        return existing

    def fetch_email_content(self, provider_message_id: str) -> EmailContent:
        """Fetch the full body content for a single Outlook message."""
        if self._access_token is None:
            raise EmailNotAuthenticatedError("Outlook fetch_email_content requires authentication.")
        try:
            response = self._graph_request(
                "GET",
                f"{GRAPH_BASE_URL}/me/messages/{provider_message_id}?$select=body",
            )
            body = response.get("body", {})
            content_type = body.get("contentType", "").lower()
            content = body.get("content")
            if content_type == "html":
                return EmailContent(html_body=content, text_body=None)
            return EmailContent(html_body=None, text_body=content)
        except EmailExternalAPIError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook unexpected fetch_email_content error ({type(exc).__name__}): {exc}"
            ) from exc

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Outlook account inside the app.
        """
        return self._account_label

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_sender_profile(self) -> tuple[str, str]:
        """Best-effort fetch of the authenticated user's email and display name (cached).

        Tries three strategies in order:
        1. GET /me (requires User.Read scope)
        2. Decode JWT access token claims
        3. Read the ``from`` field of a recently sent message (Mail.ReadWrite)
        """
        if self._sender_email is not None:
            return self._sender_email, self._sender_name or ""

        email, name = "", ""

        # Try 1: Graph API /me endpoint (needs User.Read scope)
        try:
            response = self._graph_request(
                "GET", f"{GRAPH_BASE_URL}/me?$select=displayName,mail,userPrincipalName",
            )
            email = response.get("mail") or response.get("userPrincipalName") or ""
            name = response.get("displayName") or ""
        except Exception as exc:
            logger.debug("Outlook /me profile fetch failed: %s", exc)

        # Try 2: decode JWT access token claims
        if not email:
            email, name = self._parse_token_claims()

        # Try 3: read from a recently sent message (needs Mail.ReadWrite)
        if not email:
            try:
                response = self._graph_request(
                    "GET",
                    f"{GRAPH_BASE_URL}/me/mailFolders/sentitems/messages?$top=1&$select=from",
                )
                messages = response.get("value", [])
                if messages:
                    from_obj = messages[0].get("from") or {}
                    email_addr = from_obj.get("emailAddress") or {}
                    email = email_addr.get("address") or ""
                    name = email_addr.get("name") or ""
            except Exception as exc:
                logger.debug("Outlook sent message profile fetch failed: %s", exc)

        self._sender_email = email
        self._sender_name = name
        return self._sender_email, self._sender_name

    def _parse_token_claims(self) -> tuple[str, str]:
        """Extract (email, display_name) from the JWT access token claims."""
        if not self._access_token:
            return "", ""
        try:
            parts = self._access_token.split(".")
            if len(parts) != 3:
                return "", ""
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            claims = json.loads(base64.urlsafe_b64decode(payload))
            email = (
                claims.get("preferred_username")
                or claims.get("email")
                or claims.get("unique_name")
                or claims.get("upn")
                or ""
            )
            name = claims.get("name") or ""
            return email, name
        except Exception as exc:
            logger.debug("Outlook failed to parse JWT claims: %s", exc)
            return "", ""

    def _resolve_scopes(
        self,
        credentials_payload: dict[str, Any],
        token_payload: dict[str, Any] | None = None,
    ) -> list[str]:
        """Resolve scopes from credentials or token payload, with a default fallback."""
        scopes_raw = credentials_payload.get("scopes")
        if scopes_raw is None and token_payload is not None:
            scopes_raw = token_payload.get("scopes")
        if isinstance(scopes_raw, str):
            return [s for s in scopes_raw.replace(",", " ").split() if s]
        if isinstance(scopes_raw, (list, tuple, set)):
            return [str(s).strip() for s in scopes_raw if str(s).strip()]
        return list(OUTLOOK_SCOPES)

    @staticmethod
    def _token_url(tenant: str) -> str:
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    @staticmethod
    def _compute_expiry(expires_in_raw: Any) -> str | None:
        if expires_in_raw is None:
            return None
        try:
            expires_in = int(expires_in_raw)
            if expires_in < 0:
                expires_in = 0
            return (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        except (TypeError, ValueError):
            return None

    def _token_request(self, token_url: str, payload: dict[str, str]) -> dict[str, Any]:
        """POST to the Microsoft identity token endpoint and return the parsed response."""
        data = urllib.parse.urlencode(payload).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        req = urllib.request.Request(token_url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            detail = error_body
            try:
                error_json = json.loads(error_body) if error_body else {}
                if isinstance(error_json, dict):
                    err = error_json.get("error")
                    desc = error_json.get("error_description")
                    if err or desc:
                        detail = f"{err or 'error'}: {desc or 'unknown error'}"
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            raise EmailExternalAPIError(f"Outlook failed to call token endpoint: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EmailExternalAPIError(f"Outlook failed to reach token endpoint: {exc.reason}") from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook failed during token request ({type(exc).__name__}): {exc}"
            ) from exc

        try:
            token_response = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise EmailExternalAPIError("Outlook failed to parse token endpoint response: invalid JSON.") from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook failed during token response parsing ({type(exc).__name__}): {exc}"
            ) from exc

        if not isinstance(token_response, dict):
            raise EmailExternalAPIError("Outlook failed at token endpoint: invalid response payload.")

        if token_response.get("error"):
            err = str(token_response.get("error") or "error")
            desc = str(token_response.get("error_description") or "unknown error")
            raise EmailExternalAPIError(f"Outlook failed at token endpoint: {err}: {desc}")

        return token_response

    def _graph_request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to Microsoft Graph API."""
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._access_token}",
        }
        data: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 204:
                    return {}
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            detail = error_body
            try:
                error_json = json.loads(error_body) if error_body else {}
                if isinstance(error_json, dict):
                    err_code = error_json.get("error", {})
                    if isinstance(err_code, dict):
                        detail = f"{err_code.get('code', 'error')}: {err_code.get('message', '')}"
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            raise EmailExternalAPIError(f"Outlook failed Graph API call: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EmailExternalAPIError(f"Outlook failed to reach Graph API: {exc.reason}") from exc
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Outlook failed Graph API request ({type(exc).__name__}): {exc}"
            ) from exc

