---
name: reviewDiffsBeforeCommitFrontend
description: "Pre-commit frontend architecture compliance check: read every frontend CLAUDE.md and verify the current diffs respect every rule, layer boundary, and convention stated in them. Use before committing frontend changes to catch violations early."
disable-model-invocation: true
---

Pre-commit review focused exclusively on **frontend architectural compliance**. The goal is simple: make sure nothing in the current diffs breaks any rule defined in the frontend `CLAUDE.md` files.

Usage: `/reviewDiffsBeforeCommitFrontend`

---

## Step 1 — Gather the diffs

Run in parallel:
- `git status` — see all changed and untracked files.
- `git diff -- frontend/` and `git diff --cached -- frontend/` — see unstaged and staged frontend changes.

If no frontend files are modified, stop and report that there is nothing to review.

## Step 2 — Load every frontend CLAUDE.md

Locate and **read in full** every `CLAUDE.md` under `frontend/` (both the root `frontend/CLAUDE.md` and any nested ones inside `frontend/src/**` or `frontend/e2e/`). These files are the source of truth for the frontend architecture.

Use `Glob` with pattern `frontend/**/CLAUDE.md` to enumerate them, then read each one. Do not skim — the compliance check depends on knowing every rule.

Also read `frontend/frontend_guide.md` if it exists, since layer `CLAUDE.md` files reference it for project-specific details that complement the structural rules.

## Step 3 — Extract the rules

From the CLAUDE.md files, build a mental checklist of every hard rule that applies to code changes. Typical categories to watch for in a React + Vite + TypeScript + Tailwind frontend:

- **Layer boundaries**: which directories may import from which (e.g., `api/` vs `features/` vs `components/` vs `app/`).
- **Allowed dependencies**: what can and cannot be imported from each layer.
- **Naming conventions**: files, components, hooks, types, DTOs.
- **State management rules**: where data fetching lives (e.g., TanStack Query in `api/endpoints/`), where local state is allowed.
- **Validation rules**: Zod schemas, DTO typing, runtime validation at boundaries.
- **Styling rules**: Tailwind-only vs CSS modules, restrictions on global CSS.
- **Security rules**: client-side rules about tokens, secrets, auth flows, dangerous HTML, redirects.
- **Routing and guards**: where `RequireAuth` / route guards must wrap components.
- **Testing rules**: what requires tests, where tests live (unit vs e2e), allowed testing utilities.
- **Immutability rules**: files that must never be modified (layer `CLAUDE.md` files themselves, for example).
- **Documentation rules**: when `*_guide.md` must be updated alongside code changes.

Do not rely on memory — only cite rules that are actually written in the CLAUDE.md files you read in Step 2.

## Step 4 — Map the diffs to the rules

For each changed file in the frontend diff:

1. Identify which layer it belongs to (root, `api/`, `app/`, `features/`, `components/`, `lib/`, `test/`, `e2e/`, etc.).
2. Look at what the diff actually does (new imports, new files, changed exports, new dependencies, new components, style changes, test changes).
3. Check every applicable rule from Step 3 against the change.

Be precise: quote the exact line from the CLAUDE.md that a change violates, and the exact diff line that violates it. Do not flag stylistic preferences that are not written as rules.

## Step 5 — Produce the compliance report

Output a single structured report:

### Compliance report

**Scope**: list every frontend file in the diff, grouped by layer.

**CLAUDE.md files consulted**: bullet list with the path of every CLAUDE.md you read.

**Findings**: one of the following for each diff:

- **PASS** — the change respects every applicable rule. State this briefly per file or per group.
- **VIOLATION** — include:
  - File and diff hunk (path + line range).
  - The rule that is violated, quoting the exact sentence from the relevant CLAUDE.md and the file it came from.
  - Why the diff violates it (one or two sentences).
  - Suggested fix.
- **AMBIGUOUS** — when a rule could be read either way. Explain the ambiguity, cite both interpretations, and ask the user which one to apply. Do not silently pick one.

**Verdict**: at the end, one of:
- `READY TO COMMIT` — zero violations.
- `BLOCKED` — one or more violations; list them by file.
- `NEEDS USER DECISION` — only ambiguities remain.

## Important rules for this skill

- Only review **frontend** changes. Ignore diffs outside `frontend/`.
- Do not run tests, do not run the dev server, do not modify any file. This skill is read-only — it produces a report, nothing else.
- Never propose edits to any `CLAUDE.md` file. If a rule seems wrong or outdated, flag it in the report as a note for the user; do not suggest editing the CLAUDE.md.
- If a diff touches a file that the root or any layer `CLAUDE.md` marks as immutable, that is automatically a VIOLATION — no exceptions.
- When a `*_guide.md` should have been updated to reflect a code change (per the root `CLAUDE.md` plan execution rules), flag it as a VIOLATION too, because the documentation-as-source-of-truth model depends on it.
- Prefer citing the highest-priority source when rules overlap: root `CLAUDE.md` > layer `CLAUDE.md` > `*_guide.md`.
