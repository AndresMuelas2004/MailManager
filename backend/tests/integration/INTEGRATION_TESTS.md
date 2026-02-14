# Integration Tests — `backend/tests/integration/`

## Purpose

Integration tests verify that the **full request flow** (router → service → core → storage) works correctly when all internal layers are wired together. Only external boundaries are faked: provider APIs, disk-based token files, and environment variables for credentials. JSON storage runs against real implementations redirected to temporary directories.

## What is Real vs Faked

| Component | Real or Fake | Mechanism |
|-----------|-------------|-----------|
| FastAPI router | Real | `TestClient` (ASGI in-process) |
| Services | Real | Normal import path |
| JSON storage | Real | `isolated_storage` autouse fixture → temp dir |
| EmailManager (orchestrator) | Real | Standard instantiation |
| EmailClient (Gmail/Outlook) | **Fake** | `build_manager_for_accounts` patch → `FakeEmailClient` |
| App credentials (disk/env) | **Fake** | `load_wrapped_app_credentials` → static dict |
| Account tokens (disk/env) | **Fake** | `load_wrapped_account_tokens` → static dict |
| Token persistence | **Fake** | `save_account_tokens` → no-op |
| Token cleanup | **Fake** | `delete_account_tokens_for_records` → no-op |

## Test File Organization

| File | What it covers | Tests |
|------|---------------|-------|
| `test_endpoints.py` | Happy-path CRUD for all 13 endpoints, multi-account scenarios, delete cascade, partial updates, and cross-provider (Outlook) flows | 18 |
| `test_api_layer_errors.py` | Direct `raise ApiError(...)` in services — no core error translation involved (404s, 422s) | 14 |
| `test_core_error_translation.py` | Core errors escalated via `translate_core_error` / `raise_on_silent_auth_errors` to API errors (409, 502, 400) | 7 |

## `test_endpoints.py` — Happy-Path and Behavioral Tests

### Happy-Path — One per Endpoint (13 tests)

| Test | Endpoint | Key assertion |
|------|----------|---------------|
| `test_health` | `GET /health` | 200, `{"status": "ok"}` |
| `test_create_mailbox` | `POST /mailboxes` | 200, response has `mailbox_id` and `display_name` |
| `test_list_mailboxes` | `GET /mailboxes` | 200, created mailbox appears in the list |
| `test_get_mailbox` | `GET /mailboxes/{id}` | 200, `mailbox_id` matches |
| `test_delete_mailbox` | `DELETE /mailboxes/{id}` | 200, `{"status": "deleted"}`, subsequent GET → 404 |
| `test_create_account` | `POST .../accounts` | 200, has `account_id` and `provider` |
| `test_list_accounts` | `GET .../accounts` | 200, list length 1 |
| `test_get_account` | `GET .../accounts/{id}` | 200, `account_id` matches |
| `test_update_account` | `PATCH .../accounts/{id}` | 200, `display_label` changed |
| `test_delete_account` | `DELETE .../accounts/{id}` | 200, `{"status": "deleted"}` |
| `test_connect_account` | `POST .../accounts/{id}/connect` | 200, `connected=True` |
| `test_list_unread_emails` | `GET .../emails/unread` | 200, returns 3 messages (from single FakeEmailClient) |
| `test_send_email` | `POST .../emails/send` | 200, `{"status": "sent"}` |

### Behavioral Tests (5 tests)

| Test | What it verifies |
|------|-----------------|
| `test_multi_account_unread_aggregates` | Two accounts (gmail + outlook) → unread returns 6 messages (3 per fake client) |
| `test_multi_account_send_targets_specific_account` | Send routes to the correct account by `account_id` |
| `test_delete_mailbox_removes_accounts` | Deleting a mailbox also deletes all its accounts |
| `test_update_account_config_only` | PATCH with only `config` updates config without changing `display_label` |
| `test_outlook_account_connect` | Create + connect an Outlook account end-to-end |

## `test_api_layer_errors.py` — Direct API-Layer Raises

These test every `raise ApiError(...)` that the service layer performs **directly**, without involving `translate_core_error`. The core layer is not involved in triggering these errors.

### MailboxNotFound (404) — 7 tests

| Test | Trigger |
|------|---------|
| `test_get_mailbox_not_found` | `GET /mailboxes/{bad}` |
| `test_delete_mailbox_not_found` | `DELETE /mailboxes/{bad}` |
| `test_create_account_on_missing_mailbox` | `POST /mailboxes/{bad}/accounts` |
| `test_list_accounts_missing_mailbox` | `GET /mailboxes/{bad}/accounts` |
| `test_connect_account_missing_mailbox` | `POST .../connect` on missing mailbox |
| `test_unread_missing_mailbox` | `GET .../emails/unread` on missing mailbox |
| `test_send_missing_mailbox` | `POST .../emails/send` on missing mailbox |

### AccountNotFound (404) — 5 tests

| Test | Trigger |
|------|---------|
| `test_get_account_not_found` | `GET .../accounts/{bad}` |
| `test_update_account_not_found` | `PATCH .../accounts/{bad}` |
| `test_delete_account_not_found` | `DELETE .../accounts/{bad}` |
| `test_connect_account_not_found` | `POST .../accounts/{bad}/connect` |
| `test_send_account_not_found` | `POST .../emails/send` with bad `account_id` |

### Pydantic 422 — 2 tests

| Test | Trigger |
|------|---------|
| `test_create_mailbox_invalid_body` | Missing `display_name` |
| `test_create_account_empty_provider` | Empty `provider` string |

## `test_core_error_translation.py` — Core → API Error Translation

These test errors that **originate in the core layer** (`CoreError` subclasses) and are translated to `ApiError` subclasses via `translate_core_error` or `raise_on_silent_auth_errors`. The `failing_test_client` fixture injects failure kwargs into `FakeEmailClient`.

### connect_account — EmailAuthError → translate_core_error (1 test)

| Test | Core error | Expected status |
|------|-----------|-----------------|
| `test_connect_auth_failure` | `EmailAuthError` via `auth_exc` | 409 (AccountNotConnected per `_CORE_TO_API_MAP`) |

### authenticate_all_silent — raise_on_silent_auth_errors (2 tests)

| Test | Core error | Expected status |
|------|-----------|-----------------|
| `test_unread_account_not_connected` | `EmailAuthError` via `auth_silent_exc` | 409 |
| `test_send_account_not_connected` | `EmailAuthError` via `auth_silent_exc` | 409 |

### fetch / send — CoreError → translate_core_error (2 tests)

| Test | Core error | Expected status |
|------|-----------|-----------------|
| `test_unread_fetch_failure` | `EmailExternalAPIError` via `fetch_exc` | 502 |
| `test_send_failure` | `EmailExternalAPIError` via `send_exc` | 502 |

### build_manager_for_accounts — CoreError → AccountMisconfigured (1 test)

| Test | Core error | Expected status |
|------|-----------|-----------------|
| `test_connect_account_misconfigured` | `EmailProviderConfigError` → `translate_core_error` | 400 |

### Known issue

`test_connect_auth_failure` returns 409 because `_CORE_TO_API_MAP` maps `EmailAuthError` → `AccountNotConnected`, overriding the `fallback=ProviderAuthError` in `accounts_service.connect_account`. This may warrant a review of the mapping or a dedicated exception for interactive auth failures.

## Fixture Stack

1. **`temp_base_dir`** (session) — shared temporary directory for the test session.
2. **`isolated_storage`** (autouse, per-test) — redirects `json_store._MAILBOXES_PATH` and `_ACCOUNTS_PATH` to a fresh temp subdirectory so each test starts with empty storage.
3. **`test_client`** (per-test) — wraps `test_client_base` (FastAPI `TestClient`) and applies all monkeypatches for faking credentials, tokens, and the email client builder. Used by happy-path and direct API error tests.
4. **`failing_test_client`** (per-test, indirect parametrize) — same patches as `test_client` but forwards extra kwargs (e.g. `auth_exc`, `fetch_exc`) to `FakeEmailClient`. Used by core error translation tests.

## What is NOT Integration-Tested

- **Real OAuth flows** — require browser interaction and live provider APIs; belongs in E2E.
- **Real token refresh** — requires valid tokens against live endpoints; belongs in E2E.
- **Real email fetch/send** — requires authenticated sessions with Gmail/Outlook APIs; belongs in E2E.
- **Frontend integration** — CORS, browser HTTP client behavior; belongs in E2E.

## Running Tests

```bash
# All integration tests
python -m pytest backend/tests/integration -v

# Happy-path tests only
python -m pytest backend/tests/integration/test_endpoints.py -v

# Direct API-layer error tests
python -m pytest backend/tests/integration/test_api_layer_errors.py -v

# Core error translation tests
python -m pytest backend/tests/integration/test_core_error_translation.py -v

# Single test by name
python -m pytest backend/tests/integration -k "test_connect_auth_failure"
```
