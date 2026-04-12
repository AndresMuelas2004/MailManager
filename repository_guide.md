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

Note: the `GET /mailboxes/{mailbox_id}/emails` listing endpoint reads only from the local database (Services → Database, no provider API calls).
Note: the `GET /mailboxes/{mailbox_id}/emails/{id}/content` endpoint uses a cache-aside pattern — first verifies the email exists in `email_metadata` (404 `email_not_found` otherwise), then checks the `email_content` table, and on cache miss fetches from the provider API, sanitizes the HTML, persists in DB, then returns. Content rows are tied to metadata via a composite foreign key `email_content.(provider_message_id, account_id) → email_metadata.(provider_message_id, account_id) ON DELETE CASCADE`, so metadata deletes and account deletes transitively cascade into content (migration 0013).
Note: the `POST /mailboxes/{mailbox_id}/accounts/{account_id}/drafts` endpoint follows the Provider-First Rule — the draft is created at the provider first (Gmail `drafts.create` or Outlook `POST /me/messages` with `Prefer: IdType="ImmutableId"`), and only on success persisted to the local `drafts` table.
Note: the `PATCH /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{provider_draft_id}` endpoint also follows the Provider-First Rule with a pre-check — `ensure_mailbox_access` → account lookup → `draft_store.get` (404 `draft_not_found` if the draft is not in the local DB, without wasting a provider round trip) → silent auth → provider update (Gmail `users().drafts().update()` or Outlook `PATCH /me/messages/{id}` with `Prefer: IdType="ImmutableId"` repeated because the stored ID is an Immutable ID) → only on success, `draft_store.update` persists the new recipients/subject/body and refreshes `updated_at`. The local `created_at` is preserved across updates.
Note: the `GET /mailboxes/{mailbox_id}/drafts` listing endpoint reads only from the local database (Services → Database, no provider API calls). Query param `account_id` is optional: when provided, returns drafts of that account; when omitted, returns the unified view across all accounts in the mailbox.
Note: the `POST /mailboxes/{mailbox_id}/drafts/sync` endpoint fetches drafts from the provider(s) and replaces the local rows for each synced account atomically (UPSERT + delete-missing). Query param `account_id` is optional: when provided, syncs only that account; when omitted, syncs every account in the mailbox. Both providers cap the fetch at `_DRAFTS_MAX_TOTAL = 100` drafts per account (most recent). Gmail uses the existing parallel-batch-of-100 skeleton (5 workers × 4 retries); Outlook paginates with `$top=100` + `$orderby=lastModifiedDateTime desc` + 4 retries per page.

## Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — required on account creation (`min_length=1`, `NOT NULL`); the service layer falls back to `"{provider}:{account_id}"` when rendering responses for legacy records.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).
- `email_address` — the email address of the connected account, fetched best-effort from the provider during `connect_account`. Stored as plain text (not encrypted) in the `accounts` table. May be `NULL` if the fetch failed.
- `provider_draft_id` — the draft identifier returned by the provider (Gmail `drafts.create` or Outlook `POST /me/messages` with `Prefer: IdType="ImmutableId"`). Together with `account_id`, forms the composite PK of the `drafts` table.

## Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/shared/email_fakes.py`. Cover service logic, auth settings, error translation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, isolate via `isolated_db` (transaction rollback). `require_session` overridden to return a fixed test user_id.
- Both test layers share `FakeEmailClient`, `build_metadata`, and database fakes (`FakeCursor`, `FakeConnection`) via `tests/shared/`.
- **E2E tests** (`backend/tests/e2e/`) — automated like unit and integration tests. They test all endpoints except interactive OAuth flows (`POST /auth/google`, `POST .../connect`) and `DELETE /auth/me` (cannot create a test user without the interactive login). Real third-party APIs and real DB persistence. Pre-configured test accounts are already inserted in the database with valid tokens and must never be deleted — E2E tests can be run without additional setup.

## Frontend

Stack: React + Vite + TypeScript + Tailwind. Structure:

- `src/api/` — HTTP client (`client/`), typed endpoints (`endpoints/`), DTOs (`types/`).
- `src/app/` — Layout, providers, routing.
- `src/pages/` — Page components.
- `src/lib/` — Shared constants and utilities.
- `src/styles/` — Global CSS.
- `src/features/`, `src/components/` — scaffolded (empty).

## Docker

`docker-compose.yml` orchestrates `db` (PostgreSQL 16) and `backend` (port 8000). The frontend service is currently commented out. Backend waits for database via `service_healthy`. OAuth credentials mounted as a read-only volume; the host path is developer-specific (configured in docker-compose.yml).

## Extensibility

- **New email provider**: follow the Core layer's `*_guide.md` (referenced from `backend/core/CLAUDE.md`).
- **New identity provider**: follow the Auth layer's `*_guide.md` (referenced from `backend/auth/CLAUDE.md`).
- **New API endpoint**: follow the API layer's `*_guide.md` (referenced from `backend/api/CLAUDE.md`).
Adding a new email provider or identity provider impacts multiple layers (Core, Database, API, Auth, Tests). Before starting, review the Extension / Checklist section in each affected layer's `*_guide.md` to understand the full scope of changes required.

## Provider-First Rule

For any operation that modifies email state both at the provider and in our database, always call the provider API first. Only update the DB for messages where the provider call succeeded. Never persist a state change locally if the provider rejected or failed the operation. This ensures our DB always reflects the real state of the user's mailbox at the provider.
**Current exceptions:** Both providers (Gmail and Outlook) use a uniform no-op approach for `delete_messages` -- the provider API is not called and deletion is performed only in the local database. See `core_guide.md` (Trash Management Operations > `delete_messages`) for the detailed rationale.

## Document Maintenance

Update this file when: architecture layers change, new providers are introduced, commands change, or key identifiers are added. Do not modify any `CLAUDE.md` file.
