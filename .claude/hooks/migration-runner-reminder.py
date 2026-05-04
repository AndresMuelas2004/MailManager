"""
PostToolUse hook: when Edit/Write targets an Alembic migration version file,
inject a reminder to keep backend/database/migrations/runner.py in sync.
"""
from __future__ import annotations

import json
import sys

PATH_FRAGMENT = "backend/database/migrations/versions/"

REMINDER = (
    "MIGRATION SYNC REMINDER: You just edited an Alembic migration file. "
    "Remember to update backend/database/migrations/runner.py to match: "
    "add the equivalent DDL statement to _DDL_STATEMENTS and update the "
    "alembic_version stamp to this migration revision. The fallback runner "
    "must always reflect the same final schema as Alembic."
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
