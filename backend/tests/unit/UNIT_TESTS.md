# Unit Tests (`backend/tests/unit`)

## Purpose

Unit tests validate the email core and API service/settings logic in isolation.
They do not require external services, browser interaction, or a database.

Primary target:

- `backend/core/email`
- `backend/api/database` (settings, token crypto, account repository token behavior)
- `backend/api/services` (auth service)
- `backend/api/settings` (auth settings)

## Test Principles

- Test one behavior per case.
- Keep tests deterministic and fast.
- Mock only external boundaries.
- Prefer pure function testing where possible.

## File Map

| File | Main Focus |
|---|---|
| `api/database/test_settings.py` | Env var parsing and validation for DB/token settings |
| `api/database/test_token_crypto.py` | Fernet encryption/decryption behavior and key validation |
| `api/database/test_account_repository.py` | Account repository CRUD + token dual-read fallback, lazy backfill, and context validation |
| `api/services/test_auth_service.py` | Auth service: validate_session, google_login, logout, get_current_user |
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
- `build_message(...)`

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
