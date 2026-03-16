# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Section 1: General Architecture (do not modify)

This section describes the layered architecture, structural rules, and conventions that apply to any project following this pattern. It is project-agnostic and should not be modified for domain-specific changes.

### 1.1 On-Demand Loading

Before modifying, planning or think about any layer, read **only** its `general_*_rules.md`. Do not load rules for layers unrelated to the current task.

| Layer | General Rules |
|---|---|
| API | [`backend/api/general_api_rules.md`](backend/api/general_api_rules.md) |
| Auth | [`backend/auth/general_auth_rules.md`](backend/auth/general_auth_rules.md) |
| Database | [`backend/database/general_database_rules.md`](backend/database/general_database_rules.md) |
| Core | [`backend/core/general_core_rules.md`](backend/core/general_core_rules.md) |
| Unit Tests | [`backend/tests/unit/general_unit_rules.md`](backend/tests/unit/general_unit_rules.md) |
| Integration Tests | [`backend/tests/integration/general_integration_rules.md`](backend/tests/integration/general_integration_rules.md) |
| E2E Tests | [`backend/tests/e2e/general_e2e_rules.md`](backend/tests/e2e/general_e2e_rules.md) |

These files are project-agnostic and transferable. Each one references internally a `*_guide.md` with project-specific details.

**Hard rule**: these general rules are non-negotiable and override any conflicting project-specific guidance.

### 1.2 Monorepo Structure

- `backend/` — API server organized in layers (FastAPI + Python).
- `frontend/` — Client application (React + Vite + TypeScript + Tailwind).
- Docker Compose orchestrates both services plus the database.

### 1.3 Excluded Directories

- `backend/Scripts/` — personal developer scripts (manual tests, one-off utilities). Claude must **not** read, edit, or reference files in this directory unless the user explicitly requests it. These scripts are unrelated to the application's business logic.

### 1.4 Backend Layers and Relationships

```
API (routers → services)
  → Auth       (identity verification, session management)
  → Database   (persistence)
  → Core       (domain logic, provider clients)
```

Communication rules:

- Only **Services** (inside API) talk to Auth, Database, and Core.
- Auth, Database, and Core are **independent** — none imports from another.
- No lower layer imports from API.
- Database does not communicate with Core.

Each layer defines its own error hierarchy. Services translate lower-layer errors into API-layer errors. For specifics, read the relevant `general_*_rules.md`.

### 1.5 Two-Level Documentation Pattern

Each layer has two documentation files:

- `general_*_rules.md` — general, transferable rules. Not modified for project changes.
- `*_guide.md` — project-specific details. Claude updates these when the project changes.

The general rules file references its guide. This CLAUDE.md references the general rules files.

### 1.6 Style and Code Quality

- Python: PEP 8, FastAPI conventions, `from __future__ import annotations` in all modules.
- TypeScript: ESLint config in `frontend/eslint.config.js`.
- Code language: English everywhere — identifiers, comments, docstrings, and all `.md` documentation files tracked by git.
- Comments only where they clarify non-obvious logic; avoid noise or redundancy.

---

## Section 2: Project-Specific (maintained by Claude)

This section contains details specific to MailManager. Update it when the project changes (new providers, new endpoints, architectural shifts). Do not modify Section 1.

### 2.1 Project Overview

**MailManager** is a multi-account email management application.

- **Backend**: FastAPI (Python).
- **Frontend**: React + Vite + TypeScript + Tailwind.
- **Email providers**: Gmail and Outlook (both fully implemented).
- **Authentication**: Google OIDC.
- **Database**: PostgreSQL with Alembic migrations.

### 2.3 Request Flow

```
Routers (FastAPI)
  → routers_helpers.py (require_session → user_id)
  → Services (api/services/)
    → Auth (auth/)            — Google OIDC verification
    → Database (database/)    — PostgreSQL persistence
    → Core (core/)
      → EmailManager (core/email/email_manager.py)
        → GmailClient, OutlookClient
```



### 2.4 Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — optional human-readable label; defaults to `"{provider}:{account_id}"`.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).

### 2.5 Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/shared/email_fakes.py`. Cover service logic, auth settings, error translation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, isolate via `isolated_db` (transaction rollback). `require_session` overridden to return a fixed test user_id.
- Both test layers share `FakeEmailClient` and `build_metadata` via `tests/shared/`.
- **E2E tests** (`backend/tests/e2e/`) — automated like unit and integration tests. They test all endpoints except interactive OAuth flows (`POST /auth/google`, `POST .../connect`) and `DELETE /auth/me` (cannot create a test user without the interactive login). Real third-party APIs and real DB persistence. Pre-configured test accounts are already inserted in the database with valid tokens and must never be deleted — E2E tests can be run without additional setup.

### 2.6 Frontend

Stack: React + Vite + TypeScript + Tailwind. Structure:

- `src/api/` — HTTP client, typed endpoints, DTOs.
- `src/features/`, `src/pages/`, `src/components/` — feature-based organization.

### 2.7 Docker

`docker-compose.yml` orchestrates `db` (PostgreSQL 16) and `backend` (port 8000). The frontend service is currently commented out. Backend waits for database via `service_healthy`. OAuth credentials mounted from `./credentials/`.

### 2.8 Extensibility

- **New email provider**: follow the Core layer's `*_guide.md` (referenced from `general_core_rules.md`).
- **New identity provider**: follow the Auth layer's `*_guide.md` (referenced from `general_auth_rules.md`).
- **New API endpoint**: follow the API layer's `*_guide.md` (referenced from `general_api_rules.md`).

### 2.9 Document Maintenance

Update this section when: architecture layers change, new providers are introduced, commands change, or key identifiers are added. Do not modify Section 1 or the `general_*_rules.md` files.
