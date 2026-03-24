# CLAUDE.md

  This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

  Project-specific details are maintained in @repository_guide.md (auto-imported into context).

  ---

  ## General Architecture 

  This section describes the layered architecture, structural rules, and conventions that apply to any project following this pattern. It is project-agnostic and should not be
  modified for domain-specific changes.

  ### 1 Layer Rules (Auto-Loaded)

  Each layer has its own `CLAUDE.md` that Claude Code loads automatically when reading files in that directory. These layer-level `CLAUDE.md` files are project-agnostic,
  transferable, and **must never be modified**. Each one references internally a `*_guide.md` with project-specific details.

  Layers with their own `CLAUDE.md`:
  - `backend/api/`
  - `backend/auth/`
  - `backend/database/`
  - `backend/core/`
  - `backend/Scripts/`
  - `backend/tests/unit/`
  - `backend/tests/integration/`
  - `backend/tests/e2e/`

  **Hard rule**: these layer rules are non-negotiable and override any conflicting project-specific guidance.

  ### 2 Monorepo Structure

  - `backend/` — API server organized in layers (FastAPI + Python).
  - `frontend/` — Client application (React + Vite + TypeScript + Tailwind).
  - Docker Compose orchestrates both services plus the database.

  ### 3 Excluded Directories

  - `backend/Scripts/` — personal developer scripts (manual tests, one-off utilities). Claude must **not** read, edit, or reference files in this directory unless the user explicitly requests it. These scripts are unrelated to the application's business logic, is only to try manual executions.

  ### 4 Backend Layers and Relationships

  → API (routers → services → rest of the layers)
  → Auth       (identity verification, session management)
  → Database   (persistence)
  → Core       (domain logic, provider clients)

  Communication rules:

  - Only **Services** (inside API) talk to Auth, Database, and Core.
  - Auth, Database, and Core are **independent** — none imports from another.
  - No lower layer imports from API.

  Each layer defines its own error hierarchy. Services translate lower-layer errors into API-layer errors. For specifics, consult the layer's `CLAUDE.md` (auto-loaded when reading files in that directory).

  ### 5 Two-Level Documentation Pattern

  Each layer has two documentation files:

  - `CLAUDE.md` (in each layer directory) — general, transferable rules. Not modified for project changes. Auto-loaded by Claude Code when reading files in that directory.
  - `*_guide.md` — project-specific details. Claude updates these when the project changes.

  The layer `CLAUDE.md` references its guide. This root `CLAUDE.md` lists the layers that have their own rules (§ 1.1).

  ### 6 Style and Code Quality

  - Python: PEP 8, FastAPI conventions, `from __future__ import annotations` in all modules.
  - TypeScript: ESLint config in `frontend/eslint.config.js`.
  - Code language: English everywhere — identifiers, comments, docstrings, and all `.md` documentation files tracked by git.
  - Comments only where they clarify non-obvious logic; avoid noise or redundancy.

  ### 7 Immutable Files

  All layer-level `CLAUDE.md` files (listed in § 1.1) are protected by a pre-edit hook that prevents any modification. Claude must never propose direct edits to these files. Instead, describe the suggested change — what, where, and why — so the developer can apply it manually.
  Project-specific changes always go in the corresponding `*_guide.md` file, which is not protected.

  ### 8 Plan Execution Rules

  Every plan produced in plan mode for a non-trivial feature implementation must include these two final steps, in this order:

  **Penultimate step — Documentation update (critical):**
  This step is the foundation of the entire quality assurance system. The Documentation Priority rule (§ 1.8) establishes that `.md` files are always the source of truth: when code contradicts documentation, the documentation is correct and the code must change. Review workflows (`/reviewDiffsBeforeCommit`, md-reviewer, etc.) rely on this principle to catch and fix code mistakes.

  This only works if the documentation accurately reflects the intended behavior after every plan execution. If a `*_guide.md` is left outdated or partially updated, two things break:
  1. Legitimate new code may be flagged as "wrong" because it doesn't match the stale `.md`.
  2. Actual code mistakes may go undetected because the `.md` never described the new functionality.

  Therefore, this documentation update is not a formality — it is the step that keeps the `.md`-as-source-of-truth model reliable.
  Launch the `md-reviewer` agent targeting:
  - Root `repository_guide.md`.
  - Root `README.md`.
  - Every `*_guide.md` in directories affected by the plan's changes.

  Based on the reviewer's findings, propose and apply the necessary documentation updates so all `.md` files accurately reflect the new or changed functionality.

  **Final step — Test execution:**
  Run all test suites that were added or modified during plan execution — unit, integration, and e2e. Do not run only one layer; run every test file that was created or edited as part of the implementation.

  ### 9 Documentation Priority

  When rules or information conflict, the following precedence applies (highest to lowest):
  **This root `CLAUDE.md`** — general architecture rules. Supreme authority.
  **Layer `CLAUDE.md` files** (e.g. `backend/api/CLAUDE.md`) — structural rules for that layer. Override anything below.
  **`*_guide.md` files** (e.g. `api_guide.md`, `repository_guide.md`) — project-specific details that supplement the `CLAUDE.md` files. Never contradict levels above.
  **The source code itself** — the actual implementation. When code contradicts documentation at any level above, the documentation is correct and the code is what needs to change.

  This hierarchy applies to all decisions: error handling, layer boundaries, naming conventions, allowed imports, and any other rule. If a lower-priority source conflicts with a higher-priority one, always follow the higher-priority source and flag the conflict.