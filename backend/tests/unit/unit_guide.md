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

Tests for service modules (`test_accounts_service.py`, `test_mailboxes_service.py`, `test_auth_service.py`) use inline Fake store classes (e.g. `FakeAccountStore`, `FakeMailboxStore`) combined with `monkeypatch.setattr` to replace the real store module attributes. This avoids database access entirely and allows precise control over success/failure paths. The pattern:

1. Define a `FakeStore` class with the same method signatures as the real store.
2. Define a `FakeStoreRaising` variant that raises a configurable exception on every method (optionally allowing some methods to succeed).
3. Use `monkeypatch.setattr(service_module, "store_name", FakeStore(...))` in each test.

### Database fakes

`tests/shared/database_fakes.py` provides `FakeCursor`, `FakeConnection`, `patch_connection`, and `patch_connection_error` — used by all database repository unit tests. Less discoverable than `tests/shared/email_fakes.py` (which provides `FakeEmailClient` and `build_metadata`).

### Trash management coverage

- `manage_trash` service function is covered by `TestManageTrash` in `test_emails_service.py`.
- The 4 trash helpers (`load_stored_message_ids`, `get_trash_emails_by_ids`, `mark_as_deleted_batch`, `restore_from_trash_batch`) are covered in `test_services_helpers.py`.
- `is_auth_error`, `unwrap_secret`, `_wrap_secret` utility functions are also covered in `test_services_helpers.py`.

### Move-to-trash coverage

- `move_to_trash` service function is covered by `TestMoveToTrash` in `test_emails_service.py`.
- `move_to_trash_batch` helper is covered in `test_services_helpers.py`.
- `GmailClient.move_to_trash` is covered by `TestMoveToTrash` in `test_gmail_client.py`.
- `OutlookClient.move_to_trash` is covered by `TestMoveToTrash` in `test_outlook_client.py`.
- `EmailManager.move_to_trash` delegation is covered by standalone functions (`test_move_to_trash_delegates_to_client`, `test_move_to_trash_unknown_label_raises`) in `test_email_manager.py`.
- `PgEmailMetadataStore.move_to_trash_batch` is covered in `test_email_metadata_repository.py`.
