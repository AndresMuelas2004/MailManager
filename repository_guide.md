# Repository Guide — Project-Specific (maintained by Claude)

This file contains details specific to MailManager. Update it when the project changes (new providers, new endpoints, architectural shifts). Do not modify any `CLAUDE.md` file.

## Project Overview

**MailManager** is a multi-account email management application.

- **Backend**: FastAPI (Python).
- **Frontend**: React + Vite + TypeScript + Tailwind.
- **Email providers**: Gmail and Outlook (both fully implemented).
- **Authentication**: Google OIDC.
- **Database**: PostgreSQL with Alembic migrations.

## Request Flow

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

## Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — optional human-readable label; defaults to `"{provider}:{account_id}"`.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).

## Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/shared/email_fakes.py`. Cover service logic, auth settings, error translation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, isolate via `isolated_db` (transaction rollback). `require_session` overridden to return a fixed test user_id.
- Both test layers share `FakeEmailClient`, `build_metadata`, and database fakes (`FakeCursor`, `FakeConnection`) via `tests/shared/`.
- **E2E tests** (`backend/tests/e2e/`) — automated like unit and integration tests. They test all endpoints except interactive OAuth flows (`POST /auth/google`, `POST .../connect`) and `DELETE /auth/me` (cannot create a test user without the interactive login). Real third-party APIs and real DB persistence. Pre-configured test accounts are already inserted in the database with valid tokens and must never be deleted — E2E tests can be run without additional setup.

## Frontend

Stack: React + Vite + TypeScript + Tailwind. Structure:

- `src/api/` — HTTP client, typed endpoints, DTOs.
- `src/features/`, `src/pages/`, `src/components/` — feature-based organization.

## Docker

`docker-compose.yml` orchestrates `db` (PostgreSQL 16) and `backend` (port 8000). The frontend service is currently commented out. Backend waits for database via `service_healthy`. OAuth credentials mounted as a read-only volume; the host path is developer-specific (configured in docker-compose.yml).

## Extensibility

- **New email provider**: follow the Core layer's `*_guide.md` (referenced from `backend/core/CLAUDE.md`).
- **New identity provider**: follow the Auth layer's `*_guide.md` (referenced from `backend/auth/CLAUDE.md`).
- **New API endpoint**: follow the API layer's `*_guide.md` (referenced from `backend/api/CLAUDE.md`).
Adding a new email provider or identity provider impacts multiple layers (Core, Database, API, Auth, Tests). Before starting, review the Extension / Checklist section in each affected layer's `*_guide.md` to understand the full scope of changes required.

## Provider-First Rule

For any operation that modifies email state both at the provider and in our database, always call the provider API first. Only update the DB for messages where the provider call succeeded. Never persist a state change locally if the provider rejected or failed the operation. This ensures our DB always reflects the real state of the user's mailbox at the provider.
**Current exceptions:** The delete-email endpoint skips the real provider call for Gmail because the required `mail.google.com` scope is difficult to obtain. Deletion is performed only in the local database. This exception may be removed once the scope is available.

## Document Maintenance

Update this file when: architecture layers change, new providers are introduced, commands change, or key identifiers are added. Do not modify any `CLAUDE.md` file.
