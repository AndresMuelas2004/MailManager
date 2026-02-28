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
    → Auth layer (auth/)      — Google OIDC verification, auth settings
    → Database (database/)    — PostgreSQL persistence (independent layer)
    → Core (core/)
      → EmailManager (core/email/email_manager.py)
        → EmailClients (GmailClient, OutlookClient)
```

Only Services can talk with manager, Database, or Auth. `core/`, `database/`, and `auth/` are three symmetric, framework-agnostic layers under `backend/` — none of them import from `api/`. Database cannot communicate with core.

### Layer Rules

- **Routers** (`api/routers/`) — thin HTTP surface. Zero business logic. Each endpoint declares Pydantic schemas and contains a single service call. Cookie management is handled by the service layer. See `backend/api/API_GUIDE.md` § 4.
- **Router helpers** (`api/routers/routers_helpers.py`) — shared `Depends` callables. `require_session` validates the session cookie and returns `user_id`. All routes use it except `/health`, `/auth/google`, and `/auth/logout`.
- **Services** (`api/services/`) — orchestration, validation, error mapping. Always call `ensure_mailbox_access(mailbox_id, user_id)` before any mailbox-scoped action. Build provider clients exclusively via `build_manager_for_accounts()`. See `backend/api/API_GUIDE.md` § 5–7.
- **Auth** (`auth/`) — framework-agnostic authentication layer. Uses `AuthError` hierarchy. No imports from `api/`. See `backend/auth/AUTH_GUIDE.md`.
- **Database** (`database/`) — framework-agnostic PostgreSQL persistence layer. Uses `DatabaseError` hierarchy. No imports from `api/`. See `backend/database/DATABASE.md`.
- **Core** (`core/email/`) — provider-specific logic, multi-account orchestration. Uses `CoreError` hierarchy. No imports from `api/`. See `backend/core/email/CLIENT_GUIDE.md`.

### Layer Documentation

| Layer | Guide | Key sections |
|---|---|---|
| API | `backend/api/API_GUIDE.md` | Endpoints, service conventions, error hierarchy, capture technique, translation maps |
| Auth | `backend/auth/AUTH_GUIDE.md` | Error hierarchy, capture technique, Google OIDC, provider extension |
| Database | `backend/database/DATABASE.md` | Error hierarchy, capture technique, contracts, migrations, token security |
| Core | `backend/core/email/CLIENT_GUIDE.md` | Client contract, error hierarchy, capture technique, provider extension |

### Error Hierarchy — Four Separate Trees

Each layer defines its own error hierarchy. Services translate lower-layer errors to `ApiError` subclasses via mapping tables in `services_helpers.py`:

- **API** (`api/errors/exceptions.py`): `ApiError` → HTTP-facing errors. Mapped to status codes via `_STATUS_MAP`. Full table in `API_GUIDE.md` § 6.
- **Auth** (`auth/errors/errors.py`): `AuthError` → `AuthSettingsError`, `AuthTokenError` subtree. Translated via `_AUTH_TO_API_MAP`. Full table in `AUTH_GUIDE.md` § 4.
- **Database** (`database/errors/exceptions.py`): `DatabaseError` → `ConnectionPoolError`, `QueryError`, etc. Translated via `_DB_TO_API_MAP` / `catch_database_errors`. Full table in `DATABASE.md` § Error Handling.
- **Core** (`core/email/errors.py`): `CoreError` → `EmailError` subtree. Translated via `_CORE_TO_API_MAP`. Full table in `CLIENT_GUIDE.md` § 7.

**Hard rules**: only raise `ApiError` subclasses from `api/services/` — never from routers, `database/`, `auth/`, or `core/`. Core must never import API, auth, or database exceptions. Database must never import API, auth, or core exceptions. Auth must never import API, database, or core exceptions. API must never raise `CoreError`, `AuthError`, or `DatabaseError` directly to the client. Every `try` block in services must include an `except Exception` fallback — see `API_GUIDE.md` § 7 for the full capture technique. Pydantic 422 validation errors are framework-managed.

### Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — optional human-readable label; defaults to `"{provider}:{account_id}"`.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).

### Environment Variables

| Var | Layer | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | database | *(required)* | PostgreSQL connection string |
| `GOOGLE_CLIENT_ID` | auth | *(required)* | Google OAuth client ID for OIDC |
| `AUTH_SESSION_LIFETIME_DAYS` | auth | `7` | Session duration in days |
| `AUTH_COOKIE_SECURE` | auth | `false` | HTTPS-only session cookies |
| `MIA_GMAIL_CREDENTIALS_PATH` | database | *(required)* | Path to Gmail OAuth client JSON |
| `MIA_OUTLOOK_CREDENTIALS_PATH` | database | *(required)* | Path to Outlook app credentials JSON |
| `CORS_ALLOWED_ORIGINS` | api | `http://localhost:5173` | Comma-separated CORS origins |
| `VITE_API_BASE_URL` | frontend | `http://localhost:8000` | Backend URL for frontend |

Missing required env vars must raise `EnvVarError` (api), `SettingsError` (database → translated to `EnvVarError`), or `AuthSettingsError` (auth → translated to `EnvVarError`). The backend loads `backend/.env` via `python-dotenv` (`override=False`). See `DATABASE.md` § Operational Env Vars for database-specific tuning and encryption vars.

### Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/shared/email_fakes.py`. Cover service logic, auth settings, error translation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, isolate via `isolated_db` (transaction rollback). `require_session` overridden to return a fixed test user_id. Split across `test_endpoints.py`, `test_api_layer_errors.py`, `test_core_error_translation.py`, `test_auth_endpoints.py`.
- Both test layers share `FakeEmailClient` and `build_message` via `tests/shared/`.
- **E2E tests** — NEVER run E2E tests. They require manual execution by the developer.

### Frontend Structure

- `src/api/` — HTTP client, typed endpoints, DTOs.
- `src/features/`, `src/pages/`, `src/components/` — feature-based React organization.

### Docker

- `docker-compose.yml` — orchestrates `db` (PostgreSQL 16), `backend` (port 8000), `frontend` (port 5173). Backend waits for database via `service_healthy`. OAuth credentials mounted from `./credentials/`.

## Extensibility

- **New email provider**: follow `backend/core/email/CLIENT_GUIDE.md` § 9.
- **New identity provider**: follow `backend/auth/AUTH_GUIDE.md` § 9.
- **New API endpoint**: follow `backend/api/API_GUIDE.md` § 10.

## Style and Code Quality — STRICT

Code must meet a **senior-level standard**: clear, efficient, and readable.

- Python: PEP 8, FastAPI conventions, `from __future__ import annotations` in all modules.
- TypeScript: ESLint config in `frontend/eslint.config.js`.
- Identifiers, comments, and docstrings in English.
- Comments only where they clarify non-obvious logic; avoid noise or redundancy.
- Explicit error handling with meaningful messages consistent with each layer's error patterns.
- Preserve the naming conventions and layered architecture described above at all times.

## Document Maintenance

Update this file when architecture layers change, environment variables are added, new providers are introduced, or error mapping changes. Detailed per-layer documentation lives in the layer guides referenced in the Layer Documentation table above.
