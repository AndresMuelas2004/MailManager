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

### Email address column

The `email_address` column (added in migration `0009`) stores the connected account's email address as plain text. It is not encrypted because it is not a secret. It is written during `upsert_tokens` and may be `NULL` if the email fetch was unsuccessful. The UPSERT queries use `COALESCE(%(email_address)s, email_address)` to prevent silent-refresh upserts (which don't carry an email) from erasing a previously stored value.

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

Added in migration `0008` to the `box` CHECK constraint. Acts as a soft-delete marker for emails deleted from trash. The sync pipeline's `UPSERT_EMAIL_METADATA_BATCH` and `UPDATE_LABELS_BATCH` queries use a `CASE` expression to prevent the provider's `TRASH` status **specifically** from overwriting a `DELETED` row. Any other incoming box value (`ALL_MAIL`, `SENT`, `SPAM`) does overwrite `DELETED` — this is intentional because it means the user restored the email at the provider.

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
- **`upsert_batch(account_id, rows) → int`** — bulk-upserts email metadata. Uses a `CASE` expression to protect rows with `box = 'DELETED'` from being overwritten by provider sync.

## Behavioral Contracts — Email Metadata

### `EmailMetadataStore.update_read_status_batch(account_id, rows) → int`

Batch-updates the `is_read` column for existing email metadata rows. Uses a dedicated SQL query (`UPDATE_READ_STATUS_BATCH`) that only touches `is_read` — it does **not** modify the `box` column. This is intentionally separate from `update_labels_batch`, because read-status updates should never change box classification. `rows` format: `list[tuple]` of `(provider_message_id, account_id, is_read)`. Returns the number of rows updated.

### `EmailMetadataStore.list_by_account_and_box(account_id, box) → list[dict]`

Returns email metadata rows for a single account filtered by the exact `box` value. Ordered by `received_at DESC`. Because the filter uses equality (`box = %(box)s`), `DELETED` rows are excluded implicitly when the caller passes any non-`DELETED` box value.

### `EmailMetadataStore.list_by_mailbox_and_box(mailbox_id, box) → list[dict]`

Returns email metadata rows across all accounts in a mailbox, filtered by the exact `box` value. JOINs `email_metadata` with `accounts` on `account_id` and filters by `accounts.mailbox_id`. Ordered by `received_at DESC`. This is the only `EmailMetadataStore` method whose first parameter is `mailbox_id` rather than `account_id` — this is intentional because the query operates across all accounts in a mailbox.

### `EmailMetadataStore.update_spam_status_batch(account_id, rows) → int`

Batch-updates the `provider_message_id` and `box` columns for existing email metadata rows. Uses `UPDATE_SPAM_STATUS_BATCH` which matches on the old `provider_message_id` + `account_id` and sets both the new `provider_message_id` and new `box`. This is needed because Outlook's `/move` API returns a new message ID when moving between folders. `rows` format: `list[tuple]` of `(old_message_id, account_id, new_message_id, new_box)`. Returns the number of rows updated.

## Behavioral Contracts — Email Content

### `EmailContentStore`

Stores the full HTML/text body of individual emails in a separate `email_content` table (not columns on `email_metadata`). This separation keeps `email_metadata` lightweight for listing queries.

- **`get(account_id, provider_message_id) → dict | None`** — returns `{html_body, text_body, fetched_at}` or `None` if not cached. Handles `InvalidTextRepresentation` gracefully (returns `None` for invalid UUIDs).
- **`upsert(account_id, provider_message_id, html_body, text_body) → None`** — inserts or updates the cached content. Uses `ON CONFLICT ... DO UPDATE` to overwrite `html_body`, `text_body`, and set `fetched_at = now()`.

No delete methods in the contract — deletion happens via `ON DELETE CASCADE` (when the parent account is deleted) or via inline SQL in cleanup scripts (`Scripts/cli_utilities/clear_email_content.py`).

The `email_content` table has the same composite PK as `email_metadata` (`provider_message_id, account_id`) but no FK to `email_metadata` — content can exist independently (orphaned content is harmless).

## Behavioral Contracts — Drafts

### `drafts` table (migration 0012)

Stores provider-backed draft emails in a separate table from `email_metadata` because: (1) drafts are created via a different API path, (2) recipients require `TEXT[]` arrays (`email_metadata` only has scalar `from_email`), and (3) drafts may exist at the provider without ever being sent.

Schema:
- Composite PK: `(provider_draft_id, account_id)` — analogous to `email_metadata`. The `provider_draft_id` is always present because the application follows the Provider-First Rule (provider creates the draft and returns its ID before any local persistence).
- FK: `account_id REFERENCES accounts(account_id) ON DELETE CASCADE`. There is **no direct FK to `mailboxes`** — `accounts.mailbox_id` provides the chain.
- Recipients are stored as `TEXT[] NOT NULL DEFAULT '{}'` for `to_recipients`, `cc_recipients`, `bcc_recipients`. psycopg2 transparently maps Python `list[str]` to PostgreSQL `TEXT[]`.
- `subject TEXT NOT NULL DEFAULT ''` and `body_html TEXT NOT NULL DEFAULT ''`. Empty drafts are valid (no `min_length` constraint).
- `created_at` and `updated_at` use `TIMESTAMPTZ NOT NULL DEFAULT now()`. This default applies to **`DraftStore.create`** (insert from scratch via `INSERT_DRAFT`, which does not list these columns — so the DB default fires). For `DraftStore.replace_all_for_account`, the caller passes provider-reported timestamps explicitly (see that section below) so they override the default on INSERT.
- Index: `idx_drafts_account_id ON drafts(account_id)`.

### `DraftStore.create(draft) → dict`

Inserts a new draft row using `INSERT_DRAFT` (defined in `queries/drafts.py`). The query uses `RETURNING` to bring back all columns including DB-generated `created_at` and `updated_at`. The repository (`PgDraftStore`) maps the row through `_row_to_dict`, which casts `account_id` to `str` and ensures recipient arrays are never `None`. Raises `QueryError` on any SQL failure or unexpected exception (the generic `except Exception` fallback also raises `QueryError`, keeping the contract uniform).

**Return contract**: always a populated dict. The method does NOT return an empty dict when `RETURNING` yields no row — that is a programming error and will surface as `TypeError` from `_row_to_dict(None)`, which the service layer's outer `except Exception` converts to `DraftCreationError`.

**Error handling guard order**: the method follows the capture technique from `database/CLAUDE.md` §7. The `try` block contains `connection.get_connection()` which can raise a `DatabaseError` subclass (`ConnectionPoolError`), so the method **must** have `except DatabaseError: raise` before the `except psycopg2.Error` / `except Exception` catches — otherwise a pool exhaustion would be silently re-wrapped as `QueryError`. The current implementation has this guard in all four `DraftStore` methods.

### `DraftStore.list_by_account(account_id) → list[dict]`

Returns all draft rows for a single account, ordered by `created_at DESC`. Uses `LIST_DRAFTS_BY_ACCOUNT` (filter on `drafts.account_id`, index-backed by `idx_drafts_account_id`). Returns `[]` if the UUID is malformed (`InvalidTextRepresentation`) so the service can treat "unknown account" as an empty result rather than a 500. Raises `QueryError` on other SQL failures or unexpected exceptions.

Each row is mapped through `_row_to_dict`, which casts `account_id` UUID → `str` and ensures `to_recipients`/`cc_recipients`/`bcc_recipients` are never `None` (coalesced to `[]`).

### `DraftStore.list_by_mailbox(mailbox_id) → list[dict]`

Returns all draft rows across every account that belongs to the mailbox, ordered by `created_at DESC`. Uses `LIST_DRAFTS_BY_MAILBOX` which JOINs `drafts` with `accounts` on `account_id` and filters by `accounts.mailbox_id` (there is no `mailbox_id` column on `drafts`). Same error semantics and row-mapping as `list_by_account`.

### `DraftStore.replace_all_for_account(account_id, drafts) → int`

Atomic upsert + delete-missing. Inside a single transaction:

1. If `drafts` is non-empty, batch-upsert all rows via `psycopg2.extras.execute_values` + the `UPSERT_DRAFTS_BATCH` query. **Each row tuple includes `created_at` and `updated_at` passed by the caller** (the service forwards the provider-reported timestamps from `DraftMetadata.created_at` / `DraftMetadata.updated_at`). The reason for passing provider timestamps is so that freshly-inserted rows preserve the "first time seen at provider" semantics — the DB's `DEFAULT now()` would otherwise set both timestamps to the sync time, losing information about when the draft originally existed at the provider. `ON CONFLICT (provider_draft_id, account_id) DO UPDATE` refreshes `to_recipients`, `cc_recipients`, `bcc_recipients`, `subject`, `body_html`, and sets `updated_at = now()`. **`created_at` is NOT touched on conflict** — it preserves the "first time we saw this draft locally" semantics (even across multiple syncs).
2. Executes `DELETE_DRAFTS_MISSING_FOR_ACCOUNT` — removes any draft row for this account whose `provider_draft_id` is not in the new list. This step runs **even when `drafts == []`**, in which case it deletes every draft for the account (intentional: an empty provider response means "no drafts here anymore").

Returns `len(drafts)`. Raises `QueryError` on SQL or unexpected failures. Invalid `account_id` format raises `QueryError` (wrapped from `InvalidTextRepresentation`).

The service layer (`drafts_service.sync_drafts`) calls this method per account after fetching drafts from the provider. The result is that local `drafts` rows for that account exactly match the provider's current state — stale drafts deleted, matching drafts updated, new drafts inserted.

The contract intentionally exposes only `create`, `list_by_account`, `list_by_mailbox`, and `replace_all_for_account` for now — update, send, and delete methods will be added incrementally as the corresponding drafts endpoints are implemented.

## Project-Specific Error Hierarchy

Full tree of exceptions defined in `errors/exceptions.py`:

```
DatabaseError
├── ConnectionPoolError
├── QueryError
├── MigrationError
├── SettingsError
├── TokenCryptoError
│   ├── TokenDecryptError
│   └── TokenEncryptError
├── TokenValidationError
├── CredentialReadError
└── UnknownProviderError
```

## Extension

### Adding a new provider or migration

Whenever a new Alembic migration is created in `migrations/versions/`, **`migrations/runner.py` must be updated in the same change**: add the equivalent DDL to `_DDL_STATEMENTS` and advance the stamp at the bottom to the new migration name. Forgetting this step silently breaks any environment that relies on the fallback runner (local setup without Alembic, some CI configurations).

**Provider-specific changes** (only when adding a new email provider):

1. Register the provider env var in `settings.py` (`_PROVIDER_CREDENTIALS_ENV_VARS`).
2. Add provider-specific JSON parsing in `security/app_credentials.py` if needed.
3. Update provider validation constraints via a new Alembic migration.
4. Update fallback runner (`migrations/runner.py`) with the new DDL and stamp the latest migration version — see the rule above.
5. Add/adjust integration and E2E tests for connect, send, and inbox flows.
