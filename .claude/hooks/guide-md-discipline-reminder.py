"""
PostToolUse hook: when Read targets any *_guide.md file inside this
repository, inject the "earn-its-tokens" discipline block at the END
of the model context (mirroring the same block at the top of every
*_guide.md, so the rule frames both reading and writing).
"""
from __future__ import annotations

import json
import sys

REMINDER = (
    "GUIDE.MD DISCIPLINE — applies to every *_guide.md you just read or are about to edit:\n\n"
    "> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**\n"
    "> - **YES -> delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, "
    "paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing "
    "file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.\n"
    "> - **NO -> keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave "
    "alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip "
    "through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, "
    "magic constants) that cannot be recomputed -- those earn their tokens.\n"
    ">\n"
    "> **When updating this file, re-read every section and delete anything that has since migrated into the code.** "
    "Staleness is worse than silence."
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
    normalised = file_path.replace("\\", "/").lower()

    if normalised.endswith("_guide.md"):
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
