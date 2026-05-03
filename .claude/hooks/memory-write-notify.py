#!/usr/bin/env python3
"""Stop hook: surface a red notice when MEMORY.md was written this turn.

Reads the per-session flag dropped by ``memory-write-flag.py``. When present,
prints a single ANSI-red line to stderr and exits with code 1 so Claude Code
shows it to the user (non-blocking — the session still ends normally) and then
removes the flag so the message fires only once per turn.
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

    if payload.get("stop_hook_active") is True:
        return 0

    session_id = str(payload.get("session_id") or "unknown").strip() or "unknown"

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    flag_file = (
        Path(project_dir) / ".claude" / ".memory-write-flags" / f"{session_id}.flag"
    )
    if not flag_file.is_file():
        return 0

    try:
        raw = flag_file.read_text(encoding="utf-8")
    except OSError:
        return 0

    files = sorted({line.strip() for line in raw.splitlines() if line.strip()})

    try:
        flag_file.unlink()
    except OSError:
        pass

    if not files:
        return 0

    formatted = ", ".join(files)
    sys.stderr.write(
        f"\033[1;31m[MEMORY] Se ha escrito en MEMORY.md durante este turno: "
        f"{formatted}\033[0m\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
