"""
Provider app-credentials loading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.database.settings import get_provider_credentials_path
from api.errors.exceptions import AccountMisconfigured, CredentialFileError


def load_app_credentials(provider: str) -> dict[str, Any]:
    """
    Load provider OAuth app credentials from a JSON file path in env vars.
    """
    normalized_provider = (provider or "").strip().lower()
    credentials_path = get_provider_credentials_path(normalized_provider)
    if credentials_path is None:
        raise AccountMisconfigured(f"Unknown provider '{provider}'.")

    config_path = Path(credentials_path)
    try:
        raw = config_path.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialFileError(
            "Failed to read config storage file.", {"path": str(config_path)}
        ) from exc

    if not isinstance(data, dict):
        raise CredentialFileError(
            "Config storage file is corrupted.", {"path": str(config_path)}
        )

    if normalized_provider == "gmail":
        if isinstance(data.get("installed"), dict):
            return data["installed"]
        if isinstance(data.get("web"), dict):
            return data["web"]

    return data
