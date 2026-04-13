"""
Drafts router — draft creation, listing and provider sync under a mailbox.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.routers.routers_helpers import require_session
from api.schemas.draft import DraftCreate, DraftOut, DraftsSyncResultOut, DraftUpdate
from api.services import drafts_service


router = APIRouter(
    prefix="/mailboxes/{mailbox_id}",
    tags=["drafts"],
)


@router.post("/accounts/{account_id}/drafts", response_model=DraftOut)
def create_draft(
    mailbox_id: str,
    account_id: str,
    payload: DraftCreate,
    user_id: str = Depends(require_session),
) -> DraftOut:
    """
    Create a new draft at the provider and persist it locally.
    """
    return drafts_service.create_draft(mailbox_id, account_id, payload, user_id)


@router.patch(
    "/accounts/{account_id}/drafts/{provider_draft_id}",
    response_model=DraftOut,
)
def update_draft(
    mailbox_id: str,
    account_id: str,
    provider_draft_id: str,
    payload: DraftUpdate,
    user_id: str = Depends(require_session),
) -> DraftOut:
    """
    Replace an existing draft at the provider and persist the new
    content locally. Provider-First: the provider call runs before any
    DB write.
    """
    return drafts_service.update_draft(
        mailbox_id, account_id, provider_draft_id, payload, user_id,
    )


@router.get("/drafts", response_model=list[DraftOut])
def list_drafts(
    mailbox_id: str,
    account_id: str | None = Query(default=None),
    user_id: str = Depends(require_session),
) -> list[DraftOut]:
    """
    List drafts for a mailbox.

    Query parameters:
    - account_id: optional. If provided, returns only drafts of that account.
      If omitted or None, returns drafts from all accounts in the mailbox.
    """
    return drafts_service.list_drafts(mailbox_id, user_id, account_id)


@router.post("/drafts/sync", response_model=DraftsSyncResultOut)
def sync_drafts(
    mailbox_id: str,
    account_id: str | None = Query(default=None),
    user_id: str = Depends(require_session),
) -> DraftsSyncResultOut:
    """
    Load drafts from the provider(s) into the local database.

    Query parameters:
    - account_id: optional. If provided, syncs only that account. If
      omitted or None, syncs every account in the mailbox.

    Both providers cap the fetch at 100 drafts per account (most recent).
    """
    return drafts_service.sync_drafts(mailbox_id, user_id, account_id)


@router.delete("/accounts/{account_id}/drafts/{draft_id}")
def delete_draft(
    mailbox_id: str,
    account_id: str,
    draft_id: str,
    user_id: str = Depends(require_session),
) -> dict[str, str]:
    """
    Delete a draft at the provider and then from the local database.
    """
    return drafts_service.delete_draft(mailbox_id, account_id, draft_id, user_id)
