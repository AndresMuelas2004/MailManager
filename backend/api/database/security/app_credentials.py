"""
Provider app-credentials loading.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from api.errors.exceptions import AccountMisconfigured, DatabaseError, EnvVarError


_ENV_CREDENTIALS: dict[str, str] = {
    "gmail": "MIA_GMAIL_CREDENTIALS_PATH",
    "outlook": "MIA_OUTLOOK_CREDENTIALS_PATH",
}


def load_app_credentials(provider: str) -> dict[str, Any]:
    """
    Load provider OAuth app credentials from a JSON file path in env vars.
    """
    normalized_provider = (provider or "").strip().lower()
    env_var = _ENV_CREDENTIALS.get(normalized_provider)
    if not env_var:
        raise AccountMisconfigured(f"Unknown provider '{provider}'.")

    credentials_path = os.getenv(env_var, "").strip()
    if not credentials_path:
        raise EnvVarError(f"{env_var} is not set.")

    config_path = Path(credentials_path)
    try:
        raw = config_path.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseError("Failed to read config storage file.", {"path": str(config_path)}) from exc

    if not isinstance(data, dict):
        raise DatabaseError("Config storage file is corrupted.", {"path": str(config_path)})

    if normalized_provider == "gmail":
        if isinstance(data.get("installed"), dict):
            return data["installed"]
        if isinstance(data.get("web"), dict):
            return data["web"]

    return data

