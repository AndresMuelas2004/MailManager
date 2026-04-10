> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# Unit Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Project-Specific Notes

### Coverage targets

Unit tests cover: `core/email` (clients, manager, helpers, errors), `database` (settings, token crypto, repositories, credentials, connection, lifecycle), `api/services` (auth, emails, accounts, mailboxes, drafts, error translation, helpers), and `auth` (settings).

This list is **representative**, not exhaustive — the canonical inventory is the `tests/unit/` directory tree itself. When a new service module is added (e.g. `drafts_service.py`), add a `test_<module>.py` file plus a coverage subsection here.

### Service test pattern: Fake stores with monkeypatch

Tests for service modules (`test_accounts_service.py`, `test_mailboxes_service.py`) use inline Fake store classes (e.g. `FakeAccountStore`, `FakeMailboxStore`) combined with `monkeypatch.setattr` to replace the real store module attributes. This avoids database access entirely and allows precise control over success/failure paths. The pattern:

1. Define a `FakeStore` class with the same method signatures as the real store.
2. Define a `FakeStoreRaising` variant that raises a configurable exception on every method (optionally allowing some methods to succeed).
3. Use `monkeypatch.setattr(service_module, "store_name", FakeStore(...))` in each test.

### `test_emails_service.py` mocking pattern

This file uses a different approach from the Fake store pattern above. Instead of inline Fake stores, it relies on helper functions that monkeypatch module-level functions and build an `EmailManager` with `FakeEmailClient` instances from `tests/shared/email_fakes.py`:

- `_patch_common()` — void function that applies ~12 monkeypatches covering `ensure_mailbox_access`, `account_store.list_by_mailbox`, `account_store.get`, `load_wrapped_app_credentials`, `load_wrapped_account_tokens`, `account_store.upsert_tokens`, `build_manager_for_accounts`, and persistence helpers (`persist_email_metadata_batch`, `delete_email_metadata_batch`, `update_email_metadata_labels_batch`, `load_sync_cursors`, `update_sync_cursor`). Does not return an `EmailManager`.
- `_patch_read_status()` — independent function (does not extend `_patch_common()`). Applies a **narrower** patch set than `_patch_common`: it omits `account_store.get` and the persistence helpers (read-status doesn't need single-account lookup or metadata persistence), and adds `update_email_read_status_batch`. Accepts an optional `accounts` parameter for multi-account scenarios.
- `_patch_spam()` — independent function (does not extend `_patch_common()`). Applies the same narrower patch set as `_patch_read_status` (also omitting `account_store.get`) and adds `update_email_spam_status_batch`.

These helpers centralize the monkeypatching so individual test functions stay concise — they call one helper, then exercise the service function under test.

**Per-service `_patch_common`**: each service test file owns its own `_patch_common`, tailored to that service's dependencies. The one in `test_drafts_service.py` patches `draft_store.create` instead of the email persistence helpers, and does not patch `account_store.list_by_mailbox` (drafts only ever look up a single account). Do not copy `_patch_common` verbatim across files — match the patch set to the service's actual dependencies.

### `_patch_get_content_common`

`_patch_get_content_common` in `test_emails_service.py` patches `ensure_mailbox_access`, `account_store.get`, `load_wrapped_app_credentials`, `load_wrapped_account_tokens`, `account_store.upsert_tokens`, `build_manager_for_accounts`, and **`persist_email_content`** (the cache-write helper). It does **not** patch `get_email_content` itself — each test inside `TestGetEmailFullContent` patches `get_email_content` independently to control whether the test exercises the cache-hit or cache-miss branch.

### Shared fakes

`tests/shared/database_fakes.py` provides `FakeCursor`, `FakeConnection`, `patch_connection`, and `patch_connection_error` — used by all database repository unit tests.

`tests/shared/email_fakes.py` provides `FakeEmailClient`, `build_metadata`, and `DraftMetadata`-aware draft simulation. The constructor accepts injection kwargs for every operation it supports, including:
- `auth_exc`, `auth_silent_exc`, `auth_return`, `auth_silent_return` — control authentication paths.
- `fetch_exc`, `send_exc`, `verify_exc`, `delete_exc`, `restore_exc`, `move_to_trash_exc`, `update_read_status_exc`, `move_to_spam_exc`, `restore_from_spam_exc`, `fetch_content_exc`, `create_draft_exc` — raise on the corresponding operation.
- `create_draft_return: DraftMetadata | None` — override the return value of `create_draft`. Default is a deterministic `DraftMetadata(provider_draft_id="fake_draft_1", ...)`.
- `create_draft_calls` — list field that records every `create_draft` invocation as a 5-tuple `(to, cc, bcc, subject, body_html)` for assertion-based verification of payload propagation.

### Trash management coverage

- `manage_trash` service function is covered by `TestManageTrash` in `test_emails_service.py`.
- Trash helpers (`load_stored_message_ids`, `get_trash_emails_by_ids`, `mark_as_deleted_batch`, `restore_from_trash_batch`, `restore_from_trash_discovered_batch`, `move_to_trash_batch`) are covered in `test_services_helpers.py`.
- `is_auth_error`, `unwrap_secret`, `_wrap_secret` utility functions are also covered in `test_services_helpers.py`.

### Move-to-trash coverage

- `move_to_trash` service function is covered by `TestMoveToTrash` in `test_emails_service.py`.
- `move_to_trash_batch` helper is covered in `test_services_helpers.py`.
- `GmailClient.move_to_trash` is covered by `TestMoveToTrash` in `test_gmail_client.py`.
- `OutlookClient.move_to_trash` is covered by `TestMoveToTrash` in `test_outlook_client.py`.
- `EmailManager.move_to_trash` delegation is covered by standalone functions (`test_move_to_trash_delegates_to_client`, `test_move_to_trash_unknown_label_raises`) in `test_email_manager.py`.
- `PgEmailMetadataStore.move_to_trash_batch` is covered in `test_email_metadata_repository.py`.

### Spam operations coverage

- `move_to_spam` and `restore_from_spam` service functions are covered by `TestMoveToSpam` and `TestRestoreFromSpam` in `test_emails_service.py`.
- `update_email_spam_status_batch` helper is covered in `test_services_helpers.py`.
- `GmailClient.move_to_spam` and `restore_from_spam` are covered in `test_gmail_client.py`.
- `OutlookClient.move_to_spam` and `restore_from_spam` are covered in `test_outlook_client.py`.
- `EmailManager.move_to_spam` and `restore_from_spam` delegation is covered in `test_email_manager_extended.py`.
- `PgEmailMetadataStore.update_spam_status_batch` is covered in `test_email_metadata_repository.py`.

### Email listing coverage

- `list_emails` service function is covered by `TestListEmails` in `test_emails_service.py` (8 tests: single account happy path, unified view, account not found, DB errors on lookup/query, unexpected error, empty result).
- `PgEmailMetadataStore.list_by_account_and_box` and `list_by_mailbox_and_box` are covered in `test_email_metadata_repository.py` (5 tests each: happy path, invalid text, psycopg2 error, generic error, connection pool error propagation).

### Email content coverage

- `TestGetEmailFullContent` in `test_emails_service.py`: 6 tests covering DB hit, DB miss with provider fetch, HTML sanitization, account not found, core error translation, best-effort persist failure. See the `_patch_get_content_common` description above for the patch set.
- `test_sanitize.py`: tests for `sanitize_email_html` -- strips scripts, preserves safe tags, strips event handlers, blocks javascript href, allows mailto/cid protocols, handles empty/whitespace input, strips onerror on img, strips style tag.
- `test_email_content_repository.py`: 10 tests for `PgEmailContentStore` (get/upsert with error wrapping, InvalidTextRepresentation handling).
- `TestGetEmailContent` and `TestPersistEmailContent` in `test_services_helpers.py`: 3 tests each covering happy path, DatabaseError translation, and generic exception fallback.
- `EmailManager.fetch_email_content` delegation is covered by 4 standalone functions in `test_email_manager_extended.py`: happy path, account not found, CoreError passthrough, unexpected exception wrapping.

### Drafts creation coverage

- `TestCreateDraft` in `test_drafts_service.py` covers `drafts_service.create_draft` end-to-end at the unit level. Tests include: happy path (with timestamp assertions), empty draft, account not found, mailbox access denied (`Forbidden`), provider `EmailExternalAPIError` translation, provider generic `RuntimeError` (manager wraps to `EmailExternalAPIError`), silent auth `EmailAuthError` → `AccountNotConnected`, DB persist `DatabaseError` translation, DB persist generic `RuntimeError` → `DraftCreationError`, account lookup `DatabaseError` translation, account lookup generic `RuntimeError` → `DraftCreationError`, payload field forwarding, non-auth `CoreError` (`EmailExternalAPIError` from `authenticate_silent`) → `ExternalAPIError`, `_persist_refreshed_tokens` happy path, `_persist_refreshed_tokens` `DatabaseError` translation, `_persist_refreshed_tokens` generic exception → `DraftCreationError`, outer safety net (`load_wrapped_app_credentials` raising → `DraftCreationError`), and `None`-field coalescing in `DraftOut`.
- The test file's `_patch_common` is service-specific: it patches `draft_store.create` (instead of email persistence helpers) and does not include `account_store.list_by_mailbox`.
- The `_persisted_row()` factory keeps the deterministic timestamp `datetime(2024, 1, 1, 12, 0, 0)` so the happy path can assert exact equality.
