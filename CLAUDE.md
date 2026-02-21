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
  → Services (api/services/)
    → Database (api/database/)
    → Core (core/)
      → EmailManager (core/email/email_manager.py)
        → EmailClients (GmailClient, OutlookClient)
```
Only Services can talk with manager or Database, and both can communicate only with Services or in the case of manager also it can communicate with the clients. Important, database can not communicate with core.
### Layer Rules

- **Routers** (`api/routers/`) — thin HTTP surface. Zero business logic. Delegate everything to services.
- **Services** (`api/services/`) — orchestration, validation, error mapping. Always call `ensure_mailbox_exists(mailbox_id)` before any mailbox-scoped action. Build provider clients exclusively via `build_manager_for_accounts()` — never instantiate `EmailClient` subclasses directly in services or routers.
- **Database** (`api/database/`) — PostgreSQL persistence layer. The interfaces `MailboxStore` / `AccountStore` in `contracts.py` are stable contracts. `repositories/` implements them with SQL queries from `queries/`. `security/token_store.py` handles account tokens in the `tokens` table and `security/app_credentials.py` loads provider app credentials from file-based env vars. All public symbols are re-exported from the package `__init__.py` so consumers import from `api.database`. See `backend/api/database/DATABASE.md` for a detailed description of each file.
- **Core** (`core/email/`) — provider-specific logic, multi-account orchestration, and future AI features. `EmailManager` coordinates `EmailClient` instances (`GmailClient`, `OutlookClient`). Core knows nothing about the API layer.

### API / Service Conventions

- For any action scoped to a mailbox, call `ensure_mailbox_exists(mailbox_id)` first.
- Build provider clients with `build_manager_for_accounts()`; never instantiate `EmailClient` subclasses directly in services or routers.
- Only raise `ApiError` subclasses from services/routers; `api/errors/handlers.py` maps them to HTTP status codes.
- Schemas in `api/schemas/*` are the input/output contract for routers.
- Wrap secrets with the `load_wrapped_*` helpers; unwrap with `unwrap_secret()` before persisting.

### Error Hierarchy — Two Separate Trees

- **API layer** (`api/errors/exceptions.py`): `ApiError` base → `MailboxNotFound`, `AccountNotFound`, `AccountMisconfigured`, `DatabaseError`, etc. Mapped to HTTP status codes in `api/errors/handlers.py` via `_STATUS_MAP`. Unknown providers are handled via `AccountMisconfigured` / `EmailProviderConfigError`.
- **Core layer** (`core/email/errors.py`): `CoreError` base → `EmailError` → `EmailAuthError`, `EmailAccountNotFoundError`, etc. Services catch these and re-raise as `ApiError` subclasses.

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

### Database Details

- Persistence uses PostgreSQL via `psycopg2`. Connection pool is managed in `api/database/connection.py` with lazy initialisation; `warmup_connection()` is called at application startup via FastAPI lifespan.
- Tables: `mailboxes`, `accounts`, `tokens` — defined in `api/database/schema.sql` (DDL is idempotent with `CREATE TABLE IF NOT EXISTS`).
- Foreign keys use `ON DELETE CASCADE`: deleting a mailbox automatically removes its accounts and their tokens.
- `created_at` timestamps are generated by PostgreSQL (`DEFAULT now()`), not by Python code.
- Token store functions (`load_account_tokens`, `save_account_tokens`) store tokens in the `tokens` table. `load_app_credentials` still reads from file-based env var paths.
- `delete_account_tokens_for_records()` deletes from the `tokens` table; also handled implicitly by CASCADE when deleting accounts or mailboxes.

### Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (`postgresql://user:password@host:port/dbname`).
- `MIA_GMAIL_CREDENTIALS_PATH` — path to Gmail OAuth client JSON (supports `installed` or `web` blocks).
- `MIA_OUTLOOK_CREDENTIALS_PATH` — path to Outlook app credentials JSON (flat dict with `client_id`, `client_secret`, `tenant`, `redirect_uri`, `scopes`, and optionally `provider`).
- `VITE_API_BASE_URL` — (frontend, optional) overrides the default backend URL (`http://localhost:8000`).
- Missing any required env var must raise `EnvVarError`.
- The backend loads `backend/.env` via `python-dotenv` (`override=False`) so OS/Docker env vars take precedence. Template: `backend/.env.example`. Frontend template: `frontend/.env.example`.

### Secrets Handling

Wrap secrets with `load_wrapped_app_credentials(provider)` / `load_wrapped_account_tokens(mailbox_id, account_id, provider)` (uses `pydantic.SecretStr`). Unwrap with `unwrap_secret()` before persisting to the database.

### Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/unit/core/conftest.py`.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, and isolate database writes via `isolated_db` autouse fixture that wraps each test in a PostgreSQL transaction rolled back at teardown. Split into three files: `test_endpoints.py` (happy-path and behavioral), `test_api_layer_errors.py` (direct `raise ApiError` without core involvement), and `test_core_error_translation.py` (core errors escalated via `translate_core_error`). The `failing_test_client` fixture (indirect parametrize) injects failure kwargs into `FakeEmailClient` for core error translation tests.
- Both test layers share the `FakeEmailClient` and `build_message` helper via dynamic conftest loading.

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

- **New provider**: follow the step-by-step guide in `backend/core/email/CLIENT_GUIDE.md`. In short: implement `EmailClient`, add a branch in `EmailManager._build_client`, register the provider in `token_store._ENV_CREDENTIALS`, update the `provider` CHECK constraint in `schema.sql`, and add the corresponding env var for app credentials.

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
