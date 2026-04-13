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

`_apply_test_monkeypatches` patches `build_manager_for_accounts` in **four** modules today: `services_helpers`, `accounts_service`, `emails_service`, and `drafts_service`. Each module imports this function at its own module level, so all of them must be patched independently. **This list grows whenever a new service module imports `build_manager_for_accounts`** — when adding a fifth service, the module must be added here, otherwise its integration tests will call the real builder and hit real provider APIs. The same applies to `load_wrapped_app_credentials`, `load_wrapped_account_tokens`, and `account_store.upsert_tokens`.

### `seeded_test_client` fixture

`seeded_test_client` is a per-test fixture used by GET endpoint tests against the seeded data from migration `0010`. It overrides the auth dependency to return the seeded user ID (instead of the default test user), runs the body of the test, and then restores the previous override unconditionally after the yield (reassigns `app.dependency_overrides[require_session]` back to the default test user). Because the override is global to the FastAPI app, any test that uses this fixture must not interleave with other auth overrides; the fixture is fully self-contained.

### Auth endpoint integration coverage

`test_auth_endpoints.py` covers tests (non-exhaustive list) across: Google login (happy path, missing claims, auth error types), session management (GET /auth/me, expired session, deleted user), logout (happy path, DB errors, no cookie), DELETE /auth/me (cascade delete, user gone), and ownership enforcement (foreign mailbox 403, NULL owner defense).

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

### Email content integration coverage

- `test_email_content.py`: 7 tests for `GET /mailboxes/{mid}/emails/{msg_id}/content?account_id=...`.
- Cache-aside pattern: DB hit path (returns cached content without calling core) and DB miss path (fetches from provider via FakeEmailClient, FakeEmailClient defaults return `html_body=None` and `text_body=None`).
- Error paths: wrong user 403, missing account 404, missing mailbox 404, core error 502, and **missing metadata row 404 `email_not_found`** (`test_get_email_content_missing_metadata_returns_404` — verifies the pre-check added in migration 0013 rejects unknown message IDs before touching the provider or the FK).
- Additional error translation tests in `test_core_error_translation.py`: silent auth error (`EmailAuthError`) -> 409 `account_not_connected`, RuntimeError -> 502 `external_api_error` (RuntimeError is wrapped by EmailManager into EmailExternalAPIError before the service sees it). Both tests were updated when the metadata pre-check was introduced: they now target `m1` (a message ID seeded by `sample_metadata` via sync-metadata, or inserted directly into `email_metadata` via `isolated_db` when the fake's `auth_silent_exc` would block sync-metadata). Without this adjustment the pre-check would return 404 before the path the tests want to exercise.

### Drafts integration coverage

`test_drafts.py` covers all five draft endpoints (POST create + PATCH update + DELETE delete + GET list + POST sync).

**POST `/mailboxes/{mid}/accounts/{aid}/drafts`** — 5 tests:

- Happy path returns `DraftOut` with all payload fields round-tripped and provider-assigned `provider_draft_id`.
- Persisted to the `drafts` table (verified via `isolated_db.cursor()` reading the `to_recipients`, `cc_recipients`, `bcc_recipients`, `subject`, and `body_html` columns).
- Empty body (`{}`) is accepted — `subject`, `body_html`, and recipient arrays default to empty.
- Nonexistent account returns 404 `account_not_found`.
- Nonexistent mailbox returns 404 `mailbox_not_found` (ownership check runs first).

**DELETE `/mailboxes/{mid}/accounts/{aid}/drafts/{draft_id}`** — 8 tests:

- Happy path returns `{"status": "deleted"}`.
- Persisted deletion verified via `isolated_db.cursor()` — the draft row no longer exists in the `drafts` table.
- Draft not found in local DB returns 404 `draft_not_found`.
- Nonexistent account returns 404 `account_not_found`.
- Nonexistent mailbox returns 404 `mailbox_not_found` (ownership check runs first).
- Foreign mailbox returns 403 `forbidden`.
- Provider error preserves the local DB row — when the provider call fails, the draft is not deleted locally.
- `draft_store.delete` raising `QueryError` → 503 `database_query_error`.

**GET `/mailboxes/{mid}/drafts`** — 7 tests (helper: `_list_drafts_url(mailbox_id, account_id=None)`):

- Empty mailbox returns `[]`.
- Single-account view: POSTs 3 drafts and verifies the GET with `?account_id=...` returns them in `created_at DESC` order.
- Unified view: creates 2 accounts in the same mailbox, POSTs 2 drafts in each (4 total), GET without `account_id` returns all 4.
- Cross-mailbox isolation: creates 2 mailboxes with 1 draft each, verifies GETs do not cross mailbox boundaries.
- Nonexistent mailbox returns 404 `mailbox_not_found`.
- Nonexistent account returns 404 `account_not_found`.
- Foreign mailbox returns 403 `forbidden`. Uses a local `_create_foreign_mailbox` helper (replicated from `test_auth_endpoints.py` to keep the draft test file self-contained).

**`_insert_draft` helper and the `now()` invariance trap**: `test_drafts.py` uses a local `_insert_draft` helper to seed rows directly via SQL (bypassing `FakeEmailClient`'s default `provider_draft_id` collision across multiple POSTs). The helper accepts an optional `created_at` ISO string. This parameter is essential for ordering tests: PostgreSQL's `now()` returns the **same value for every statement inside a single transaction** — so when the isolated-db fixture wraps the whole test in one transaction, rows inserted back-to-back without explicit timestamps all share the exact same `created_at`, and `ORDER BY created_at DESC` produces a non-deterministic order. Tests that assert a specific ordering must pass distinct `created_at` values to `_insert_draft`.

**POST `/mailboxes/{mid}/drafts/sync`** — 10 tests (helpers: `_sync_drafts_url`, `_make_draft`, `_patch_drafts_builder`):

- Empty provider returns zero: `FakeEmailClient.fetch_drafts_return=[]` → response `total_synced == 0` and 0 rows in DB.
- Single-account persists 3 drafts: provider returns 3 DraftMetadata → response `total_synced == 3` and DB contains exactly those 3 provider_draft_ids.
- Mailbox-wide persists rows for all accounts: 2 accounts with 2 drafts each → response `total_synced == 4`, 2 `accounts` entries, 4 DB rows.
- Replaces stale rows: pre-insert 2 stale drafts directly in DB, provider returns 1 new draft → after sync only the new draft remains (stale ones deleted).
- Upserts existing rows: pre-insert a draft, provider returns the same provider_draft_id with a changed subject → subject is updated in place via `ON CONFLICT DO UPDATE`.
- Empty provider for a single account returns `total_synced == 0` and 0 DB rows.
- Empty provider for mailbox-wide sync with multiple accounts returns `total_synced == 0` and the `accounts` list is populated (one entry per account).
- `draft_store.replace_all_for_account` raising `QueryError` → 503 `database_query_error`.
- Nonexistent account returns 404 `account_not_found`.
- Foreign mailbox returns 403 `forbidden` (reuses `_create_foreign_mailbox`).

The `_patch_drafts_builder` helper overrides `drafts_service.build_manager_for_accounts` with a fresh builder that constructs a `FakeEmailClient` per account and configures its `fetch_drafts_return` from a `dict[account_id, list[DraftMetadata]]` map. This is how each sync test injects the exact drafts the "provider" should return without relying on real Gmail/Outlook APIs.

**PATCH `/mailboxes/{mid}/accounts/{aid}/drafts/{provider_draft_id}`** — 12 tests:

- Happy path returns `DraftOut` with updated fields (`subject`, recipients, `body_html`).
- DB persistence verified via `isolated_db.cursor()` — reads `subject`, `to_recipients`, `body_html` from the `drafts` table and asserts the new values.
- `created_at` is preserved from the original insert; `updated_at` is greater than or equal to `created_at`.
- Empty body (`{}`) is accepted — all fields default to empty strings / empty arrays (same behavior as POST create).
- Draft not found (no matching DB row) → 404 `draft_not_found`.
- Nonexistent account → 404 `account_not_found`.
- Nonexistent mailbox → 404 `mailbox_not_found`.
- Foreign mailbox → 403 `forbidden`.
- Provider `EmailExternalAPIError` → 502 `external_api_error`.
- Provider generic `RuntimeError` → 502 `external_api_error`.
- `draft_store.update` raising `QueryError` → 503 `database_query_error`.
- Silent auth `EmailAuthError` → 409 `account_not_connected`.

Core-error translation tests for drafts live in `test_core_error_translation.py`:

- **Create draft** (3 parametrized cases): `create_draft_exc: EmailExternalAPIError → 502`, `auth_silent_exc: EmailAuthError → 409`, `create_draft_exc: RuntimeError → 502`.
- **Delete draft** (3 parametrized cases): `delete_draft_exc: EmailExternalAPIError → 502 external_api_error`, `auth_silent_exc: EmailAuthError → 409 account_not_connected`, `delete_draft_exc: RuntimeError → 502 external_api_error` (RuntimeError is wrapped by the manager into `EmailExternalAPIError`). Each test seeds a draft row via `_insert_draft_for_delete` so the service pre-check passes.
- **Sync drafts** (3 parametrized cases): `fetch_drafts_exc: EmailExternalAPIError → 502 external_api_error`, `auth_silent_exc: EmailAuthError → 409 account_not_connected`, `fetch_drafts_exc: RuntimeError → 502 draft_sync_error`. Note: `RuntimeError` from sync is captured in `_last_errors` by `EmailManager.fetch_all_drafts` (not wrapped like `send_email` does) and surfaces as `draft_sync_error` (the fallback passed to `raise_on_silent_auth_errors`), not `external_api_error`.

The GET `list_drafts` endpoint is DB-only and has no provider call path to translate.

**Trap reminder**: when the drafts feature was first added, `conftest.py` needed two updates that any future draft-related endpoint must also respect:
1. The new `draft_repository` module must be added to the `isolated_db` fixture so it shares the per-test transaction connection (otherwise the `INSERT_DRAFT`, `LIST_DRAFTS_BY_ACCOUNT`, and `LIST_DRAFTS_BY_MAILBOX` queries bypass the rollback and leak data between tests).
2. The new `drafts_service` module must be added to `_apply_test_monkeypatches` for `build_manager_for_accounts`, `load_wrapped_app_credentials`, `load_wrapped_account_tokens`, and `account_store.upsert_tokens` (otherwise the service hits the real provider APIs — **only relevant for POST, PATCH, and DELETE**; the GET does not use any of these helpers).

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

GET endpoints that read exclusively from the database (no provider API calls, no fakes in the read path) can be fully covered by integration tests with the **same fidelity as E2E tests**. GET endpoints that involve external calls (e.g. cache-aside with provider fallback) require additional test strategies beyond the seeded-data approach described here.

**Rule 1 — Use seeded data, not ephemeral data.** All GET endpoint tests must use the seeded fake data from migration 0010 (documented below) via the `seeded_test_client` fixture, which authenticates as the seeded user. Do not create throwaway resources via POST just to test a GET — the seeded data is deterministic, permanent, and provides known expected values.

**Rule 2 — Assert exact content, not just status codes.** Every GET test must verify both the HTTP status **and** the actual response content against the known seeded values. For example: assert that `GET /mailboxes` returns entries with `display_name == "Gmail inventada"`, not just that it returns 200. Assert that `GET .../emails?box=SENT` returns exactly 10 items, not `len >= 1`.

**Rule 3 — Cover all parameter variants.** When a GET endpoint accepts filtering parameters (e.g. `box`, `account_id`), test every valid combination. Use `@pytest.mark.parametrize` to keep the code compact.

**Rule 4 — New database-only GET endpoints must follow these rules.** Whenever a new GET endpoint that reads exclusively from the database is added, its integration tests must use the seeded data and assert exact content. If the new endpoint reads data not covered by the current seed, extend the seed (new migration + update the data section below) before writing the tests. GET endpoints with external dependencies (e.g. cache or provider fallback) define their own test strategy in their endpoint documentation.

### Seeded fake data for GET endpoint assertions (migration 0010)

Migration `0010_seed_fake_data_for_get_tests` inserts a complete set of fake data into the real database, designed exclusively for testing database-only GET endpoints with exact content assertions — not just HTTP 200 status codes. This data is **not authenticated** with any real provider; it exists only to verify that the API returns the correct records from the database.

**Why this matters for integration tests:** Integration tests already use a real PostgreSQL database (with per-test rollback). For GET endpoints that read exclusively from the database, integration tests cover them with the same fidelity as E2E. The seeded data allows tests to assert exact counts and content per box/account, rather than just checking status codes.

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
