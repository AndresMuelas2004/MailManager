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

## Architecture — STRICT, DO NOT VIOLATE

The layered architecture below is **mandatory**. Every change must preserve it. Never skip layers, never put business logic in routers, never import API exceptions from core, never instantiate provider clients outside of `build_manager_for_accounts()`.

### Request Flow

```
Routers (FastAPI)
  → Services (api/services/)
    → Storage (api/storage/)
    → Core (core/)
      → EmailManager (core/email/email_manager.py)
        → EmailClients (GmailClient, OutlookClient)
```
Only Services can talk with manager or Storage, and both cand comunicate only with Services or in the case of manager also it can comunicate with the clients. Important, storage can not comunicate with core.
### Layer Rules

- **Routers** (`api/routers/`) — thin HTTP surface. Zero business logic. Delegate everything to services.
- **Services** (`api/services/`) — orchestration, validation, error mapping. Always call `ensure_mailbox_exists(mailbox_id)` before any mailbox-scoped action. Build provider clients exclusively via `build_manager_for_accounts()` — never instantiate `EmailClient` subclasses directly in services or routers.
- **Storage** (`api/storage/`) — persistence abstraction (JSON files today, database later). The interfaces `MailboxStore` / `AccountStore` in `base.py` are stable contracts that future implementations must respect.
- **Core** (`core/email/`) — provider-specific logic, multi-account orchestration, and future AI features. `EmailManager` coordinates `EmailClient` instances (`GmailClient`, `OutlookClient`). Core knows nothing about the API layer.

### API / Service Conventions

- For any action scoped to a mailbox, call `ensure_mailbox_exists(mailbox_id)` first.
- Build provider clients with `build_manager_for_accounts()`; never instantiate `EmailClient` subclasses directly in services or routers.
- Only raise `ApiError` subclasses from services/routers; `api/errors/handlers.py` maps them to HTTP status codes.
- Schemas in `api/schemas/*` are the input/output contract for routers.
- Wrap secrets with the `load_wrapped_*` helpers; unwrap with `unwrap_secret()` before persisting.

### Error Hierarchy — Two Separate Trees

- **API layer** (`api/errors/exceptions.py`): `ApiError` base → `MailboxNotFound`, `AccountNotFound`, `AccountMisconfigured`, `StorageError`, etc. Mapped to HTTP status codes in `api/errors/handlers.py` via `_STATUS_MAP`. `ProviderNotSupported` has been removed — unknown providers are handled via `AccountMisconfigured` / `EmailProviderConfigError`.
- **Core layer** (`core/email/errors.py`): `CoreError` base → `EmailError` → `EmailAuthError`, `EmailAccountNotFoundError`, etc. Services catch these and re-raise as `ApiError` subclasses.

**Hard rules**: only raise `ApiError` subclasses from services/routers. Core must never import API exceptions. API must never raise `CoreError` directly to the client. Prefer explicit error handling with meaningful messages consistent with `ApiError` patterns.

### Email Core Flows and Authentication

- `EmailManager.add_account_record` — creates Gmail/Outlook clients from stored account records.
- **Interactive connection**: `EmailManager.connect_account` (used by `accounts_service.connect_account`).
- **Silent authentication**: `authenticate_all_silent` — can auto-refresh tokens without user interaction. Outlook may rotate refresh tokens on every refresh; both access and refresh tokens are always persisted.
- Both Gmail and Outlook are fully supported. See `backend/core/email/CLIENT_GUIDE.md` for detailed client implementation patterns and flows.

### Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` and token file names.
- `display_label` — optional human-readable label; defaults to `"{provider}:{account_id}"`.

### Storage Details

- Data files: `backend/data/mailboxes.json`, `backend/data/accounts.json` (gitignored).
- Token files live in `$MIA_TOKEN_PATH`:
  - Gmail: `gmail_token_{account_label}.json`
  - Outlook: `outlook_token_{account_label}.json`
- Token store functions (`load_account_tokens`, `save_account_tokens`, `load_app_credentials`) receive a `provider` parameter to dispatch path/env-var resolution.
- JSON store uses per-file threading locks and atomic write: `_write_list` writes content to a temporary file (`<name>.tmp`) first; only on success does it replace the real file. If the process is interrupted, the original file remains intact and the JSON is not corrupted.
- Before deleting mailboxes/accounts, call `delete_account_tokens_for_records()` for best-effort token cleanup.

### Environment Variables

- `MIA_GMAIL_CREDENTIALS_PATH` — path to Gmail OAuth client JSON (supports `installed` or `web` blocks).
- `MIA_OUTLOOK_CREDENTIALS_PATH` — path to Outlook app credentials JSON (flat dict with `client_id`, `client_secret`, `tenant`, `redirect_uri`, `scopes`, and optionally `provider`).
- `MIA_TOKEN_PATH` — shared directory for per-account token JSON files (both Gmail and Outlook).
- Missing any required env var must raise `EnvVarError`.

### Secrets Handling

Wrap secrets with `load_wrapped_app_credentials(provider)` / `load_wrapped_account_tokens(mailbox_id, account_id, provider)` (uses `pydantic.SecretStr`). Unwrap with `unwrap_secret()` before persisting.

### Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/unit/core/conftest.py`.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, and isolate JSON storage via `isolated_storage` autouse fixture that redirects to temp directories. Split into three files: `test_endpoints.py` (happy-path and behavioral), `test_api_layer_errors.py` (direct `raise ApiError` without core involvement), and `test_core_error_translation.py` (core errors escalated via `translate_core_error`). The `failing_test_client` fixture (indirect parametrize) injects failure kwargs into `FakeEmailClient` for core error translation tests.
- Both test layers share the `FakeEmailClient` and `build_message` helper via dynamic conftest loading.

### Frontend Structure

- `src/api/` — HTTP client (`client/http.ts`), typed endpoints (`endpoints/`), DTOs (`types/dto.ts`).
- `src/features/`, `src/pages/`, `src/components/` — feature-based React organization.
- CORS is configured to allow `http://localhost:5173`.

## Extensibility / TODO

- **New provider**: follow the step-by-step guide in `backend/core/email/CLIENT_GUIDE.md`. In short: implement `EmailClient`, add a branch in `EmailManager._build_client`, register the provider in `token_store._ENV_CREDENTIALS` and `_token_path_for_account`, and add the corresponding env var for app credentials.
- **Database migration**: replace JSON stores but preserve the `MailboxStore` / `AccountStore` contracts.

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

## Extras
Never toch the test called generalTest, this is only for me to comprobate the complete behavior of the backend with one execution, and in the future it will not exist.

## Workflow Rules
- **Never run tests automatically** after making code changes. Only run tests when explicitly requested by the user in a separate instruction.