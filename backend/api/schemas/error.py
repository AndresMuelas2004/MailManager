"""
Pydantic schemas for standardized error responses.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """
    Structured error details returned by the API.
    """

    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """
    Envelope for API error responses.
    """

    error: ErrorDetail
