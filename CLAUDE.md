# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. **Read this document in full before writing or reviewing any code.**

## Project Overview

MailManager is a multi-account email management application with a FastAPI backend and a React (Vite + TypeScript + Tailwind) frontend. It supports **Gmail** and **Outlook** (both fully implemented). The project language for code (identifiers, docstrings, comments) is English. The scope of this document covers the backend FastAPI and `core/email`; the frontend is only mentioned when it affects backend contracts.

## Commands

### Backend

```bash
# Run the API server (from backend/)
python main.py                       # starts uvicorn on 0.0.0.0:8000

# Run all tests (from project root, with .venv activated)
python -m pytest backend/tests

# Run only unit tests
python -m pytest backend/tests/unit

# Run only integration tests
python -m pytest backend/tests/integration

# Run a single test file
python -m pytest backend/tests/unit/core/email/test_email_manager.py

# Run a single test by name
python -m pytest backend/tests -k "test_name"
```

### Frontend

```bash
cd frontend
npm run dev          # Vite dev server (port 5173)
npm run build        # TypeScript check + Vite production build
npm run lint         # ESLint
```

### Docker

```bash
docker compose up --build       # build and start all services
docker compose down             # stop all services
docker compose down -v          # stop and delete database volume
```

## Architecture — STRICT, DO NOT VIOLATE

The layered architecture below is **mandatory**. Every change must preserve it. Never skip layers, never put business logic in routers, never import API exceptions from core, never instantiate provider clients outside of `build_manager_for_accounts()`.

### Request Flow

```
Routers (FastAPI)
  → Routers helpers (api/routers/routers_helpers.py)  — e.g. require_session → user_id
  → Services (api/services/)
    → Auth layer (auth/)  — Google OIDC verification, auth settings
    → Database (api/database/)
    → Core (core/)
      → EmailManager (core/email/email_manager.py)
        → EmailClients (GmailClient, OutlookClient)
```
Only Services can talk with manager, Database, or Auth. Auth (`auth/`) is a framework-agnostic layer parallel to `core/email/` — it has no imports from `api/`. Database cannot communicate with core.

### Layer Rules

- **Routers** (`api/routers/`) — thin HTTP surface. Zero business logic. Routers only know schemas (`api/schemas/`), services (`api/services/`), and router helpers (`api/routers/routers_helpers.py`). Each endpoint declares its Pydantic request/response schemas and contains a single call to a service function — nothing else. Cookie management is handled by the service layer (routers pass `Response` to service functions that need it).
- **Router helpers** (`api/routers/routers_helpers.py`) — shared FastAPI `Depends` callables used across all routers. `require_session` validates the session cookie via `auth_service` and returns `user_id`. All routes use `Depends(require_session)` except `/health` and the auth endpoints (`/auth/google`, `/auth/logout`) which handle session management directly.
- **Services** (`api/services/`) — orchestration, validation, error mapping. Always call `ensure_mailbox_access(mailbox_id, user_id)` before any mailbox-scoped action. Build provider clients exclusively via `build_manager_for_accounts()` — never instantiate `EmailClient` subclasses directly in services or routers. `auth_service` handles Google OIDC login (delegating token verification to `auth/`), session/cookie management, and user lookup.
- **Auth** (`auth/`) — framework-agnostic authentication layer, parallel to `core/email/`. Contains `auth/settings.py` (auth environment settings, raises `ValueError`) and `auth/google_auth/google.py` (`verify_google_token` — pure Google OIDC verification). This layer has **no imports from `api/`**. Services catch `ValueError` from auth and re-raise as `EnvVarError` or `Unauthorized`.
- **Database** (`api/database/`) — PostgreSQL persistence layer. The interfaces `MailboxStore` / `AccountStore` / `UserStore` / `SessionStore` in `contracts.py` are stable contracts. `repositories/` implements them with SQL queries from `queries/`. `security/app_credentials.py` loads provider app credentials from file-based env vars and `security/token_crypto.py` provides Fernet encrypt/decrypt utilities. All public symbols are re-exported from the package `__init__.py` so consumers import from `api.database`. See `backend/api/database/DATABASE.md` for a detailed description of each file.
- **Core** (`core/email/`) — provider-specific logic, multi-account orchestration, and future AI features. `EmailManager` coordinates `EmailClient` instances (`GmailClient`, `OutlookClient`). Core knows nothing about the API layer.

### Authentication

- **Google OIDC**: Users authenticate via `POST /auth/google` with a Google `id_token`. The service calls `auth.google_auth.google.verify_google_token` (which uses `google.oauth2.id_token.verify_oauth2_token`), upserts a `users` record, creates a server-side `sessions` record, sets the HttpOnly `session_id` cookie on the `Response`, and returns the user dict.
- **Session validation**: `require_session` (in `api/routers/routers_helpers.py`) reads the `session_id` cookie, validates it against the `sessions` table via `auth_service`, and returns the `user_id`.
- **Ownership**: Each mailbox has an `owner_user_id` (NOT NULL). `ensure_mailbox_access` checks ownership — only the owning user can access a mailbox.
- **Auth endpoints**: `POST /auth/google` (login), `GET /auth/me` (current user), `POST /auth/logout` (delete session + clear cookie), `DELETE /auth/me` (delete user account + cascade all data). Login and logout do not use `require_session` — login cannot require a prior session, and logout must work even with expired sessions. `DELETE /auth/me` uses `require_session` and calls `auth_service.delete_account` which deletes the user row; CASCADE removes all associated mailboxes, accounts, and sessions. `GET /health` also requires no authentication.

### API / Service Conventions

- For any action scoped to a mailbox, call `ensure_mailbox_access(mailbox_id, user_id)` first.
- Build provider clients with `build_manager_for_accounts()`; never instantiate `EmailClient` subclasses directly in services or routers.
- Only raise `ApiError` subclasses from services/routers; `api/errors/handlers.py` maps them to HTTP status codes.
- Schemas in `api/schemas/*` are the input/output contract for routers.
- Wrap secrets with the `load_wrapped_*` helpers; unwrap with `unwrap_secret()` before persisting.

### Error Hierarchy — Two Separate Trees

- **API layer** (`api/errors/exceptions.py`): `ApiError` base → `MailboxNotFound`, `AccountNotFound`, `UserNotFound`, `AccountMisconfigured`, `Unauthorized`, `Forbidden`, `DatabaseConnectionError`, `DatabaseQueryError`, `DatabaseMigrationError`, `TokenDecryptionError`, `TokenIntegrityError`, `CredentialFileError`, etc. Mapped to HTTP status codes in `api/errors/handlers.py` via `_STATUS_MAP`. Unknown providers are handled via `AccountMisconfigured` / `EmailProviderConfigError`. See `backend/api/database/DATABASE.md` § Error Handling for the full database exception table, capture technique, and per-module mapping.
- **Core layer** (`core/email/errors.py`): `CoreError` base → `EmailError` → `EmailAuthError`, `EmailAccountNotFoundError`, etc. Services catch these and re-raise as `ApiError` subclasses. See `backend/core/email/CLIENT_GUIDE.md` § 7 for the full core error table, capture technique, and provider-specific patterns.

**Hard rules**: only raise `ApiError` subclasses explicitly from `api/database/` and `api/services/` — never from routers, which must stay logic-free. Core must never import API exceptions. API must never raise `CoreError` directly to the client. Prefer explicit error handling with meaningful messages consistent with `ApiError` patterns. (FastAPI's request validation errors — HTTP 422 — are raised automatically by Pydantic schema parsing and are framework-managed; no explicit raise is needed or expected for them.)

### Email Core Flows and Authentication

- `EmailManager.add_account_record` — creates Gmail/Outlook clients from stored account records.
- **Interactive connection**: `EmailManager.connect_account` (used by `accounts_service.connect_account`).
- **Silent authentication**: `authenticate_all_silent` — can auto-refresh tokens without user interaction. Outlook may rotate refresh tokens on every refresh; both access and refresh tokens are always persisted.
- Both Gmail and Outlook are fully supported. See `backend/core/email/CLIENT_GUIDE.md` for detailed client implementation patterns and flows.

### Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — optional human-readable label; defaults to `"{provider}:{account_id}"`.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).

### Database Details

- Persistence uses PostgreSQL via `psycopg2`. Connection pool is managed in `api/database/connection.py` with lazy initialisation; `warmup_connection()` is called at application startup via FastAPI lifespan.
- Tables: `users`, `mailboxes`, `accounts`, `sessions` — defined in `api/database/schema.sql` (DDL is idempotent with `CREATE TABLE IF NOT EXISTS`). Token columns live directly in the `accounts` table.
- Foreign keys use `ON DELETE CASCADE`: deleting a user cascades to their mailboxes → accounts; deleting a user also cascades to their sessions.
- `created_at` timestamps are generated by PostgreSQL (`DEFAULT now()`), not by Python code.
- `account_store` (`PgAccountStore`) handles account CRUD and token persistence via `get_tokens()` and `upsert_tokens()`. `load_app_credentials` reads provider app credentials from file-based env var paths.

### Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (`postgresql://user:password@host:port/dbname`).
- `GOOGLE_CLIENT_ID` — Google OAuth client ID for OIDC token verification (required for auth).
- `AUTH_SESSION_LIFETIME_DAYS` — session duration in days (default `7`).
- `AUTH_COOKIE_SECURE` — set `true` for HTTPS-only session cookies (default `false`).
- `MIA_GMAIL_CREDENTIALS_PATH` — path to Gmail OAuth client JSON (supports `installed` or `web` blocks).
- `MIA_OUTLOOK_CREDENTIALS_PATH` — path to Outlook app credentials JSON (flat dict with `client_id`, `client_secret`, `tenant`, `redirect_uri`, `scopes`, and optionally `provider`).
- `VITE_API_BASE_URL` — (frontend, optional) overrides the default backend URL (`http://localhost:8000`).
- Missing any required env var must raise `EnvVarError` (in `api/`) or `ValueError` (in `auth/`; services translate to `EnvVarError`). Auth-related env vars (`GOOGLE_CLIENT_ID`, `AUTH_SESSION_LIFETIME_DAYS`, `AUTH_COOKIE_SECURE`) are read by `auth/settings.py`.
- The backend loads `backend/.env` via `python-dotenv` (`override=False`) so OS/Docker env vars take precedence. Template: `backend/.env.example`. Frontend template: `frontend/.env.example`.

### Secrets Handling

Wrap secrets with `load_wrapped_app_credentials(provider)` / `load_wrapped_account_tokens(mailbox_id, account_id, provider)` (uses `pydantic.SecretStr`). Unwrap with `unwrap_secret()` before persisting to the database.

### Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/unit/core/conftest.py`. Includes `test_auth_service.py` for auth service logic and `test_auth_settings.py` for auth settings validation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, and isolate database writes via `isolated_db` autouse fixture that wraps each test in a PostgreSQL transaction rolled back at teardown. The `require_session` dependency is overridden via `app.dependency_overrides` to return a fixed test user_id. Split into four files: `test_endpoints.py` (happy-path and behavioral), `test_api_layer_errors.py` (direct `raise ApiError` without core involvement), `test_core_error_translation.py` (core errors escalated via `translate_core_error`), and `test_auth_endpoints.py` (auth login/logout, ownership, and session validation). The `failing_test_client` fixture (indirect parametrize) injects failure kwargs into `FakeEmailClient` for core error translation tests.
- Both test layers share the `FakeEmailClient` and `build_message` helper via dynamic conftest loading.
- **E2E tests** — NEVER run E2E tests. They require manual execution by the developer and must not be triggered by the AI under any circumstances.

### Frontend Structure

- `src/api/` — HTTP client (`client/http.ts`), typed endpoints (`endpoints/`), DTOs (`types/dto.ts`).
- `src/features/`, `src/pages/`, `src/components/` — feature-based React organization.
- CORS is configured to allow `http://localhost:5173`.

### Docker

- `Dockerfile` (root) — backend image (Python 3.12-slim).
- `frontend/Dockerfile` — multi-stage frontend image (Node build + nginx).
- `frontend/nginx.conf` — SPA routing for nginx.
- `docker-compose.yml` — orchestrates `db` (PostgreSQL 16), `backend` (port 8000), and `frontend` (port 5173). Backend waits for database via `service_healthy`. Database volume `pgdata` persists data across restarts.
- OAuth credential files are mounted from `./credentials/` into the backend container.

## Extensibility / TODO

- **New provider**: follow the step-by-step guide in `backend/core/email/CLIENT_GUIDE.md`. In short: implement `EmailClient`, add a branch in `EmailManager._build_client`, register the provider env var in `settings._PROVIDER_CREDENTIALS_ENV_VARS`, update the `provider` CHECK constraint in `schema.sql`, and add the corresponding env var for app credentials.

## Style and Code Quality — STRICT

Code must meet a **senior-level standard**: clear, efficient, and readable.

- Python: PEP 8, FastAPI conventions, `from __future__ import annotations` in all modules.
- TypeScript: ESLint config in `frontend/eslint.config.js`.
- Identifiers, comments, and docstrings in English.
- Comments only where they clarify non-obvious logic; avoid noise or redundancy.
- Explicit error handling with meaningful messages consistent with `ApiError` patterns.
- Preserve the naming conventions and layered architecture described above at all times.

## Document Maintenance

Update this file when architecture layers change, environment variables are added, new providers are introduced, error mapping changes, or the persistence strategy evolves. If this document grows too large, move detailed subsections to `docs/` and keep this as an index.
