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
- `existing_message_ids` — set of IDs returned by `verify_message_existence`.
- `sync_cursor_return` — the cursor string returned by the fake.

Tests mutate `config` between API calls to simulate different provider responses within a single test function. Because the `FakeEmailClient` reads from the same `config` dict reference, changes take effect immediately on the next API call.

### Trap: new service module must be patched in `_apply_test_monkeypatches`

`_apply_test_monkeypatches` patches `build_manager_for_accounts` in three modules: `services_helpers`, `accounts_service`, and `emails_service`. Each module imports this function at its own module level, so all three must be patched independently. If a new service module is added that also imports `build_manager_for_accounts`, it must be added to `_apply_test_monkeypatches` — otherwise, that module's tests will call the real builder and hit real provider APIs.

### Missing claims tests for Google login

`test_auth_endpoints.py` covers 27 tests across: Google login (happy path, missing claims, auth error types), session management (GET /auth/me, expired session, deleted user), logout (happy path, DB errors, no cookie), DELETE /auth/me (cascade delete, user gone), and ownership enforcement (foreign mailbox 403, NULL owner defense).

### Trash tests use manual DB UPDATE

Trash management integration tests first sync emails via the normal sync endpoint, then manually `UPDATE email_metadata SET box = 'TRASH'` using `isolated_db` to simulate emails being in trash. Now that `move_to_trash` is implemented, new trash tests can use the API endpoint instead of raw SQL, but existing tests retain the manual approach for backward compatibility.

### Move-to-trash integration coverage

- Happy path: move-to-trash for a single account with successful provider response (`test_endpoints.py`).
- Multi-account: move-to-trash across multiple accounts in a single request (`test_endpoints.py`).
- Partial success: some messages succeed at the provider while others fail, verifying per-item result reporting (`test_endpoints.py`).
- Error translations: `MoveToTrashError` from provider failures is tested via `failing_test_client` with `indirect=True` parametrize (`test_core_error_translation.py`).

### `configurable_test_client` for multi-phase tests

The `configurable_test_client` fixture (`conftest.py`) returns a tuple `(client, config)`. Mutating the `config` dict between API calls changes the `FakeEmailClient` behavior for subsequent requests (metadata, deletes, label updates, sync cursors, restore/delete/move-to-trash returns). Use it when a test needs to exercise multiple API calls with different provider responses. Compare: `test_client` provides a static fake, `failing_test_client` injects a single failure, `configurable_test_client` allows dynamic behavior changes.
