# Integration Tests (`backend/tests/integration`)

## Purpose

Integration tests verify the full internal backend flow:

```text
router -> service -> database -> core
```

These tests execute real FastAPI endpoints and real PostgreSQL operations,
while replacing external provider boundaries with fakes.

## Test Boundary Model

| Component | Real or Fake | Notes |
|---|---|---|
| FastAPI app | Real | Exercised via TestClient |
| Routers and services | Real | Production modules |
| PostgreSQL | Real | Per-test transaction rollback isolation |
| EmailManager orchestration | Real | Built and used in tests |
| Gmail/Outlook provider calls | Fake | Replaced with `FakeEmailClient` |
| App credentials loading | Fake | Monkeypatched wrapped credentials |
| Account token loading/saving | Fake | Monkeypatched token I/O helpers |

## Files and Coverage

| File | Focus |
|---|---|
| `test_endpoints.py` | Happy-path and behavioral endpoint tests |
| `test_api_layer_errors.py` | Direct API-layer errors raised in services |
| `test_core_error_translation.py` | Core error to API error translation paths |
| `conftest.py` | Shared fixtures, DB isolation, monkeypatch wiring |

## Key Fixtures

### `create_test_schema` (session, autouse)

- Requires `DATABASE_URL`.
- Executes `api/database/schema.sql` once at session start.

### `isolated_db` (autouse, per test)

- Opens one PostgreSQL connection with `autocommit=False`.
- Monkeypatches `get_connection` in:
  - `api.database.db`
  - `api.database.repository`
  - `api.database.token_store`
- Rolls back after each test for clean isolation.

### `test_client`

- Patches manager builder and credential/token helpers.
- Uses `FakeEmailClient` from `tests/shared/email_fakes.py`.
- Used for happy-path and direct API error tests.

### `failing_test_client` (indirect parametrize)

- Same as `test_client` with injected fake client failures.
- Used for core translation tests.

## Error Strategy Coverage

Integration tests separate two major error surfaces.

1. Direct API-layer errors (service raises `ApiError` directly)

- Missing mailbox/account
- Request validation failures
- Other direct service-level guard errors

2. Core-originated errors translated to API errors

- Auth/connect failures
- Silent auth failures
- Provider operation failures
- Account misconfiguration at manager build time

## What These Tests Do Not Cover

- Real OAuth browser flows
- Real provider HTTP traffic
- Real token refresh against live endpoints
- Frontend behavior

Those are covered by E2E tests.

## Running the Suite

```bash
# All integration tests
python -m pytest backend/tests/integration -v

# Endpoint behavior tests
python -m pytest backend/tests/integration/test_endpoints.py -v

# Direct API-layer error tests
python -m pytest backend/tests/integration/test_api_layer_errors.py -v

# Core-to-API translation tests
python -m pytest backend/tests/integration/test_core_error_translation.py -v

# Filter by test name
python -m pytest backend/tests/integration -k "connect_auth_failure"
```

## Maintenance Rules

- Keep fake behavior deterministic.
- Keep each test focused on one API contract or one translation path.
- Avoid provider-specific assumptions in integration tests.
- Add E2E coverage when a change depends on real provider behavior.
