#!/usr/bin/env python3
"""PostToolUse hook: record any Write/Edit on a MEMORY.md during the current turn.

Drops a per-session flag file under ``.claude/.memory-write-flags/`` that the
companion ``memory-write-notify.py`` Stop hook consumes to surface a red notice
to the user once Claude finishes responding.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = str(tool_input.get("file_path") or "").strip()
    if not file_path:
        return 0

    if Path(file_path).name.lower() != "memory.md":
        return 0

    session_id = str(payload.get("session_id") or "unknown").strip() or "unknown"

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    flag_dir = Path(project_dir) / ".claude" / ".memory-write-flags"
    flag_dir.mkdir(parents=True, exist_ok=True)

    flag_file = flag_dir / f"{session_id}.flag"
    with flag_file.open("a", encoding="utf-8") as fh:
        fh.write(file_path + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
