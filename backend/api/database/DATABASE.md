# Database Package

This directory contains the PostgreSQL persistence layer for MailManager. It is the only part of the application that communicates directly with the database; all other layers (services, routers, core) interact with data exclusively through the public interface exposed by this package.

## Files

### `__init__.py`

Package entry point. Re-exports every public symbol (`mailbox_store`, `account_store`, token helpers, connection utilities) so that consumers throughout the codebase can import from `api.database` without referencing individual modules.

### `base.py`

Abstract base classes that define the persistence contracts: `MailboxStore` and `AccountStore`. These interfaces guarantee that the rest of the application remains decoupled from the concrete storage engine. Any future migration (e.g. to a different database) only requires a new implementation of these contracts.

### `config.py`

Reads the `DATABASE_URL` environment variable and exposes it through a single helper function. If the variable is missing the application raises an `EnvVarError` at startup, following the same pattern used for provider credential paths.

### `db.py`

Manages the PostgreSQL connection pool (`ThreadedConnectionPool` from psycopg2) and provides two key utilities:

- `get_connection()` — a context manager that borrows a connection from the pool, commits on success, and rolls back on failure.
- `init_db()` — executes `schema.sql` to create the tables if they do not already exist. Called automatically when the FastAPI application starts.

### `repository.py`

Concrete implementations of the `MailboxStore` and `AccountStore` interfaces using SQL queries against PostgreSQL. Exports the singleton instances `mailbox_store` and `account_store` that services use for all mailbox and account CRUD operations.

### `token_store.py`

Handles two distinct concerns:

- **App credentials** (`load_app_credentials`) — reads OAuth client configuration from JSON files pointed to by environment variables (`MIA_GMAIL_CREDENTIALS_PATH`, `MIA_OUTLOOK_CREDENTIALS_PATH`). This logic has not changed from the original implementation.
- **Account tokens** (`load_account_tokens`, `save_account_tokens`, `delete_account_tokens_for_records`) — stores and retrieves per-account OAuth tokens in the `tokens` database table instead of individual JSON files on disk.

### `schema.sql`

The DDL (Data Definition Language) that defines the three core tables: `mailboxes`, `accounts`, and `tokens`. All statements use `CREATE TABLE IF NOT EXISTS`, making execution idempotent. Foreign keys with `ON DELETE CASCADE` ensure referential integrity across the three tables.
