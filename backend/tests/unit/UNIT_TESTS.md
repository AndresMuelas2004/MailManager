# Unit Tests (`backend/tests/unit`)

## Purpose

Unit tests validate the email core and API service/settings logic in isolation.
They do not require external services, browser interaction, or a database.

Primary target:

- `backend/core/email`
- `backend/database` (settings, token crypto, account repository token behavior)
- `backend/api/services` (auth service)
- `backend/auth` (auth settings)

## Test Principles

- Test one behavior per case.
- Keep tests deterministic and fast.
- Mock only external boundaries.
- Prefer pure function testing where possible.

## File Map

| File | Main Focus |
|---|---|
| `database/test_settings.py` | Env var parsing and validation for DB/token settings |
| `database/test_token_crypto.py` | Fernet encryption/decryption behavior and key validation |
| `database/test_account_repository.py` | Account repository CRUD + token dual-read fallback, lazy backfill, and context validation |
| `database/test_app_credentials.py` | App credential loading for Gmail/Outlook |
| `database/test_connection.py` | Connection pool creation and error handling |
| `database/test_lifecycle.py` | Database lifecycle warmup and migration errors |
| `database/test_mailbox_repository.py` | Mailbox repository CRUD operations |
| `database/test_session_repository.py` | Session repository CRUD operations |
| `database/test_user_repository.py` | User repository CRUD operations |
| `api/services/test_auth_service.py` | Auth service: validate_session, google_login, logout, get_current_user |
| `api/services/test_services_helpers.py` | `build_manager_for_accounts`, `catch_database_errors`, `ensure_mailbox_access` |
| `api/test_auth_settings.py` | Auth settings: GOOGLE_CLIENT_ID, session lifetime, cookie secure |
| `core/email/test_email_manager.py` | `EmailManager` lifecycle, account registration, routing, and error handling |
| `core/email/test_email_manager_extended.py` | Additional manager scenarios and edge-case behavior |
| `core/email/test_errors.py` | Core error hierarchy contracts (`code`, default messages, details) |
| `core/email/test_helpers.py` | Shared helper functions (`parse_expiry`, wrapping/unwrapping secrets) |
| `core/email/test_gmail_client.py` | Gmail client helper logic and guard clauses |
| `core/email/test_outlook_client.py` | Outlook helper logic, guards, and refresh path behavior |

## Shared Test Utilities

`tests/shared/email_fakes.py` provides reusable fakes for both unit and integration tests:

- `FakeEmailClient`
- `build_metadata(...)`

`tests/shared/database_fakes.py` provides database-level fakes:

- `FakeCursor` — records SQL executions, returns pre-configured results
- `FakeConnection` — returns pre-configured `FakeCursor` instances
- `patch_connection(monkeypatch, module, cursors)` — replaces `module.connection.get_connection` with a fake
- `patch_connection_error(monkeypatch, module, error)` — replaces `module.connection.get_connection` with one that raises immediately

These keep provider-independent tests simple and stable.

## Mocking Strategy

Used where external boundaries exist:

- Token endpoint and Graph request boundaries in Outlook client tests
- OAuth/network related boundaries in provider client tests
- Client orchestration behavior via fake clients in manager tests
- Database stores (UserStore, SessionStore) in auth service tests
- Google OIDC token verification in auth service tests

Pure helpers are tested directly without mocking.

## What Is Not Unit-Tested

- Real OAuth browser flows
- Real Gmail or Microsoft Graph API calls
- Real token persistence in PostgreSQL
- API router/service wiring (covered by integration tests)

Those behaviors are covered in integration and E2E suites.

## Running Unit Tests

```bash
# All unit tests
python -m pytest backend/tests/unit -v

# Only core email unit tests
python -m pytest backend/tests/unit/core/email -v

# Auth service unit tests
python -m pytest backend/tests/unit/api/services/test_auth_service.py -v

# Auth settings unit tests
python -m pytest backend/tests/unit/api/test_auth_settings.py -v

# Single file
python -m pytest backend/tests/unit/core/email/test_helpers.py -v

# Filter by test name
python -m pytest backend/tests/unit -k "parse_expiry"
```

## Naming and Organization

- File naming: `test_<module>.py`
- Test function naming: `test_<behavior>_<scenario>`
- Group related cases in classes when it improves readability
- Keep fixtures in `conftest.py` focused and composable
