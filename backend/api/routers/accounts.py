"""
Account router for provider-agnostic account management.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.account import AccountConnectResponse, AccountCreate, AccountOut, AccountUpdate
from api.services import accounts_service


router = APIRouter(prefix="/mailboxes/{mailbox_id}/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(mailbox_id: str) -> list[AccountOut]:
    """
    List all accounts for a mailbox.
    """
    return accounts_service.list_accounts(mailbox_id)


@router.post("", response_model=AccountOut)
def create_account(mailbox_id: str, payload: AccountCreate) -> AccountOut:
    """
    Create a new account for the mailbox.
    """
    return accounts_service.create_account(mailbox_id, payload)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(mailbox_id: str, account_id: str) -> AccountOut:
    """
    Fetch a single account by identifier.
    """
    return accounts_service.get_account(mailbox_id, account_id)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(mailbox_id: str, account_id: str, payload: AccountUpdate) -> AccountOut:
    """
    Update mutable fields of an account.
    """
    return accounts_service.update_account(mailbox_id, account_id, payload)


@router.delete("/{account_id}")
def delete_account(mailbox_id: str, account_id: str) -> dict[str, str]:
    """
    Delete an account and invalidate the mailbox manager cache.
    """
    return accounts_service.delete_account(mailbox_id, account_id)


@router.post("/{account_id}/connect", response_model=AccountConnectResponse)
def connect_account(mailbox_id: str, account_id: str) -> AccountConnectResponse:
    """
    Verify and connect an account by running provider authentication.
    """
    return accounts_service.connect_account(mailbox_id, account_id)
