"""PostToolUse hook: run ruff check on .py files edited/written by Claude.

Reads JSON from stdin (standard Claude Code hook input). Filters by .py
extension first — if the edited file is not Python, exits silently.
"""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response") or {}
    file_path = (
        tool_input.get("file_path")
        or tool_response.get("filePath")
        or ""
    )

    if not file_path.lower().endswith(".py"):
        return 0

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select=E,F,I", file_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
