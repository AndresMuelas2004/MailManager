"""
PostToolUse hook: when Edit/Write targets a database query file,
inject a reminder to maximise query reuse.
"""
from __future__ import annotations

import json
import sys

PATH_FRAGMENT = "backend/database/queries/"

REMINDER = (
    "REUSE DIRECTIVE: Before writing or modifying queries in this file, "
    "review all existing query constants. Avoid creating similar standalone "
    "queries when an existing one can be parameterized or reused. Keep the "
    "query surface area minimal, professional, and DRY."
)


def main() -> None:
    data = json.load(sys.stdin)
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    normalised = file_path.replace("\\", "/")

    if PATH_FRAGMENT in normalised and normalised.endswith(".py"):
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": REMINDER,
            }
        }
        print(json.dumps(output))


if __name__ == "__main__":
    main()
