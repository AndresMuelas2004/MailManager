"""
Core email package public surface.
"""

from core.email.email_client import EmailClient, EmailMessage
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
    "EmailAccountNotFoundError",
    "EmailAccountRecordError",
    "EmailAuthError",
    "EmailClient",
    "EmailConfigError",
    "EmailDuplicateAccountLabelError",
    "EmailError",
    "EmailExternalAPIError",
    "EmailInvalidCredentialsDataError",
    "EmailInvalidExpiryError",
    "EmailInvalidTokenDataError",
    "EmailManager",
    "EmailMessage",
    "EmailMissingAppCredentialsError",
    "EmailMissingRefreshTokenError",
    "EmailMissingTokenError",
    "EmailNotAuthenticatedError",
    "EmailProviderConfigError",
    "EmailRecipientsMissingError",
    "EmailRefreshFailedError",
]
