"""
Core email package public surface.
"""

from core.email.email_client import DraftMetadata, EmailClient, EmailContent, EmailMetadata, LabelUpdate, SpamMoveResult, SyncResult
from core.email.email_manager import EmailManager
from core.email.errors import (
    CoreError,
    EmailAccountNotFoundError,
    EmailAccountRecordError,
    EmailAuthError,
    EmailConfigError,
    EmailDuplicateAccountLabelError,
    EmailError,
    EmailExternalAPIError,
    EmailInvalidCredentialsDataError,
    EmailInvalidExpiryError,
    EmailInvalidTokenDataError,
    EmailMissingAppCredentialsError,
    EmailMissingRefreshTokenError,
    EmailMissingTokenError,
    EmailNotAuthenticatedError,
    EmailProviderConfigError,
    EmailRecipientsMissingError,
    EmailRefreshFailedError,
)

__all__ = [
    "CoreError",
    "DraftMetadata",
    "EmailAccountNotFoundError",
    "EmailAccountRecordError",
    "EmailAuthError",
    "EmailClient",
    "EmailContent",
    "EmailConfigError",
    "EmailDuplicateAccountLabelError",
    "EmailError",
    "EmailExternalAPIError",
    "EmailInvalidCredentialsDataError",
    "EmailInvalidExpiryError",
    "EmailInvalidTokenDataError",
    "EmailManager",
    "EmailMetadata",
    "LabelUpdate",
    "SpamMoveResult",
    "EmailMissingAppCredentialsError",
    "EmailMissingRefreshTokenError",
    "EmailMissingTokenError",
    "EmailNotAuthenticatedError",
    "EmailProviderConfigError",
    "EmailRecipientsMissingError",
    "EmailRefreshFailedError",
    "SyncResult",
]
