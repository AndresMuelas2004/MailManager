---
name: reviewDiffsBeforeCommit
description: "Exhaustive pre-commit review: analyze diffs, determine affected backend layers, launch parallel review subagents, and consolidate findings into a severity-graded report."
disable-model-invocation: true
---

Exhaustive pre-commit review: analyze diffs, determine affected backend layers, launch parallel review subagents, and consolidate findings into a severity-graded report.

Usage: `/reviewDiffsBeforeCommit` (uses defaults) or `/reviewDiffsBeforeCommit --tests backend/tests/unit/ --md extra/doc.md`

Optional $ARGUMENTS:
- `--tests dir1 dir2 ...` — override default test directories (default: `backend/tests/unit/` `backend/tests/integration/` `backend/tests/e2e/`)
- `--md path1 path2 ...` — add extra `.md` files to review beyond the auto-detected ones

---

## PHASE 1 — Diff Analysis (synchronous, before launching any agents)

Execute these steps sequentially:

1. Run `git diff --cached --name-only` (staged) and `git diff --name-only` (unstaged) via Bash. Combine both lists, deduplicate.

2. If the combined list is empty — inform the user "No diffs found (staged or unstaged). Nothing to review." and STOP. Do NOT launch any agents.

3. From the changed files, determine which of these 4 backend directories are affected (a directory is "affected" if at least one changed file's path starts with it):
   - `backend/api/`
   - `backend/database/`
   - `backend/auth/`
   - `backend/core/`

4. For each affected directory, identify its `*_guide.md` file:
   - `backend/api/` → `backend/api/api_guide.md`
   - `backend/database/` → `backend/database/database_guide.md`
   - `backend/auth/` → `backend/auth/auth_guide.md`
   - `backend/core/` → `backend/core/core_guide.md`

5. Parse $ARGUMENTS (if provided):
   - If `--tests` flag present: use the paths following it as the test directories (until the next flag or end).
   - If `--tests` flag absent: use defaults `backend/tests/unit/` `backend/tests/integration/` `backend/tests/e2e/`.
   - If `--md` flag present: collect the paths following it as extra MD files to review.

6. Check whether `README.md` exists at the repo root (via Glob or ls). Note its existence for Phase 2.

7. Print a brief summary to the user:
   - List of changed files (truncated if > 30)
   - Affected backend directories
   - Test directories to review
   - MD files to review
   - Then proceed immediately to Phase 2.

---

## PHASE 2 — Launch All Agents (single message, all `run_in_background: true`)

Launch ALL of the following agents in a SINGLE message with multiple Agent tool calls. Every agent uses `run_in_background: true`.

### Per affected backend directory (up to 4 dirs x 2 agents = 8 agents):

For EACH affected directory, launch:

1. **error-structure-reviewer** — `subagent_type: "error-structure-reviewer"`
   - Prompt: "Audit error handling compliance and coverage in `{directory}`. Read the layer's CLAUDE.md and *_guide.md for the error hierarchy rules. Focus on files changed in the current diffs: {list of changed files in this directory}."

2. **dead-code-finder** — `subagent_type: "dead-code-finder"`
   - Prompt: "Scan `{directory}` for dead code: unused functions, methods, variables, classes, constants, imports, and orphan files. Pay special attention to files changed in the current diffs: {list of changed files in this directory}."

### Test quality (1 agent per test directory):

For EACH test directory (from defaults or $ARGUMENTS override), launch:

3. **tests-quality-reviewer** — `subagent_type: "tests-quality-reviewer"`
   - Prompt: "Audit test quality, coverage completeness, and architectural soundness in `{test_directory}`. Check for test gaps, missing edge cases, and structural issues."

### Documentation MD (variable number of agents):

4. **md-reviewer for each affected guide** — `subagent_type: "md-reviewer"`
   - One agent per `*_guide.md` of each affected directory.
   - Prompt: "Review `{guide_path}` for accuracy, completeness, and clarity by cross-referencing the source code in its directory. Check that all documented contracts, functions, and behaviors match the current implementation."

5. **md-reviewer for test guides** (always, one per test directory) — `subagent_type: "md-reviewer"`
   - Prompt: "Review `{test_guide_path}` for accuracy and completeness by cross-referencing the test files and source code."
   - Default paths: `backend/tests/unit/unit_guide.md`, `backend/tests/integration/integration_guide.md`, `backend/tests/e2e/e2e_guide.md`

6. **md-reviewer for root CLAUDE.md** (always) — `subagent_type: "md-reviewer"`
   - Prompt: "Review `CLAUDE.md` (root) for accuracy and completeness. IMPORTANT: Only Section 2 (Project-Specific) is editable — Section 1 must never be modified. Flag any inaccuracies in Section 2 by cross-referencing the current codebase. Do NOT suggest changes to Section 1."

7. **md-reviewer for README.md** (only if it exists) — `subagent_type: "md-reviewer"`
   - Prompt: "Review `README.md` for accuracy, completeness, and clarity by cross-referencing the current codebase."

8. **md-reviewer for extra MDs** (only if `--md` in $ARGUMENTS) — `subagent_type: "md-reviewer"`
   - One agent per extra MD path provided.

### Query review (only if `backend/database/` is affected):

9. **queries-reviewer per query file** — `subagent_type: "queries-reviewer"`
   - Use `Glob` to list all `.py` files in `backend/database/queries/` (exclude `__init__.py`).
   - Launch one agent per file. Each agent's prompt: "Analyze ONLY the file `{file_path}`. Focus exclusively on this file and on the usage flow of the query functions it contains. Do NOT read or analyze any other query file in `backend/database/queries/`. Follow all analysis phases (inventory, usage, efficiency, quality, cross-validation) scoped exclusively to this file."

### After launching:

Print a brief message listing all agents launched (count and types) and tell the user you will report when they all finish. Then STOP — do NOT add any more tool calls. Do NOT poll, retry, resume, or call any tool. Wait for automatic completion notifications.

---

## PHASE 3 — Consolidation (only after ALL agents complete)

Only when ALL agents have reported back (via automatic completion notifications):

1. Collect all findings from every subagent.

2. Deduplicate: remove findings that overlap between reviewers (e.g., a dead-code finding that an error-reviewer also flagged).

3. Classify each finding by severity:

| Severity       | Criteria |
|----------------|----------|
| **Blocker**    | Prevents commit — errors, broken code, critical inconsistencies, missing error handling for required cases |
| **Major**      | Must fix — significant quality problems, incorrect documentation, untested critical paths |
| **Minor**      | Should fix — style issues, naming inconsistencies, small doc gaps |
| **Suggestion** | Optional — improvement ideas, future refactoring opportunities |

4. Present the consolidated report in this format:

```
## Pre-Commit Review Report

### Executive Summary
- X blocker(s), Y major(s), Z minor(s), W suggestion(s)
- Verdict: BLOCK COMMIT / REVIEW BEFORE COMMIT / SAFE TO COMMIT

### backend/api/
#### Error Handling
- [Severity] finding...
#### Dead Code
- [Severity] finding...

### backend/database/
#### Error Handling
- [Severity] finding...
#### Dead Code
- [Severity] finding...
#### Query Review
- [Severity] finding...

### backend/auth/
(same structure, only if affected)

### backend/core/
(same structure, only if affected)

### Tests
#### unit
- [Severity] finding...
#### integration
- [Severity] finding...
#### e2e
- [Severity] finding...

### Documentation
#### Guides
- [Severity] finding...
#### Root docs (CLAUDE.md, README.md)
- [Severity] finding...
```

5. Verdict rules:
   - Any Blocker → **BLOCK COMMIT**
   - No Blockers but any Major → **REVIEW BEFORE COMMIT**
   - Only Minor/Suggestion or no findings → **SAFE TO COMMIT**

6. If no findings at all across all agents, say: "All reviews passed. No issues found. SAFE TO COMMIT."
