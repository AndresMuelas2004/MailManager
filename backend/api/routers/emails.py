"""
Email router for inbox fetching and sending.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.errors.exceptions import (
    AccountNotConnected,
    AccountNotFound,
    EmailFetchError,
    EmailSendError,
)
from api.services.auth_detection import is_auth_error
from api.schemas.email import EmailOut, EmailSendRequest
from api.services.account_factory import build_client_label
from api.services.manager_registry import get_manager
from api.storage.json_store import account_store


router = APIRouter(prefix="/users/{user_id}/emails", tags=["emails"])


@router.get("/unread", response_model=list[EmailOut])
def list_unread_emails(user_id: str) -> list[EmailOut]:
    """
    Fetch unread emails for all accounts under a user.
    """
    manager = get_manager(user_id)
    manager.authenticate_all()
    errors = manager.get_last_errors()
    if errors:
        auth_labels = [label for label, error in errors.items() if is_auth_error(error)]
        if auth_labels:
            raise AccountNotConnected(
                "One or more accounts are not connected. Call /connect first.",
                {"account_labels": auth_labels},
            )
        raise EmailFetchError(
            "Failed to authenticate one or more accounts.",
            {"account_labels": list(errors.keys())},
        )
    try:
        unread = manager.fetch_all_unread_emails()
    except Exception as exc:
        if is_auth_error(exc):
            raise AccountNotConnected(
                "One or more accounts are not connected. Call /connect first."
            ) from exc
        raise EmailFetchError("Failed to fetch unread emails.") from exc

    errors = manager.get_last_errors()
    if errors:
        auth_labels = [label for label, error in errors.items() if is_auth_error(error)]
        if auth_labels:
            raise AccountNotConnected(
                "One or more accounts are not connected. Call /connect first.",
                {"account_labels": auth_labels},
            )
        raise EmailFetchError(
            "Failed to fetch unread emails from one or more accounts.",
            {"account_labels": list(errors.keys())},
        )

    return [EmailOut.from_core(email) for email in unread]


@router.post("/send")
def send_email(user_id: str, payload: EmailSendRequest) -> dict[str, str]:
    """
    Send an email using a specific account under the user.
    """
    account = account_store.get(user_id, payload.account_id)
    if account is None:
        raise AccountNotFound(f"Account '{payload.account_id}' not found.")

    manager = get_manager(user_id)
    account_label = build_client_label(user_id, payload.account_id)

    try:
        manager.send_email_from_account(
            account_label=account_label,
            subject=payload.subject,
            body=payload.body,
            recipients=payload.recipients,
        )
    except Exception as exc:
        if is_auth_error(exc):
            raise AccountNotConnected(
                "Account is not connected. Call /connect first.",
                {"account_id": payload.account_id, "account_label": account_label},
            ) from exc
        raise EmailSendError("Failed to send email.") from exc

    return {"status": "sent"}
