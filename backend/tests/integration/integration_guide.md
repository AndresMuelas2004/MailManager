> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# Integration Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Project-Specific Notes

### Trap: new repository must be patched in `isolated_db`

When adding a new repository module, its `get_connection` must be monkeypatched in the `isolated_db` fixture (`conftest.py`). If you forget, that repository will use the real connection pool instead of the per-test transaction, breaking isolation and causing flaky tests.

### `failing_test_client` with `indirect=True`

The `failing_test_client` fixture uses `@pytest.mark.parametrize(..., indirect=True)` to inject specific failure behaviors into `FakeEmailClient`. The parametrize value configures which client method raises and what error — this is not obvious from the fixture signature alone.

### Auth override removal pattern

Most tests run with `require_session` overridden to return `TEST_USER_ID`. Tests that verify real session validation (no cookie, expired session) temporarily remove the override:

```python
override = app.dependency_overrides.pop(require_session, None)
try:
    # test code
finally:
    if override is not None:
        app.dependency_overrides[require_session] = override
```

The `finally` block is essential — without it, a test failure would leave the override removed, breaking all subsequent tests.

### `translate_database_error` coverage via monkeypatched stores

Integration tests for database error translation (`test_api_layer_errors.py`) monkeypatch specific store methods (e.g. `mailbox_store.list_by_owner`, `account_store.upsert`) to raise `QueryError` or `ConnectionPoolError` after initial setup succeeds. This verifies the full path from store failure through `translate_database_error` to the HTTP response.

### `configurable_test_client` fixture

Returns a `(client, config)` tuple where `client` is a FastAPI `TestClient` and `config` is a mutable dict that controls `FakeEmailClient` behavior at runtime. Supported keys in `config`:

- `metadata` — list of `EmailMetadata` objects the fake client returns from `fetch_email_metadata`.
- `deletes` — list of `provider_message_id`s to include as deletes in the `SyncResult`.
- `label_updates` — list of `LabelUpdate` objects for partial label changes.
- `is_full_sync` — boolean controlling `SyncResult.is_full_sync`.
- `existing_message_ids` — list of IDs returned by `verify_message_existence` (initialized as a list in the config dict; `FakeEmailClient` converts to set internally).
- `sync_cursor_return` — the cursor string returned by the fake.
- `delete_return` — value returned by the fake's `delete_email` method (default `None`).
- `restore_return` — value returned by the fake's `restore_email` method (default `None`).
- `move_to_trash_return` — value returned by the fake's `move_to_trash` method (default `None`).
- `fetch_messages_metadata_return` — value returned by the fake's `fetch_messages_metadata` method (default `None`).

Tests mutate `config` between API calls to simulate different provider responses within a single test function. Because the `FakeEmailClient` reads from the same `config` dict reference, changes take effect immediately on the next API call. Compare: `test_client` provides a static fake, `failing_test_client` injects a single failure, `configurable_test_client` allows dynamic behavior changes.

### Trap: new service module must be patched in `_apply_test_monkeypatches`

`_apply_test_monkeypatches` patches `build_manager_for_accounts` in three modules: `services_helpers`, `accounts_service`, and `emails_service`. Each module imports this function at its own module level, so all three must be patched independently. If a new service module is added that also imports `build_manager_for_accounts`, it must be added to `_apply_test_monkeypatches` — otherwise, that module's tests will call the real builder and hit real provider APIs.

### Missing claims tests for Google login

`test_auth_endpoints.py` covers 26 tests across: Google login (happy path, missing claims, auth error types), session management (GET /auth/me, expired session, deleted user), logout (happy path, DB errors, no cookie), DELETE /auth/me (cascade delete, user gone), and ownership enforcement (foreign mailbox 403, NULL owner defense).

### Trash tests use manual DB UPDATE

Trash management integration tests first sync emails via the normal sync endpoint, then manually `UPDATE email_metadata SET box = 'TRASH'` using `isolated_db` to simulate emails being in trash. Now that `move_to_trash` is implemented, new trash tests can use the API endpoint instead of raw SQL, but existing tests retain the manual approach for backward compatibility.

### Move-to-trash integration coverage

- Happy path: move-to-trash for a single account with successful provider response (`test_endpoints.py`).
- Multi-account: move-to-trash across multiple accounts in a single request (`test_endpoints.py`).
- Partial success: some messages succeed at the provider while others fail, verifying per-item result reporting (`test_endpoints.py`).
- Error translations: core exceptions (`EmailExternalAPIError`, `EmailAuthError`, `RuntimeError`) during move-to-trash are tested via `failing_test_client` with `indirect=True` parametrize (`test_core_error_translation.py`). `RuntimeError` translates to `ExternalAPIError` (502) because `EmailManager` wraps it in `EmailExternalAPIError` before the service sees it.

### Read-status integration coverage

10 tests across three files:

- **`test_endpoints.py`** (5): happy path (mark read), persistence to DB, box preservation after read-status update, nonexistent account 404, nonexistent mailbox 404.
- **`test_core_error_translation.py`** (3): `EmailExternalAPIError` -> 502, `EmailAuthError` (silent auth failure) -> 409, `RuntimeError` -> 502 (wrapped by `EmailManager` into `EmailExternalAPIError`).
- **`test_api_layer_errors.py`** (2): empty items list -> 422, missing required fields -> 422.

### Spam integration coverage

16 tests across three files covering move-to-spam and restore-from-spam:

- **`test_endpoints.py`** (8): move-to-spam happy path, move persists box to DB, restore-from-spam happy path, restore persists box to DB, nonexistent account 404 (move), nonexistent mailbox 404 (move), nonexistent account 404 (restore), nonexistent mailbox 404 (restore).
- **`test_core_error_translation.py`** (6): for both move and restore — `EmailExternalAPIError` -> 502, `EmailAuthError` (silent auth failure) -> 409, `RuntimeError` -> 502 (wrapped by `EmailManager`).
- **`test_api_layer_errors.py`** (2): empty items list -> 422 (move), empty items list -> 422 (restore).

### Email listing integration coverage

14 tests in `test_endpoints.py`:

- Unified view (`?box=ALL_MAIL`) returns 200 with exactly 30 emails, all with correct `box` and `account_id`.
- Single account view (`?box=ALL_MAIL&account_id=<id>`) returns 200 with exactly 30 emails, all matching `account_id`.
- Invalid box value returns 422.
- Missing box parameter returns 422.
- Nonexistent `account_id` returns 404 (`account_not_found`).
- Nonexistent `mailbox_id` returns 404 (`mailbox_not_found`).
- Parametrized by-account tests (4): one per box (ALL_MAIL=30, SENT=10, TRASH=4, SPAM=6), exact counts and field assertions.
- Parametrized by-mailbox tests (4): same distribution, no `account_id` filter.

### GET endpoint testing rules (mandatory)

GET endpoints only read from the database — they never call provider APIs and no fakes are involved in the read path. This means integration tests cover GET endpoints with the **same fidelity as E2E tests**. There is no coverage gap.

**Rule 1 — Use seeded data, not ephemeral data.** All GET endpoint tests must use the seeded fake data from migration 0010 (documented below) via the `seeded_test_client` fixture, which authenticates as the seeded user. Do not create throwaway resources via POST just to test a GET — the seeded data is deterministic, permanent, and provides known expected values.

**Rule 2 — Assert exact content, not just status codes.** Every GET test must verify both the HTTP status **and** the actual response content against the known seeded values. For example: assert that `GET /mailboxes` returns entries with `display_name == "Gmail inventada"`, not just that it returns 200. Assert that `GET .../emails?box=SENT` returns exactly 10 items, not `len >= 1`.

**Rule 3 — Cover all parameter variants.** When a GET endpoint accepts filtering parameters (e.g. `box`, `account_id`), test every valid combination. Use `@pytest.mark.parametrize` to keep the code compact.

**Rule 4 — New GET endpoints must follow these rules.** Whenever a new GET endpoint is added, its integration tests must use the seeded data and assert exact content. If the new endpoint reads data not covered by the current seed, extend the seed (new migration + update the data section below) before writing the tests.

### Seeded fake data for GET endpoint assertions (migration 0010)

Migration `0010_seed_fake_data_for_get_tests` inserts a complete set of fake data into the real database, designed exclusively for testing GET endpoints with exact content assertions — not just HTTP 200 status codes. This data is **not authenticated** with any real provider; it exists only to verify that the API returns the correct records from the database.

**Why this matters for integration tests:** Integration tests already use a real PostgreSQL database (with per-test rollback). Since GET endpoints are pure DB reads (no provider API calls, no fakes involved), integration tests cover them with the same fidelity as E2E. The seeded data allows tests to assert exact counts and content per box/account, rather than just checking status codes.

#### Identifiers (fixed UUIDs)

| Entity | ID |
|---|---|
| User | `11111111-1111-4000-a000-111111111111` |
| Gmail mailbox | `aaaaaaaa-aaaa-4000-a000-aaaaaaaaa001` |
| Outlook mailbox | `aaaaaaaa-aaaa-4000-a000-aaaaaaaaa002` |
| Gmail account | `bbbbbbbb-bbbb-4000-a000-bbbbbbbbb001` |
| Outlook account | `bbbbbbbb-bbbb-4000-a000-bbbbbbbbb002` |

#### User

- `name`: `inventadoParaEndpointGet`
- `email`: `inventadoParaEndpointGet@fake.test`
- `google_sub`: `inventadoParaEndpointGet-google-sub`

#### Accounts

| Account | Provider | Display label | Email address |
|---|---|---|---|
| Gmail | `gmail` | `Gmail inventada - inventadoParaEndpointGet` | `gmailinventada@gmail.com` |
| Outlook | `outlook` | `Outlook inventada - inventadoParaEndpointGet` | `outlookinventada@outlook.com` |

#### Email distribution (identical per account, 50 emails each)

| Box | Count |
|---|---|
| `ALL_MAIL` | 30 |
| `SENT` | 10 |
| `TRASH` | 4 |
| `SPAM` | 6 |
| **Total** | **50** |

All SENT emails have `from_email` = the account's email address and `from_name` = `inventadoParaEndpointGet`. TRASH emails have `previous_box = 'ALL_MAIL'`. SPAM emails have `previous_box = NULL`. Emails span from `2026-03-01` to `2026-03-13` with unique subjects and varied `is_read` values.

The full data is also available as structured JSON in `tests/fixtures/seed_get_endpoints.json`.
