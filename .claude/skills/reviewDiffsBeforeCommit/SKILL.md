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

5. Determine which **test directories** are affected by the diffs. Default candidates: `backend/tests/unit/`, `backend/tests/integration/`, `backend/tests/e2e/`. A test directory is "affected" if at least one changed file's path starts with it. Only affected test directories will receive a tests-quality-reviewer and an md-reviewer agent.

6. Parse $ARGUMENTS (if provided):
   - If `--tests` flag present: use the paths following it as the test directory candidates, but still filter to only those with at least one changed file in the diffs.
   - If `--tests` flag absent: use the defaults filtered in step 5.
   - If `--md` flag present: collect the paths following it as extra MD files to review.

7. If `backend/database/` is affected, collect the list of changed query files: filter the diff file list for paths matching `backend/database/queries/*.py` (exclude `__init__.py`). These are the only query files that will receive a queries-reviewer agent. If no query files were changed, skip query review entirely.

8. Print a brief summary to the user:
   - List of changed files (truncated if > 30)
   - Affected backend directories
   - Test directories to review
   - Then proceed immediately to Phase 2.

---

## PHASE 2 — Launch All Agents (single message, all `run_in_background: true`)

Launch ALL of the following agents in a SINGLE message with multiple Agent tool calls. Every agent uses `run_in_background: true`.

### Per affected backend directory (up to 4 dirs x 2 agents = 8 agents):

For EACH affected directory, launch:

1. **error-structure-reviewer** — `subagent_type: "error-structure-reviewer"`
   - Prompt: "Audit error handling compliance and coverage. Analyze ONLY the following files (they are the ones with diffs in this commit): {list of changed files in this directory}. For each file, review ONLY the changed/added code (the diffs), not the entire file. Read the layer's CLAUDE.md and *_guide.md for the error hierarchy rules. Do NOT read or analyze files outside this list."

2. **dead-code-finder** — `subagent_type: "dead-code-finder"`
   - Prompt: "Scan for dead code: unused functions, methods, variables, classes, constants, imports, and orphan files. Analyze ONLY the following files (they are the ones with diffs in this commit): {list of changed files in this directory}. For each file, focus exclusively on the changed/added code (the diffs), not the entire file. Do NOT read or analyze files outside this list."

### Test quality (1 agent per **affected** test directory):

For EACH **affected** test directory (filtered in Phase 1 step 5), launch:

3. **tests-quality-reviewer** — `subagent_type: "tests-quality-reviewer"`
   - Prompt: "Audit test quality, coverage completeness, and architectural soundness. Analyze ONLY the following test files (they are the ones with diffs in this commit): {list of changed files in this test directory}. For each file, focus exclusively on the changed/added code (the diffs), not the entire file. Do NOT read or analyze test files outside this list."
   - Do NOT launch for test directories that have zero changed files in the diffs.

### Documentation MD (variable number of agents):

4. **md-reviewer for each affected guide** — `subagent_type: "md-reviewer"`
   - One agent per `*_guide.md` of each affected directory.
   - Prompt: "Read the full content of `{guide_path}`. Then read ONLY the following changed files in this directory (they are the ones with diffs in this commit): {list of changed files in this directory}. Your task is to determine whether the diffs introduce new or modified functionality that is not yet reflected in the guide. Do NOT read or analyze any other file in the directory — only the changed files listed above. If the guide needs updates to accurately describe the new/modified functionality from these diffs, report exactly what should be added or changed. Ignore any pre-existing gaps unrelated to these diffs."

5. **md-reviewer for test guides** (one per **affected** test directory only) — `subagent_type: "md-reviewer"`
   - Only launch for test directories that were identified as affected in Phase 1 step 5.
   - Prompt: "Read the full content of `{test_guide_path}`. Then read ONLY the following changed test files (they are the ones with diffs in this commit): {list of changed files in this test directory}. Your task is to determine whether the diffs introduce new or modified tests that are not yet reflected in the guide. Do NOT read or analyze any other test file — only the changed files listed above. If the guide needs updates to accurately describe the new/modified test coverage from these diffs, report exactly what should be added or changed. Ignore any pre-existing gaps unrelated to these diffs."
   - Guide paths: `backend/tests/unit/unit_guide.md`, `backend/tests/integration/integration_guide.md`, `backend/tests/e2e/e2e_guide.md`

6. **md-reviewer for extra MDs** (only if `--md` in $ARGUMENTS) — `subagent_type: "md-reviewer"`
   - One agent per extra MD path provided.

### Query review (only if changed query files exist in the diffs):

8. **queries-reviewer per changed query file** — `subagent_type: "queries-reviewer"`
   - From the diff file list (collected in Phase 1 step 7), use only the `.py` files in `backend/database/queries/` (exclude `__init__.py`) that were actually changed.
   - If no query files were changed → skip query review entirely, even if `backend/database/` is affected.
   - Launch one agent per changed query file. Each agent's prompt: "Analyze ONLY the file `{file_path}`. Focus exclusively on this file and on the usage flow of the query functions it contains. Do NOT read or analyze any other query file in `backend/database/queries/`. Follow all analysis phases (inventory, usage, efficiency, quality, cross-validation) scoped exclusively to this file."

### After launching:

Print a brief message listing all agents launched (count and types) and tell the user you will report when they all finish. Then STOP — do NOT add any more tool calls. Do NOT poll, retry, resume, or call any tool. Wait for automatic completion notifications.

---

## PHASE 3 — Consolidation (only after ALL agents complete)

Only when ALL agents have reported back (via automatic completion notifications):

1. Collect all findings from every subagent.

2. Deduplicate: remove findings that overlap between reviewers (e.g., a dead-code finding that an error-reviewer also flagged).

3. **Two-tier classification — MANDATORY.** Every finding must first be classified into one of two groups by comparing the finding's file against the diff file list:

   - **Group A — New code findings**: the finding concerns code, tests, or documentation that was introduced or modified in this diff. If the file appears in the diff list AND the finding is about new/changed content, it belongs here.
   - **Group B — Pre-existing findings**: the finding was detected by reviewers in code that was NOT changed in this diff. These are informational only — they never affect the commit verdict.

4. Within each group, classify each finding by severity:

| Severity       | Criteria |
|----------------|----------|
| **Blocker**    | Prevents commit — errors, broken code, critical inconsistencies, missing error handling for required cases |
| **Major**      | Must fix — significant quality problems, incorrect documentation, untested critical paths |
| **Minor**      | Should fix — style issues, naming inconsistencies, small doc gaps |
| **Suggestion** | Optional — improvement ideas, future refactoring opportunities |

5. Present the consolidated report in this format:

```
## Pre-Commit Review Report

### Executive Summary
- Group A (new code): X blocker(s), Y major(s), Z minor(s), W suggestion(s)
- Group B (pre-existing): X blocker(s), Y major(s), Z minor(s), W suggestion(s)
- Verdict: BLOCK COMMIT / REVIEW BEFORE COMMIT / SAFE TO COMMIT (based on Group A only)

### Group A — New Code Findings

#### backend/api/
##### Error Handling
- [Severity] finding...
##### Dead Code
- [Severity] finding...

#### backend/database/
##### Error Handling
- [Severity] finding...
##### Query Review
- [Severity] finding...

#### Tests
##### unit
- [Severity] finding...
##### integration
- [Severity] finding...

#### Documentation
- [Severity] finding...

### Group B — Pre-Existing Findings (informational, do not affect verdict)

#### backend/api/
- [Severity] finding...

#### backend/core/
- [Severity] finding...

#### Documentation
- [Severity] finding...
```

6. Verdict rules — **based on Group A only** (Group B findings never block the commit):
   - Any Blocker **in Group A** → **BLOCK COMMIT**
   - No Blockers but any Major **in Group A** → **REVIEW BEFORE COMMIT**
   - Only Minor/Suggestion **in Group A** or no Group A findings → **SAFE TO COMMIT**

7. If no findings at all across all agents, say: "All reviews passed. No issues found. SAFE TO COMMIT."
