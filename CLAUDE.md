# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Section 1: General Architecture (do not modify)

This section describes the layered architecture, structural rules, and conventions that apply to any project following this pattern. It is project-agnostic and should not be modified for domain-specific changes.

### 1.1 Layer Rules (Auto-Loaded)

Each layer has its own `CLAUDE.md` that Claude Code loads automatically when reading files in that directory. These layer-level `CLAUDE.md` files are project-agnostic, transferable, and **must never be modified**. Each one references internally a `*_guide.md` with project-specific details.

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

### 1.2 Monorepo Structure

- `backend/` — API server organized in layers (FastAPI + Python).
- `frontend/` — Client application (React + Vite + TypeScript + Tailwind).
- Docker Compose orchestrates both services plus the database.

### 1.3 Excluded Directories

- `backend/Scripts/` — personal developer scripts (manual tests, one-off utilities). Claude must **not** read, edit, or reference files in this directory unless the user explicitly requests it. These scripts are unrelated to the application's business logic, is only to try manual executions.

### 1.4 Backend Layers and Relationships

```
→ API (routers → services → rest of the layers)
→ Auth       (identity verification, session management)
→ Database   (persistence)
→ Core       (domain logic, provider clients)
```

Communication rules:

- Only **Services** (inside API) talk to Auth, Database, and Core.
- Auth, Database, and Core are **independent** — none imports from another.
- No lower layer imports from API.

Each layer defines its own error hierarchy. Services translate lower-layer errors into API-layer errors. For specifics, consult the layer's `CLAUDE.md` (auto-loaded when reading files in that directory).

### 1.5 Two-Level Documentation Pattern

Each layer has two documentation files:

- `CLAUDE.md` (in each layer directory) — general, transferable rules. Not modified for project changes. Auto-loaded by Claude Code when reading files in that directory.
- `*_guide.md` — project-specific details. Claude updates these when the project changes.

The layer `CLAUDE.md` references its guide. This root `CLAUDE.md` lists the layers that have their own rules (§ 1.1).

### 1.6 Style and Code Quality

- Python: PEP 8, FastAPI conventions, `from __future__ import annotations` in all modules.
- TypeScript: ESLint config in `frontend/eslint.config.js`.
- Code language: English everywhere — identifiers, comments, docstrings, and all `.md` documentation files tracked by git.
- Comments only where they clarify non-obvious logic; avoid noise or redundancy.

### 1.7 Immutable Files

  All layer-level `CLAUDE.md` files (listed in § 1.1) are protected by a pre-edit
  hook that prevents any modification. Claude must never propose direct edits to
  these files. Instead, describe the suggested change — what, where, and why — so
  the developer can apply it manually.

  Project-specific changes always go in the corresponding `*_guide.md` file, which
  is not protected.
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

### 2.2 Request Flow

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



### 2.3 Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — optional human-readable label; defaults to `"{provider}:{account_id}"`.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).

### 2.4 Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/shared/email_fakes.py`. Cover service logic, auth settings, error translation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, isolate via `isolated_db` (transaction rollback). `require_session` overridden to return a fixed test user_id.
- Both test layers share `FakeEmailClient`, `build_metadata`, and database fakes (`FakeCursor`, `FakeConnection`) via `tests/shared/`.
- **E2E tests** (`backend/tests/e2e/`) — automated like unit and integration tests. They test all endpoints except interactive OAuth flows (`POST /auth/google`, `POST .../connect`) and `DELETE /auth/me` (cannot create a test user without the interactive login). Real third-party APIs and real DB persistence. Pre-configured test accounts are already inserted in the database with valid tokens and must never be deleted — E2E tests can be run without additional setup.

### 2.5 Frontend

Stack: React + Vite + TypeScript + Tailwind. Structure:

- `src/api/` — HTTP client, typed endpoints, DTOs.
- `src/features/`, `src/pages/`, `src/components/` — feature-based organization.

### 2.6 Docker

`docker-compose.yml` orchestrates `db` (PostgreSQL 16) and `backend` (port 8000). The frontend service is currently commented out. Backend waits for database via `service_healthy`. OAuth credentials mounted as a read-only volume; the host path is developer-specific (configured in docker-compose.yml).

### 2.7 Extensibility

- **New email provider**: follow the Core layer's `*_guide.md` (referenced from `backend/core/CLAUDE.md`).
- **New identity provider**: follow the Auth layer's `*_guide.md` (referenced from `backend/auth/CLAUDE.md`).
- **New API endpoint**: follow the API layer's `*_guide.md` (referenced from `backend/api/CLAUDE.md`).
Adding a new email provider or identity provider impacts multiple layers (Core, Database, API, Auth, Tests). Before starting, review the Extension / Checklist section in each affected layer's `*_guide.md` to understand the full scope of changes required.

### 2.8 Document Maintenance

Update this section when: architecture layers change, new providers are introduced, commands change, or key identifiers are added. Do not modify Section 1 or any layer-level `CLAUDE.md` files.

### 2.9 Provider-First Rule

For any operation that modifies email state both at the provider and in our database, always call the provider API first. Only update the DB for messages where the provider call succeeded. Never persist a state change locally if the provider rejected or failed the operation. This ensures our DB always reflects the real state of the user's mailbox at the provider. 
**Current exceptions:** The delete-email endpoint skips the real provider call for Gmail because the required `mail.google.com` scope is difficult to obtain. Deletion is performed only in the local database. This exception may be removed once the scope is available.
