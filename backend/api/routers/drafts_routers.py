"""
Drafts router — draft creation under a mailbox/account.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.routers.routers_helpers import require_session
from api.schemas.draft import DraftCreate, DraftOut
from api.services import drafts_service


router = APIRouter(
    prefix="/mailboxes/{mailbox_id}/accounts/{account_id}/drafts",
    tags=["drafts"],
)


@router.post("", response_model=DraftOut)
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
