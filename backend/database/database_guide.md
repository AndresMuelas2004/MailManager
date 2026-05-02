> **Permanent rule — read before editing this file.**
>
> This file is loaded into context on every Claude session. A line here only justifies its tokens if it cannot be reconstructed by reading the code.
>
> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**
> - **YES → delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.
> - **NO → keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, magic constants) that cannot be recomputed — those earn their tokens.
>
> **When updating this file, re-read every section and delete anything that has since migrated into the code.** Staleness is worse than silence.

# Database Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Token security model

- Token columns (`access_token_encrypted`, `refresh_token_encrypted`, …) live directly on the `accounts` table (merged from a separate `tokens` table in migration 0005).
- **All new writes are encrypted** via Fernet (`TOKEN_ENCRYPTION_KEY` + `TOKEN_ENCRYPTION_KEY_ID`).
- A malformed `TOKEN_ENCRYPTION_KEY` raises `SettingsError` **immediately** from `get_fernet()` — never silently treated as "key absent". Do not add a fallback here.
- `TOKEN_PLAINTEXT_FALLBACK_ENABLED` toggles whether legacy plaintext columns are still read. On a plaintext hit, `AccountStore` attempts a best-effort lazy backfill to the encrypted columns. The backfill **never propagates failures** — it logs a warning and retries on the next read.
- The plaintext columns (`access_token`, `refresh_token`) are **deprecated** and remain only for migration compatibility. A future migration will remove them once legacy data is fully backfilled.

## `email_address` column (migration 0009)

- Plain text, **not encrypted** — it is not a secret.
- Written during `upsert_tokens`; may be `NULL` if the best-effort provider fetch during `authenticate` failed.
- The UPSERT queries use `COALESCE(%(email_address)s, email_address)` so silent-refresh upserts (which don't carry an `email_address` — only the interactive `authenticate` flow fetches it) cannot erase a previously stored value. **Do not remove the `COALESCE` thinking it is a leftover** — it is load-bearing; without it, any refresh blanks the column.

## `AccountStore.get_tokens()` returns `None` instead of raising

Missing-token scenarios (no row, encrypted columns absent with fallback disabled, etc.) return `None`. The service layer maps `None → AccountNotConnected`. **Input-validation** errors (`TokenValidationError` for blank provider) still propagate — only the absence of a token is expressed as `None`.

## Trash — `previous_box` + `DELETED` box value (migration 0008)

- `previous_box VARCHAR(20)` nullable, CHECK allows `ALL_MAIL`, `SENT`, `SPAM`. `move_to_trash_batch` copies the current `box` into `previous_box` before setting `box = 'TRASH'`. `restore_from_trash_batch` uses `COALESCE(previous_box, 'ALL_MAIL')`. Rows where `previous_box IS NULL` go through `restore_from_trash_discovered_batch`, which receives the discovered box from the caller.
- `DELETED` is a new allowed value in the `box` CHECK. Soft-delete marker for emails removed from trash via the no-op `delete_messages` path (see `core_guide.md`). The `CASE` expression in `UPSERT_EMAIL_METADATA_BATCH` and `UPDATE_LABELS_BATCH` **preserves `DELETED` when the incoming provider box is `TRASH`** (would undo the user's explicit delete), but **overwrites `DELETED` on any other incoming box** — interpreted as "the user restored it manually at the provider". Don't simplify this CASE into a plain `EXCLUDED.box` assignment.

## `EmailMetadataStore` — trash batch guardrails

Every trash-related batch method adds a **box-state precondition** directly in the SQL — these are not client-side checks, they're WHERE clauses:

- `mark_as_deleted_batch`, `restore_from_trash_batch`, `restore_from_trash_discovered_batch` → **only update rows where `box = 'TRASH'`**. Rows in a different box are silently skipped (race-condition safety — if a sync meanwhile moved the row out of trash, the trash operation must not touch it).
- `move_to_trash_batch` → **only updates rows where `box` is NOT already `'TRASH'` or `'DELETED'`** — idempotent move, and does not downgrade a soft-deleted row back to trash.

`restore_from_trash*` and `move_to_trash_batch` all delegate to `_execute_batch_values`, which wraps `psycopg2.extras.execute_values` with the standard error handling.

## `email_content` composite FK (migration 0013) + `EmailMetadataStore.exists`

`email_content` uses the **shared primary key pattern**: composite PK `(provider_message_id, account_id)` + composite FK to `email_metadata(provider_message_id, account_id) ON DELETE CASCADE` (constraint `email_content_metadata_fkey`). No direct FK to `accounts` — the cascade chain `accounts → email_metadata → email_content` is fully transitive, so account deletion still wipes both tables.

**Service-layer contract:** because the FK target is `email_metadata`, `get_email_full_content` **must** verify the metadata row exists before any `email_content` upsert — otherwise the upsert surfaces as `ForeignKeyViolation → 500`. `EmailMetadataStore.exists(account_id, provider_message_id)` is the lightweight probe (`SELECT 1 … LIMIT 1`) used for the pre-check. It handles `InvalidTextRepresentation` gracefully (returns `False` for malformed UUIDs) so bad inputs surface as 404 instead of 500.

## `DraftStore` — contract invariants

- **Composite PK `(provider_draft_id, account_id)`.** Every `get` / `update` / `delete` takes both; single-arg overloads do not exist. `provider_draft_id` is always present because the repo follows the Provider-First Rule (the provider creates the draft and returns its ID before any local persistence).
- **`DatabaseError` re-raise guard is mandatory in every method.** The pattern is `except DatabaseError: raise` **before** `except psycopg2.Error` / `except Exception`. `connection.get_connection()` can raise `ConnectionPoolError` (a `DatabaseError` subclass) — without this guard, pool exhaustion gets re-wrapped as `QueryError` and disappears from the error signal.
- **`UPDATE ... RETURNING` yielding no row → `QueryError("Draft row to update not found.")`.** Defensive check for a race where another caller deleted the draft between the service's pre-check (`DraftStore.get`) and the update/delete. Without the explicit raise, the operation would silently succeed with a `None` return.
- **`list_by_account` / `list_by_mailbox` / `get` return `[]` / `None` on malformed UUID** (`InvalidTextRepresentation`) so service code can treat "unknown account" as an empty result instead of a 500. `delete` intentionally does **not** have this guard — a malformed UUID there is a programming error and must surface.

## `DraftStore.replace_all_for_account` — atomic upsert + delete-missing

Single transaction:

1. Non-empty `drafts` → `psycopg2.extras.execute_values` with `UPSERT_DRAFTS_BATCH`. Each tuple carries the caller-provided `created_at` / `updated_at` (the service forwards `DraftMetadata.created_at` / `.updated_at`), so freshly inserted rows preserve "first-time-seen-at-provider" semantics instead of collapsing both timestamps to `now()`. `ON CONFLICT (provider_draft_id, account_id) DO UPDATE` refreshes recipients + subject + body + `updated_at = now()`, but **never touches `created_at`** — it preserves "first time we saw this draft locally", even across multiple syncs.
2. `DELETE_DRAFTS_MISSING_FOR_ACCOUNT` runs **unconditionally, even when `drafts == []`** — intentional: an empty provider response means "no drafts here anymore", so local state is wiped for that account. Do not add a guard to skip the DELETE on empty input.

Invalid `account_id` format raises `QueryError` (wrapped from `InvalidTextRepresentation`).

## `drafts` table invariants (migration 0012)

- Recipients stored as `TEXT[] NOT NULL DEFAULT '{}'`. psycopg2 maps Python `list[str]` ↔ PostgreSQL `TEXT[]` transparently.
- `subject` and `body_html` are `TEXT NOT NULL DEFAULT ''` — empty drafts are valid.
- `created_at` / `updated_at` are `TIMESTAMPTZ NOT NULL DEFAULT now()`. The `DEFAULT now()` fires only for `INSERT_DRAFT` (which doesn't list these columns). `UPSERT_DRAFTS_BATCH` always passes them explicitly from provider-reported timestamps.

## `LIST_FILTERED` traps (email metadata search)

- **`unaccent` is a runtime dependency.** The query wraps both columns and the search pattern in `unaccent(lower(...))`. The function is provided by the `unaccent` PostgreSQL extension, enabled once via migration `0020_create_extension_unaccent`. Any environment that bypasses migrations (e.g. a manually restored DB dump) raises `function unaccent(text) does not exist` at query time, not at startup — extension state is checked lazily by the planner.
- **`account_ids` MUST be cast to `uuid[]` in the SQL.** psycopg2 sends a Python `list[str]` as `text[]`, and `account_id = ANY(%(account_ids)s)` without the explicit `::uuid[]` cast raises `operator does not exist: uuid = text`. Removing the cast is silently fine for empty lists (the repository short-circuits before the query) and breaks the moment any account is supplied.

## Extension

### Whenever a new Alembic migration is created

**`migrations/runner.py` must be updated in the same change**: append the equivalent DDL to `_DDL_STATEMENTS` and advance the stamp at the bottom to the new migration name. Forgetting this silently breaks any environment that relies on the fallback runner (local setup without Alembic, some CI configurations). Data-only migrations also belong here — e.g. migration 0014 adds `TRUNCATE TABLE email_content;` immediately before the stamp line, and every subsequent `email_content`-invalidating migration follows the same shape (see `repository_guide.md` § "Email HTML rendering cache"). Pure DDL extensions (e.g. migration 0020 adds `CREATE EXTENSION IF NOT EXISTS unaccent;`) do **not** require a `TRUNCATE` — only schema changes that invalidate cached HTML do.

### Adding a new email provider

1. Register the provider env var in `settings.py::_PROVIDER_CREDENTIALS_ENV_VARS`.
2. Extend `security/app_credentials.py` if the provider needs custom JSON parsing.
3. Update the provider CHECK constraint via a new Alembic migration (+ fallback runner per rule above).
4. Add/adjust integration and E2E coverage for connect, send, and inbox flows.
