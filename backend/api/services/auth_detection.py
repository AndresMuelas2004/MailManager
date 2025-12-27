"""
Authentication error detection helpers.

This module centralizes best-effort checks for provider auth failures
without touching core provider implementations.
"""

from __future__ import annotations


def is_auth_error(exc: Exception) -> bool:
    """
    Return True when the exception looks like an auth/connectivity issue.
    """
    message = str(exc).lower()
    keywords = [
        "not authenticated",
        "authenticate",
        "authentication",
        "credential",
        "token",
    ]
    return any(keyword in message for keyword in keywords)
