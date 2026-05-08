#!/usr/bin/env python3
"""PreToolUse hook: block any write/edit on this project's
``.claude/settings.local.json``.

Triggered for the four filesystem-mutating structured tools
(Write, Edit, MultiEdit, NotebookEdit). Resolves the target path against the
project root and denies the operation when it lands on the protected file.
Any other target passes through unchanged.

Project policy is documented in ``repository_guide.md`` (section
"Claude Code Configuration"): a single contributor on a single machine works
exclusively from the tracked ``.claude/settings.json``; the gitignored
``.claude/settings.local.json`` must not be recreated or modified by any tool.

Bash is intentionally NOT covered here. A shell command such as
``echo {} > .claude/settings.local.json`` would bypass this hook. Adding a
Bash matcher would require fragile shell parsing; if that protection is
needed, register a separate Bash-aware hook.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROTECTED_RELATIVE = Path(".claude") / "settings.local.json"


def _extract_target(tool_name: str, tool_input: dict) -> str:
    if tool_name == "NotebookEdit":
        return str(tool_input.get("notebook_path") or "")
    return str(tool_input.get("file_path") or "")


def _normalize(path_str: str, project_dir: Path) -> Path | None:
    if not path_str:
        return None
    if sys.platform == "win32" and len(path_str) >= 3:
        # MSYS / Git Bash absolute form: "/c/Users/..." → "C:/Users/..."
        if (
            path_str[0] == "/"
            and path_str[1].isalpha()
            and path_str[2] == "/"
        ):
            path_str = path_str[1] + ":/" + path_str[3:]
    try:
        candidate = Path(path_str)
        if not candidate.is_absolute():
            candidate = project_dir / candidate
        return Path(os.path.normcase(os.path.normpath(str(candidate))))
    except (OSError, ValueError):
        return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    target = _extract_target(tool_name, tool_input)
    if not target:
        return 0

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    protected = _normalize(str(project_dir / PROTECTED_RELATIVE), project_dir)
    candidate = _normalize(target, project_dir)
    if candidate is None or protected is None:
        return 0

    if candidate != protected:
        return 0

    reason = (
        "BLOCKED: '.claude/settings.local.json' is protected in this project. "
        "All Claude Code permissions, hooks, MCP toggles and plugins live in "
        "the tracked '.claude/settings.json' (single-contributor, "
        "single-machine setup). See repository_guide.md "
        "('Claude Code Configuration') for the rationale."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
