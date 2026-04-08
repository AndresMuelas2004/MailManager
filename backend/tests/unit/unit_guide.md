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

Unit tests cover: `core/email` (clients, manager, helpers, errors), `database` (settings, token crypto, repositories, credentials, connection, lifecycle), `api/services` (auth, emails, accounts, mailboxes, error translation, helpers), and `auth` (settings).

### Service test pattern: Fake stores with monkeypatch

Tests for service modules (`test_accounts_service.py`, `test_mailboxes_service.py`) use inline Fake store classes (e.g. `FakeAccountStore`, `FakeMailboxStore`) combined with `monkeypatch.setattr` to replace the real store module attributes. This avoids database access entirely and allows precise control over success/failure paths. The pattern:

1. Define a `FakeStore` class with the same method signatures as the real store.
2. Define a `FakeStoreRaising` variant that raises a configurable exception on every method (optionally allowing some methods to succeed).
3. Use `monkeypatch.setattr(service_module, "store_name", FakeStore(...))` in each test.

### `test_emails_service.py` mocking pattern

This file uses a different approach from the Fake store pattern above. Instead of inline Fake stores, it relies on helper functions that monkeypatch module-level functions and build an `EmailManager` with `FakeEmailClient` instances from `tests/shared/email_fakes.py`:

- `_patch_common()` — void function that applies ~12 monkeypatches covering `ensure_mailbox_access`, `account_store.list_by_mailbox`, `account_store.get`, `load_wrapped_app_credentials`, `load_wrapped_account_tokens`, `account_store.upsert_tokens`, `build_manager_for_accounts`, and persistence helpers (`persist_email_metadata_batch`, `delete_email_metadata_batch`, `update_email_metadata_labels_batch`, `load_sync_cursors`, `update_sync_cursor`). Does not return an `EmailManager`.
- `_patch_read_status()` — independent function (does not extend `_patch_common()`). Re-applies the shared patches independently and adds `update_email_read_status_batch`. Accepts an optional `accounts` parameter for multi-account scenarios.
- `_patch_spam()` — independent function (does not extend `_patch_common()`). Re-applies the shared patches independently and adds `update_email_spam_status_batch`.

These helpers centralize the monkeypatching so individual test functions stay concise — they call one helper, then exercise the service function under test.

### Database fakes

`tests/shared/database_fakes.py` provides `FakeCursor`, `FakeConnection`, `patch_connection`, and `patch_connection_error` — used by all database repository unit tests. Less discoverable than `tests/shared/email_fakes.py` (which provides `FakeEmailClient` and `build_metadata`).

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

- `TestGetEmailFullContent` in `test_emails_service.py`: 6 tests covering DB hit, DB miss with provider fetch, HTML sanitization, account not found, core error translation, best-effort persist failure. Helper `_patch_get_content_common` patches `account_store.get`, `ensure_mailbox_access`, `build_manager_for_accounts`, and `get_email_content` for content endpoint tests.
- `test_sanitize.py`: tests for `sanitize_email_html` -- strips scripts, preserves safe tags, strips event handlers, blocks javascript href, allows mailto/cid protocols, handles empty/whitespace input, strips onerror on img, strips style tag.
- `test_email_content_repository.py`: 10 tests for `PgEmailContentStore` (get/upsert with error wrapping, InvalidTextRepresentation handling).
- `TestGetEmailContent` and `TestPersistEmailContent` in `test_services_helpers.py`: 3 tests each covering happy path, DatabaseError translation, and generic exception fallback.
- `EmailManager.fetch_email_content` delegation is covered by 4 standalone functions in `test_email_manager_extended.py`: happy path, account not found, CoreError passthrough, unexpected exception wrapping.
