---
name: reviewQueries
disable-model-invocation: true
---

Launch parallel `queries-reviewer` agents to audit SQL query functions for efficiency, reusability, dead code, and quality. One agent per `.py` file.

$ARGUMENTS

CRITICAL EXECUTION RULE — follow this EXACTLY:

1. Determine the scope based on `$ARGUMENTS`:

   **A) No arguments** (empty or blank): use `Glob` to list all `.py` files in `backend/database/queries/` (exclude `__init__.py`). Each file becomes a target.

   **B) One or more `.py` file paths** (space-separated, e.g., `backend/database/queries/accounts.py backend/database/queries/auth.py`): use those files as targets.

   **C) The word `diffs`**: run `git diff --name-only` and `git diff --cached --name-only` via Bash. From the combined output, keep only files that match `backend/database/queries/*.py` (exclude `__init__.py`). Each matching file becomes a target. If no query files appear in the diffs, inform the user "No query files found in current diffs." and STOP.

2. Launch exactly **one** `queries-reviewer` agent per target file, all in parallel in a **single message** with multiple Agent tool calls. Each agent uses `run_in_background: true` and `subagent_type: "queries-reviewer"`. Each agent's prompt: "Analyze ONLY the file `{file_path}`. Focus exclusively on this file and on the usage flow of the query functions it contains. Do NOT read or analyze any other query file in `backend/database/queries/`."

3. After launching, your response MUST END IMMEDIATELY. Write a brief message listing the agents launched (count and file names) and tell the user you will report when they finish — then STOP. Do NOT add any more tool calls.

4. Do NOT poll, retry, resume, or call any tool after launching the agents. The main thread must be completely idle until the automatic completion notifications arrive.

5. Only when ALL agents have completed (via automatic notifications), present a unified summary to the user with the results from each file.
