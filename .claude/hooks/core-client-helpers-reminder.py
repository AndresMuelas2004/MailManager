"""
PostToolUse hook: when Read targets gmail_client.py, outlook_client.py,
or email_manager.py inside backend/core/email/, inject a reminder to
maximise helper reuse.
"""
from __future__ import annotations

import json
import sys

TARGET_FILES = ("gmail_client.py", "outlook_client.py", "email_manager.py")
CORE_PATH_FRAGMENT = "backend/core/email/"

REMINDER = (
    "REMINDER — Core helper reuse policy (see core_guide.md § Helper Reuse Policy):\n"
    "1. Check helpers.py for shared functions before writing new logic "
    "(parse_expiry, unwrap_app_credentials, unwrap_user_tokens, "
    "wrap_account_tokens, http_error_detail).\n"
    "2. Scan this file for existing private methods (_*) and reuse them.\n"
    "3. If new logic is useful to more than one client, extract it to helpers.py."
)


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path: str = (data.get("tool_input") or {}).get("file_path", "")
    normalised = file_path.replace("\\", "/")

    if CORE_PATH_FRAGMENT in normalised and normalised.endswith(TARGET_FILES):
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": REMINDER,
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
