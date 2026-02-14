# Unit Tests — `backend/tests/unit/`

## Purpose

Unit tests verify the **core email layer** (`core/email/`) in isolation, without network access, databases, or browser interaction. External boundaries (Google OAuth, Microsoft Graph, urllib) are replaced by fakes or mocks.

## Test File Organization

| File | What it covers | Approx. tests |
|------|---------------|---------------|
| `core/email/test_email_manager.py` | `EmailManager` CRUD, auth orchestration, fetch/send routing, error registry | ~24 |
| `core/email/test_email_manager_extended.py` | `EmailManager` gap-filling: auth_payloads forwarding, refreshed token collection, send error propagation | ~8 |
| `core/email/test_errors.py` | Error hierarchy: inheritance chains, `code` uniqueness, `default_message`, `detail` dict, `CoreUnexpectedError.original` | ~20 |
| `core/email/test_gmail_client.py` | `GmailClient` pure helpers (`_parse_expiry`, `_unwrap_*`, `_build_client_config`, `_wrap_account_tokens`) and guard clauses | ~25 |
| `core/email/test_outlook_client.py` | `OutlookClient` pure helpers (`_parse_expiry`, `_unwrap_*`, `_resolve_scopes`, `_compute_expiry`, `_token_url`), guard clauses, and refresh path with mocked `_token_request` | ~30 |

## Shared Test Utilities
/
### `FakeEmailClient` (in `core/conftest.py`)

A concrete `EmailClient` subclass for testing `EmailManager` without real providers.

**Constructor parameters:**
- `account_label` — label returned by `get_account_label()`
- `auth_exc` / `auth_silent_exc` / `fetch_exc` / `send_exc` — exceptions raised by the corresponding methods
- `unread_messages` — list of `EmailMessage` returned by `fetch_unread_emails()`
- `auth_return` / `auth_silent_return` — values returned by `authenticate()` / `authenticate_silent()`

**Tracking attributes:**
- `authenticate_calls`, `authenticate_silent_calls`, `fetch_calls` — call counters
- `sent_emails` — list of `(subject, body, recipients)` tuples
- `last_app_credentials`, `last_user_tokens` — last arguments passed

### `build_message` helper

Factory function for creating `EmailMessage` instances with sensible defaults.

## Mocking Strategy

- **Pure helpers** (e.g., `_parse_expiry`, `_resolve_scopes`) are tested directly — no mocking needed.
- **Guard clauses** require minimal setup (just constructor + bad input) — no mocking needed.
- **Refresh paths** mock at the boundary: `OutlookClient._token_request` is patched via `unittest.mock.patch` to simulate Microsoft token endpoint responses.
- **EmailManager** tests use `FakeEmailClient` instead of real `GmailClient`/`OutlookClient`.

## What is NOT Unit-Tested

- **Interactive OAuth flows** (`authenticate()` full flow) — requires browser/local server
- **Actual HTTP calls** (`_token_request`, `_graph_request`, Gmail API `build()`) — hit external servers
- **`fetch_unread_emails` parsing** — tightly coupled to provider API response formats; better tested in integration/E2E
- **API services layer** — covered by integration tests

## Running Tests

```bash
# All unit tests
python -m pytest backend/tests/unit -v

# Core email tests only
python -m pytest backend/tests/unit/core/email/ -v

# Single file
python -m pytest backend/tests/unit/core/email/test_errors.py -v

# Single test by name
python -m pytest backend/tests/unit -k "test_parse_expiry_iso_string"
```

## Naming Conventions

- Test files: `test_<module>.py`
- Test functions: `test_<method_or_behavior>_<scenario>` (e.g., `test_parse_expiry_none_returns_none`)
- Test classes: group related tests (e.g., `TestParseExpiry`, `TestGuardClauses`)
- Fixtures: descriptive names matching what they provide (e.g., `client`, `manager`, `fake_client_factory`)
