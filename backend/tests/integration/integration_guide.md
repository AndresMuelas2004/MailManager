# Integration Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`general_integration_rules.md`](./general_integration_rules.md).
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
