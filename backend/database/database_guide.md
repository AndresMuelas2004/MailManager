> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# Database Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### Token security model

- Token columns (`access_token_encrypted`, `refresh_token_encrypted`, etc.) live directly in the `accounts` table (merged from a separate `tokens` table in migration 0005).
- New token writes are always encrypted via Fernet (`TOKEN_ENCRYPTION_KEY` + `TOKEN_ENCRYPTION_KEY_ID`).
- Token reads validate full account context (`account_id + mailbox_id + provider`).
- Legacy plaintext fallback is controlled by `TOKEN_PLAINTEXT_FALLBACK_ENABLED`.
- On legacy plaintext read, account store attempts lazy backfill to encrypted columns.

### Deprecation note

The plaintext token columns (`access_token`, `refresh_token`) remain temporarily for migration compatibility. A future migration should remove them once legacy data is fully backfilled.

## Behavioral Contracts — Traps to Avoid

### `AccountStore.get_tokens()`

- Returns `None` when no usable token exists (no row, encrypted columns absent with fallback disabled, etc.). It **never raises** business-level exceptions for missing-token scenarios — the service layer maps `None` to `AccountNotConnected`. Input validation errors (`TokenValidationError` for blank provider) still propagate; only missing-token scenarios return `None`.
- `_backfill_plaintext_tokens` is best-effort: failures are logged as warnings and never propagate. The backfill retries on the next read.
- A malformed `TOKEN_ENCRYPTION_KEY` raises `SettingsError` immediately via `get_fernet()` — it is never silently treated as "key absent".

## Trash Management — `DELETED` Box and `previous_box` Column

### `previous_box` column

Added in migration `0008`. Nullable `VARCHAR(20)` with CHECK constraint allowing `ALL_MAIL`, `SENT`, `SPAM`. Set by `move_to_trash_batch`, which copies the current `box` into `previous_box` before setting `box = 'TRASH'`. On restore, `restore_from_trash_batch` uses `COALESCE(previous_box, 'ALL_MAIL')` for rows with a known value. Rows where `previous_box` is `NULL` go through `restore_from_trash_discovered_batch`, which receives the actual box from the caller (discovered at the provider after restore).

### `DELETED` box value

Added in migration `0008` to the `box` CHECK constraint. Acts as a soft-delete marker for emails deleted from trash. The sync pipeline's `UPSERT_EMAIL_METADATA_BATCH` and `UPDATE_LABELS_BATCH` queries use a `CASE` expression to prevent the provider's `TRASH` status from overwriting a `DELETED` row. If the provider reports a box other than `TRASH`, it means the user restored the email at the provider and the row is updated.

### `LIST_BY_ACCOUNT` filter

`LIST_BY_ACCOUNT` excludes `DELETED` rows (`box != 'DELETED'`) so they don't appear in the user's email list.

### `EmailMetadataStore` trash method contracts

- **`mark_as_deleted_batch(account_id, message_ids) → int`** — soft-deletes by setting `box = 'DELETED'`. **Only updates rows where `box = 'TRASH'`** — if a row has a different box, it is silently skipped. Returns count of affected rows.
- **`restore_from_trash_batch(account_id, rows) → int`** — restores emails: replaces `provider_message_id` with the new ID from the provider, sets `box` from `COALESCE(previous_box, 'ALL_MAIL')`, and clears `previous_box`. **Only updates rows where `box = 'TRASH'`** — rows with a different box are silently skipped. Each tuple in `rows` is `(old_id, new_id, account_id)`.
- **`restore_from_trash_discovered_batch(account_id, rows) → int`** — same as `restore_from_trash_batch` but for rows where `previous_box` was `NULL`. Instead of reading `COALESCE(previous_box, ...)` from the DB, it receives the discovered box from the caller as part of each tuple. Each tuple in `rows` is `(old_id, new_id, account_id, discovered_box)`. **Only updates rows where `box = 'TRASH'`**.
- **`move_to_trash_batch(account_id, rows) → int`** — replaces `provider_message_id` with the new ID from the provider (Outlook assigns a new ID on move), copies the current `box` into `previous_box`, and sets `box = 'TRASH'`. Each tuple in `rows` is `(old_id, new_id, account_id)`. **Only updates rows where `box` is NOT already `'TRASH'` or `'DELETED'`** — rows already in trash or deleted are silently skipped. Returns count of affected rows.

`restore_from_trash_batch`, `restore_from_trash_discovered_batch`, and `move_to_trash_batch` all delegate to the internal `_execute_batch_values` helper, which wraps `psycopg2.extras.execute_values` with standard error handling.

- **`delete_batch_by_message_ids(account_id, message_ids) → int`** — **hard-deletes** rows permanently. Used by ghost email reconciliation, NOT by user-facing trash operations. Do not confuse with `mark_as_deleted_batch` (soft-delete).
- **`get_trash_emails_by_ids(account_id, message_ids) → list[dict]`** — returns rows where `box = 'TRASH'` matching the given IDs. Each dict includes `provider_message_id`, `account_id`, `box`, and `previous_box`. Used to verify emails are in trash before acting.
- **`list_provider_message_ids(account_id) → list[str]`** — returns all stored `provider_message_id` values for an account. Used by ghost email reconciliation.
- **`update_labels_batch(account_id, rows) → int`** — bulk-updates `is_read` and `box` for email metadata. Uses the same `CASE` expression as `UPSERT_EMAIL_METADATA_BATCH` to protect `DELETED` rows from being reverted to `TRASH` by provider sync.

## Behavioral Contracts — Email Metadata

### `EmailMetadataStore.update_read_status_batch(account_id, rows) → int`

Batch-updates the `is_read` column for existing email metadata rows. Uses a dedicated SQL query (`UPDATE_READ_STATUS_BATCH`) that only touches `is_read` — it does **not** modify the `box` column. This is intentionally separate from `update_labels_batch`, because read-status updates should never change box classification. `rows` format: `list[tuple]` of `(provider_message_id, account_id, is_read)`. Returns the number of rows updated.

### `EmailMetadataStore.update_spam_status_batch(account_id, rows) → int`

Batch-updates the `provider_message_id` and `box` columns for existing email metadata rows. Uses `UPDATE_SPAM_STATUS_BATCH` which matches on the old `provider_message_id` + `account_id` and sets both the new `provider_message_id` and new `box`. This is needed because Outlook's `/move` API returns a new message ID when moving between folders. `rows` format: `list[tuple]` of `(old_message_id, account_id, new_message_id, new_box)`. Returns the number of rows updated.

## Extension

### Adding a new provider

1. Register the provider env var in `settings.py` (`_PROVIDER_CREDENTIALS_ENV_VARS`).
2. Add provider-specific JSON parsing in `security/app_credentials.py` if needed.
3. Update provider validation constraints via a new Alembic migration.
4. Add/adjust integration and E2E tests for connect, send, and inbox flows.
