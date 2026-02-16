"""
Database configuration loaded from environment variables.
"""

from __future__ import annotations

import os

from api.errors.exceptions import EnvVarError


def get_database_url() -> str:
    """
    Return the DATABASE_URL from the environment, or raise EnvVarError.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise EnvVarError("DATABASE_URL is not set.")
    return url
