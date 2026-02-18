# Database Package (`api/database`)

This package is the PostgreSQL persistence layer for MailManager.
Only this layer should execute SQL or manage database connections.

## Design Goals

- Keep storage concerns isolated from routers, services, and core clients.
- Expose stable interfaces (`MailboxStore`, `AccountStore`) to service modules.
- Centralize connection pooling and transaction behavior.
- Persist OAuth tokens in PostgreSQL, not in per-account local files.

## Public Surface

Consumers should import from `api.database` (package root), not from internal modules.

Re-exported symbols:

- `mailbox_store`
- `account_store`
- `get_connection`
- `init_db`
- `close_pool`
- `load_app_credentials`
- `load_account_tokens`
- `save_account_tokens`
- `delete_account_tokens_for_records`

## Module Breakdown

### `base.py`

Defines abstract contracts:

- `MailboxStore`
- `AccountStore`

These contracts allow replacing the concrete storage implementation with minimal service-layer impact.

### `config.py`

Contains `get_database_url()`.

- Reads `DATABASE_URL` from the environment.
- Raises `EnvVarError` if the variable is missing or empty.

### `db.py`

Connection and schema utilities:

- `ThreadedConnectionPool` is initialized lazily.
- `get_connection()` yields one pooled connection in a context manager.
- Successful block execution commits automatically.
- Exceptions trigger rollback before re-raising.
- `init_db()` executes `schema.sql` at application startup.
- `close_pool()` closes all pooled connections on shutdown.

### `repository.py`

Concrete PostgreSQL implementations:

- `PgMailboxStore`
- `PgAccountStore`

Implementation details:

- Uses `psycopg2` and `RealDictCursor`.
- Uses raw SQL (no ORM).
- Converts UUID and timestamp fields into JSON-serializable strings.
- Wraps database driver exceptions as `DatabaseError`.

Exported singletons used by services:

- `mailbox_store`
- `account_store`

### `token_store.py`

Handles two separate credential domains.

1. App credentials (provider-level OAuth client settings)

- Loaded from JSON files pointed by environment variables.
- Provider mapping is in `_ENV_CREDENTIALS`:
  - `gmail -> MIA_GMAIL_CREDENTIALS_PATH`
  - `outlook -> MIA_OUTLOOK_CREDENTIALS_PATH`

2. Account tokens (user-level OAuth tokens)

- Loaded/saved in PostgreSQL table `tokens`.
- Main functions:
  - `load_account_tokens(...)`
  - `save_account_tokens(...)`
  - `delete_account_tokens_for_records(...)`

Error behavior:

- Unknown provider -> `AccountMisconfigured`
- Missing env var -> `EnvVarError`
- DB or JSON file failures -> `DatabaseError`
- Missing account token row -> `AccountNotConnected`

### `schema.sql`

Defines three tables:

- `mailboxes`
- `accounts`
- `tokens`

Schema characteristics:

- Idempotent DDL (`CREATE TABLE IF NOT EXISTS`).
- UUID primary keys for mailbox and account IDs.
- Provider constraint on `accounts.provider` (`gmail`, `outlook`).
- Foreign keys with `ON DELETE CASCADE`:
  - deleting a mailbox deletes related accounts and tokens
  - deleting an account deletes its token row

## Transaction Model

All repository and token operations run inside `get_connection()` context blocks.

Implications:

- Commit on success.
- Rollback on exception.
- Per-operation transaction boundaries by default.
- In tests, `get_connection()` is monkeypatched to a shared transaction for isolation.

## Operational Notes

- `init_db()` is called from FastAPI lifespan during app startup.
- Connection pool size is currently fixed to `minconn=1`, `maxconn=10`.
- Startup fails fast if `DATABASE_URL` is missing or invalid.
- Token persistence includes `updated_at` refresh on upsert.

## Extension Guidance

When adding a new provider:

1. Add provider env var mapping in `token_store._ENV_CREDENTIALS`.
2. Update `accounts.provider` CHECK constraint in `schema.sql`.
3. Ensure services pass normalized provider names consistently.
4. Add integration and E2E coverage for token load/save behavior.
