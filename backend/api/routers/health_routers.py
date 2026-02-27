"""
Health check router.
"""

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """
    Minimal health check endpoint.
    """
    return {"status": "ok"}
