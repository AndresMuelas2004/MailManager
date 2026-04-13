from __future__ import annotations

from typing import Any
from .email_client import DraftMetadata, EmailClient, EmailContent, EmailMetadata, SpamMoveResult, SyncResult
from .errors import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailDuplicateAccountLabelError,
    EmailExternalAPIError,
    EmailProviderConfigError,
)
from .gmail_client import GmailClient
from .outlook_client import OutlookClient


class EmailManager:
    """
    Coordinator for multiple EmailClient instances.
    This class is responsible for orchestrating multi-account flows.
    """

    def __init__(self) -> None:
        """
        Initialize the manager with empty client and error registries.
        """
        self._clients: list[EmailClient] = []
        self._last_errors: dict[str, Exception] = {}

    def add_account_record(self, record: dict[str, Any]) -> None:
        """
        Build and register an EmailClient based on a persisted account record.
        """
        mailbox_id = str(record.get("mailbox_id") or "")
        account_id = str(record.get("account_id") or "")
        provider = str(record.get("provider") or "").lower()
        if not mailbox_id:
            raise EmailAccountRecordError("Account record is missing mailbox_id.")
        if not account_id:
            raise EmailAccountRecordError("Account record is missing account_id.")
        if not provider:
            raise EmailAccountRecordError("Account record is missing provider.")

        account_label = f"{mailbox_id}__{account_id}"
        client = self._build_client(provider, account_label)
        self.add_client(client)

    def _build_client(self, provider: str, account_label: str) -> EmailClient:
        if provider == "gmail":
            return GmailClient(account_label=account_label)
        if provider == "outlook":
            return OutlookClient(account_label=account_label)
        raise EmailProviderConfigError(f"Unknown provider '{provider}'.")

    def add_client(self, client: EmailClient) -> None:
        """
        Register a new EmailClient with a unique account label.
        """
        new_label = client.get_account_label()
        for existing in self._clients:
            if existing.get_account_label() == new_label:
                raise EmailDuplicateAccountLabelError(f"Account label '{new_label}' already exists.")
        self._clients.append(client)

    def _get_client_or_raise(self, account_label: str) -> EmailClient:
        """
        Return the client matching *account_label* or raise EmailAccountNotFoundError.
        """
        for client in self._clients:
            if client.get_account_label() == account_label:
                return client
        raise EmailAccountNotFoundError(
            f"Account '{account_label}' not found.",
            {"account_label": account_label},
        )

    def authenticate_all_silent(
        self,
        auth_payloads: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Authenticate all registered clients without interactive flows.
        """
        self._last_errors = {}
        refreshed_tokens: dict[str, dict[str, Any]] = {}
        for client in self._clients:
            try:
                if auth_payloads is None:
                    updated = client.authenticate_silent()
                else:
                    app_credentials = None
                    user_tokens = None
                    payload = auth_payloads.get(client.get_account_label())
                    if payload is not None:
                        app_credentials, user_tokens = payload
                    updated = client.authenticate_silent(app_credentials, user_tokens)
                if isinstance(updated, dict) and updated:
                    refreshed_tokens[client.get_account_label()] = updated
            except Exception as exc:
                self._last_errors[client.get_account_label()] = exc
        return refreshed_tokens

    def connect_account(
        self,
        account_label: str,
        app_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Authenticate a single account by its label.
        This method is for UI flows, not for scripts or batch jobs.
        """
        self._last_errors = {}
        client = self._get_client_or_raise(account_label)
        try:
            return client.authenticate(app_credentials)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected connect_account error ({type(exc).__name__}): {exc}"
            ) from exc

    def fetch_all_email_metadata(
        self,
        sync_cursors: dict[str, str | None] | None = None,
    ) -> dict[str, SyncResult]:
        """
        Fetch email metadata from all clients.
        Returns {account_label: SyncResult}.
        """
        self._last_errors = {}
        results: dict[str, SyncResult] = {}
        for client in self._clients:
            label = client.get_account_label()
            cursor = (sync_cursors or {}).get(label)
            try:
                results[label] = client.fetch_email_metadata(sync_cursor=cursor)
            except Exception as exc:
                self._last_errors[label] = exc
        return results

    def verify_message_existence(
        self,
        account_label: str,
        message_ids: list[str],
    ) -> list[str]:
        client = self._get_client_or_raise(account_label)
        try:
            return client.verify_message_existence(message_ids)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected verify_message_existence error ({type(exc).__name__}): {exc}"
            ) from exc

    def delete_messages(self, account_label: str, message_ids: list[str]) -> list[str]:
        client = self._get_client_or_raise(account_label)
        try:
            return client.delete_messages(message_ids)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected delete_messages error ({type(exc).__name__}): {exc}"
            ) from exc

    def restore_from_trash(self, account_label: str, items: dict[str, str | None]) -> dict[str, str]:
        client = self._get_client_or_raise(account_label)
        try:
            return client.restore_from_trash(items)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected restore_from_trash error ({type(exc).__name__}): {exc}"
            ) from exc

    def fetch_messages_metadata(
        self, account_label: str, message_ids: list[str],
    ) -> list[EmailMetadata]:
        client = self._get_client_or_raise(account_label)
        try:
            return client.fetch_messages_metadata(message_ids)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected fetch_messages_metadata error ({type(exc).__name__}): {exc}"
            ) from exc

    def move_to_trash(self, account_label: str, message_ids: list[str]) -> dict[str, str]:
        client = self._get_client_or_raise(account_label)
        try:
            return client.move_to_trash(message_ids)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected move_to_trash error ({type(exc).__name__}): {exc}"
            ) from exc

    def send_email_from_account(
        self,
        account_label: str,
        subject: str,
        body: str,
        recipients: list[str],
    ) -> EmailMetadata:
        """
        Send an email using the client that matches the requested account label.
        Returns metadata of the sent email.
        """
        client = self._get_client_or_raise(account_label)
        try:
            return client.send_email(subject, body, recipients)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected send_email error ({type(exc).__name__}): {exc}"
            ) from exc

    def create_draft(
        self,
        account_label: str,
        to_recipients: list[str],
        cc_recipients: list[str],
        bcc_recipients: list[str],
        subject: str,
        body_html: str,
    ) -> DraftMetadata:
        """
        Create a draft using the client that matches the requested account label.
        """
        client = self._get_client_or_raise(account_label)
        try:
            return client.create_draft(
                to_recipients, cc_recipients, bcc_recipients, subject, body_html,
            )
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected create_draft error ({type(exc).__name__}): {exc}"
            ) from exc

    def update_draft(
        self,
        account_label: str,
        provider_draft_id: str,
        to_recipients: list[str],
        cc_recipients: list[str],
        bcc_recipients: list[str],
        subject: str,
        body_html: str,
    ) -> DraftMetadata:
        """
        Update an existing draft using the client that matches the
        requested account label. Full-field replacement semantics — the
        caller passes every field; the provider overwrites the draft
        with exactly those values.
        """
        client = self._get_client_or_raise(account_label)
        try:
            return client.update_draft(
                provider_draft_id,
                to_recipients, cc_recipients, bcc_recipients,
                subject, body_html,
            )
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected update_draft error ({type(exc).__name__}): {exc}"
            ) from exc

    def delete_draft(self, account_label: str, provider_draft_id: str) -> None:
        """
        Delete a draft using the client that matches the requested account label.
        """
        client = self._get_client_or_raise(account_label)
        try:
            client.delete_draft(provider_draft_id)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected delete_draft error ({type(exc).__name__}): {exc}"
            ) from exc

    def fetch_all_drafts(self) -> dict[str, list[DraftMetadata]]:
        """
        Fetch drafts from every registered client. Returns
        ``{account_label: list[DraftMetadata]}``. Per-account failures
        are captured in ``self._last_errors`` (mirroring the error
        aggregation behavior of ``fetch_all_email_metadata``).
        """
        self._last_errors = {}
        results: dict[str, list[DraftMetadata]] = {}
        for client in self._clients:
            label = client.get_account_label()
            try:
                results[label] = client.fetch_drafts()
            except Exception as exc:
                self._last_errors[label] = exc
        return results

    def update_read_status(
        self,
        account_label: str,
        message_ids: list[str],
        is_read: bool,
    ) -> list[str]:
        """Mark messages as read/unread for the given account. Returns successfully updated IDs."""
        client = self._get_client_or_raise(account_label)
        try:
            return client.update_read_status(message_ids, is_read)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected update_read_status error ({type(exc).__name__}): {exc}"
            ) from exc

    def move_to_spam(
        self,
        account_label: str,
        message_ids: list[str],
    ) -> list[SpamMoveResult]:
        """Move messages to spam for the given account. Returns results for successfully moved messages."""
        client = self._get_client_or_raise(account_label)
        try:
            return client.move_to_spam(message_ids)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected move_to_spam error ({type(exc).__name__}): {exc}"
            ) from exc

    def restore_from_spam(
        self,
        account_label: str,
        message_ids: list[str],
    ) -> list[SpamMoveResult]:
        """Restore messages from spam for the given account. Returns results for successfully restored messages."""
        client = self._get_client_or_raise(account_label)
        try:
            return client.restore_from_spam(message_ids)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected restore_from_spam error ({type(exc).__name__}): {exc}"
            ) from exc

    def fetch_email_content(self, account_label: str, provider_message_id: str) -> EmailContent:
        """Fetch the full body content for a single email by account label."""
        client = self._get_client_or_raise(account_label)
        try:
            return client.fetch_email_content(provider_message_id)
        except CoreError:
            raise
        except Exception as exc:
            raise EmailExternalAPIError(
                f"Unexpected fetch_email_content error ({type(exc).__name__}): {exc}"
            ) from exc

    def get_last_errors(self) -> dict[str, Exception]:
        """
        Return a snapshot of the most recent errors per account label.
        """
        return dict(self._last_errors)
