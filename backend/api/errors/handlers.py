"""
FastAPI exception handlers for API errors.

Handlers translate domain-specific exceptions into consistent HTTP responses.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from api.errors.exceptions import (
    AccountConnectAuthError,
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    AppCredentialsInvalid,
    AppCredentialsMissing,
    CredentialFileError,
    DatabaseConnectionError,
    DatabaseMigrationError,
    DatabaseQueryError,
    EmailFetchError,
    EmailSendError,
    EnvVarError,
    ExternalAPIError,
    Forbidden,
    MailboxNotFound,
    RecipientsMissing,
    TokenDecryptionError,
    TokenIntegrityError,
    Unauthorized,
    UserNotFound,
)
from api.schemas.error import ErrorResponse


_STATUS_MAP: dict[type[ApiError], int] = {
    Unauthorized: status.HTTP_401_UNAUTHORIZED,
    Forbidden: status.HTTP_403_FORBIDDEN,
    MailboxNotFound: status.HTTP_404_NOT_FOUND,
    AccountNotFound: status.HTTP_404_NOT_FOUND,
    UserNotFound: status.HTTP_404_NOT_FOUND,
    AccountMisconfigured: status.HTTP_400_BAD_REQUEST,
    AppCredentialsInvalid: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AppCredentialsMissing: status.HTTP_500_INTERNAL_SERVER_ERROR,
    AccountConnectAuthError: status.HTTP_401_UNAUTHORIZED,
    AccountNotConnected: status.HTTP_409_CONFLICT,
    EmailFetchError: status.HTTP_502_BAD_GATEWAY,
    EmailSendError: status.HTTP_502_BAD_GATEWAY,
    RecipientsMissing: status.HTTP_400_BAD_REQUEST,
    ExternalAPIError: status.HTTP_502_BAD_GATEWAY,
    EnvVarError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    CredentialFileError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    DatabaseConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,
    DatabaseMigrationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    DatabaseQueryError: status.HTTP_503_SERVICE_UNAVAILABLE,
    TokenDecryptionError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    TokenIntegrityError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _error_payload(exc: ApiError) -> dict:
    """
    Build a standard JSON response payload for API errors.
    """
    payload = ErrorResponse(
        error={"code": exc.code, "message": exc.message, "detail": exc.detail}
    )
    return payload.model_dump()


def register_error_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers for the API.
    """

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        status_code = _STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse(status_code=status_code, content=_error_payload(exc))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        fallback = ApiError("Unexpected server error.")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(fallback),
        )
