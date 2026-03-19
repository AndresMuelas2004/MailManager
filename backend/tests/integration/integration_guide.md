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
app.dependency_overrides.pop(require_session, None)
try:
    # test code
finally:
    app.dependency_overrides[require_session] = override_fn
```

The `finally` block is essential — without it, a test failure would leave the override removed, breaking all subsequent tests.

### `translate_database_error` coverage via monkeypatched stores

Integration tests for database error translation (`test_api_layer_errors.py`) monkeypatch specific store methods (e.g. `mailbox_store.list_by_owner`, `account_store.upsert`) to raise `QueryError` or `ConnectionPoolError` after initial setup succeeds. This verifies the full path from store failure through `translate_database_error` to the HTTP response.

### Missing claims tests for Google login

`test_auth_endpoints.py` includes integration tests verifying that Google login correctly rejects tokens missing the `sub` or `email` claims with a 401 response. These complement the unit-level claim checks in `test_auth_service.py`.
