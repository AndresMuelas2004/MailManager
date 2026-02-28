from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from .email_client import EmailClient, EmailMessage
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
    "offline_access",
]

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class OutlookClient(EmailClient):
    """
    Concrete implementation of EmailClient for Outlook accounts.
    This class talks to Microsoft Graph API for mail operations
    and to the Microsoft identity platform for OAuth2 authentication.
    """

    def __init__(self, account_label: str = "outlook") -> None:
        self._account_label = account_label
        self._access_token: str | None = None

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
                except Exception:
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

        token_record = {
            "access_token": access_token,
            "refresh_token": token_response.get("refresh_token"),
            "expiry": self._compute_expiry(token_response.get("expires_in")),
            "scopes": scopes,
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

    def fetch_unread_emails(self, max_total: int = 200, page_size: int = 50) -> list[EmailMessage]:
        """
        Fetch unread messages from Microsoft Graph, normalize them into
        EmailMessage objects and return them as a list.
        """
        if self._access_token is None:
            raise EmailNotAuthenticatedError()

        select_fields = "id,conversationId,subject,from,toRecipients,bodyPreview,receivedDateTime,isRead"
        query = urllib.parse.urlencode(
            {
                "$filter": "isRead eq false",
                "$select": select_fields,
                "$top": page_size,
                "$orderby": "receivedDateTime desc",
            },
            quote_via=urllib.parse.quote,
            safe="$,",
        )
        url: str | None = f"{GRAPH_BASE_URL}/me/messages?{query}"

        raw_messages: list[dict[str, Any]] = []
        while url and len(raw_messages) < max_total:
            response = self._graph_request("GET", url)
            raw_messages.extend(response.get("value", []))
            url = response.get("@odata.nextLink")

        raw_messages = raw_messages[:max_total]

        unread_emails: list[EmailMessage] = []
        for msg in raw_messages:
            from_data = (msg.get("from") or {}).get("emailAddress") or {}
            sender_name = from_data.get("name") or ""
            sender_addr = from_data.get("address") or ""
            sender = f"{sender_name} <{sender_addr}>".strip() if sender_addr else sender_name

            to_recipients = msg.get("toRecipients") or []
            recipients = [
                (r.get("emailAddress") or {}).get("address", "")
                for r in to_recipients
            ]
            recipients = [r for r in recipients if r]

            received_str = msg.get("receivedDateTime") or ""
            if received_str:
                try:
                    sent_at = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
                except ValueError:
                    sent_at = datetime.now(timezone.utc)
            else:
                sent_at = datetime.now(timezone.utc)

            message_id = msg.get("id", "")
            raw_mime_url = f"{GRAPH_BASE_URL}/me/messages/{message_id}/$value"
            raw_bytes = self._graph_raw_request(raw_mime_url)
            raw_rfc822_b64url = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

            unread_emails.append(
                EmailMessage(
                    message_id=message_id,
                    thread_id=msg.get("conversationId"),
                    subject=msg.get("subject", ""),
                    sender=sender,
                    recipients=recipients,
                    body=msg.get("bodyPreview", ""),
                    sent_at=sent_at,
                    is_unread=True,
                    provider="outlook",
                    raw_rfc822_b64url=raw_rfc822_b64url,
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
        Send a plain text email using Microsoft Graph API.
        """
        if self._access_token is None:
            raise EmailNotAuthenticatedError()

        if not recipients:
            raise EmailRecipientsMissingError()

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [
                    {"emailAddress": {"address": r}} for r in recipients
                ],
            }
        }

        self._graph_request("POST", f"{GRAPH_BASE_URL}/me/sendMail", body=payload)

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Outlook account inside the app.
        """
        return self._account_label

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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
    ) -> dict[str, Any]:
        """Make an authenticated request to Microsoft Graph API."""
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._access_token}",
        }
        data: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
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

    def _graph_raw_request(self, url: str) -> bytes:
        """Make an authenticated GET request and return the raw response bytes."""
        headers = {"Authorization": f"Bearer {self._access_token}"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
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
