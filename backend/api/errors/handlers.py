"""
FastAPI exception handlers for API errors.

Handlers translate domain-specific exceptions into consistent HTTP responses.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from api.errors.exceptions import (
    AccountMisconfigured,
    AccountNotConnected,
    AccountNotFound,
    ApiError,
    EmailFetchError,
    EmailSendError,
    EnvVarError,
    ExternalAPIError,
    ProviderAuthError,
    StorageError,
    MailboxNotFound,
)
from api.schemas.error import ErrorResponse


_STATUS_MAP: dict[type[ApiError], int] = {
    MailboxNotFound: status.HTTP_404_NOT_FOUND,
    AccountNotFound: status.HTTP_404_NOT_FOUND,
    AccountMisconfigured: status.HTTP_400_BAD_REQUEST,
    ProviderAuthError: status.HTTP_401_UNAUTHORIZED,
    AccountNotConnected: status.HTTP_409_CONFLICT,
    EmailFetchError: status.HTTP_502_BAD_GATEWAY,
    EmailSendError: status.HTTP_502_BAD_GATEWAY,
    ExternalAPIError: status.HTTP_502_BAD_GATEWAY,
    EnvVarError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    StorageError: status.HTTP_503_SERVICE_UNAVAILABLE,
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
        fallback = ApiError("Unexpected server error.")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(fallback),
        )

