# Database Package (`database`)

This package is the PostgreSQL persistence layer for MailManager.
Schema changes are managed with Alembic migrations.

## Architecture

The package follows an internal layered design with a **single public facade**: all external consumers (services) import exclusively from `database` (`__init__.py`), never from internal submodules. This gives full freedom to reorganize internals without breaking any consumer.

The `database/` package is a framework-agnostic layer parallel to `core/email/` and `auth/` — it has **no imports from `api/`**. Services in `api/services/` translate `DatabaseError` subclasses into `ApiError` subclasses via `translate_database_error` / `catch_database_errors` (same pattern as `translate_core_error` for core).

```
database/
├── __init__.py                  # Public facade (re-exports everything below)
│
├── errors/                      # Database-specific error hierarchy
│   ├── __init__.py              #   Re-exports all exceptions
│   └── exceptions.py            #   DatabaseError base + subclasses
│
├── settings.py                  # Centralized env var reading and validation
├── connection.py                # ThreadedConnectionPool + transactional context manager
├── lifecycle.py                 # App startup helpers (warmup, optional auto-migrate)
├── contracts.py                 # Abstract interfaces (MailboxStore, AccountStore, UserStore, SessionStore, EmailMetadataStore)
│
├── queries/                     # Raw SQL constants only — no Python logic
│   ├── mailboxes.py             #   CRUD for mailboxes table (incl. owner_user_id)
│   ├── accounts.py              #   CRUD for accounts table + token SELECT/UPSERT/BACKFILL + sync_cursor
│   ├── email_metadata.py        #   UPSERT_BATCH, LIST_BY_ACCOUNT, DELETE_BY_ACCOUNT for email_metadata table
│   └── auth.py                  #   UPSERT/SELECT/DELETE for users and sessions tables
│
├── repositories/                # Concrete implementations of contracts
│   ├── mailbox_repository.py    #   PgMailboxStore (implements MailboxStore)
│   ├── account_repository.py    #   PgAccountStore (implements AccountStore) — includes token persistence with encryption + sync_cursor
│   ├── email_metadata_repository.py  #  PgEmailMetadataStore (implements EmailMetadataStore) — batch upsert via execute_values
│   ├── user_repository.py       #   PgUserStore (implements UserStore)
│   └── session_repository.py    #   PgSessionStore (implements SessionStore)
│
├── security/                    # Credentials and token encryption utilities
│   ├── app_credentials.py       #   Loads provider OAuth app credentials from JSON files (paths from settings)
│   └── token_crypto.py          #   Fernet encrypt/decrypt helpers + plaintext fallback flag
│
├── migrations/                  # Schema evolution
│   ├── env.py                   #   Alembic runtime config
│   ├── runner.py                #   Fallback DDL runner (environments without Alembic)
│   └── versions/                #   Versioned migration scripts
│
└── schema.sql                   # Reference snapshot (NOT migration source of truth)
```

### Internal data flow

```
repositories/
  → import queries from queries/
  → import connection from connection.py
  → import contracts from contracts.py
  → account_repository also imports security/token_crypto

security/
  → app_credentials imports settings.py (provider credential paths)
  → token_crypto imports settings.py (encryption keys, plaintext fallback)

connection.py
  → imports settings.py (pool config)

settings.py
  → reads os.environ (the only module that does)
```

Repositories are the only modules that execute SQL. They combine a query from `queries/` with a connection from `connection.py`, and raise specific `DatabaseError` subclasses on failure (`QueryError` for SQL failures, `TokenValidationError` for token validation issues, etc.).

### Layer boundaries

- **`settings.py`** is the only module that reads `os.environ`.
- **`connection.py`** is the only module that manages the connection pool.
- **`queries/`** contains only SQL string constants — zero imports, zero logic.
- **`repositories/`** (including token operations in `account_repository.py`) are the only modules that execute SQL.
- **`contracts.py`** defines abstract interfaces that decouple services from concrete implementations.
- **`__init__.py`** re-exports everything — external code never imports submodules directly.

## Error Handling

The database layer uses its own `DatabaseError` hierarchy defined in `database/errors/exceptions.py`, independent of the API error hierarchy. Services translate these into `ApiError` subclasses via `catch_database_errors`.

### Exception classes

| Exception | `code` | Translates to (API) | When |
|---|---|---|---|
| `DatabaseError` | `database_error` | `ApiError` (fallback) | Base for all database errors |
| `ConnectionPoolError` | `connection_pool_error` | `DatabaseConnectionError` (503) | Pool creation, warmup |
| `QueryError` | `query_error` | `DatabaseQueryError` (503) | Any SQL execution failure (CRUD) |
| `MigrationError` | `migration_error` | `DatabaseMigrationError` (500) | Schema migration failures |
| `SettingsError` | `settings_error` | `EnvVarError` (500) | Missing/invalid env vars, malformed keys |
| `TokenDecryptError` | `token_decrypt_error` | `TokenDecryptionError` (500) | Fernet `InvalidToken` |
| `TokenValidationError` | `token_validation_error` | `TokenIntegrityError` (500) | Token validation/context mismatches |
| `CredentialReadError` | `credential_read_error` | `CredentialFileError` (500) | Credential file unreadable/corrupted |
| `UnknownProviderError` | `unknown_provider_error` | `AccountMisconfigured` (400) | Unknown email provider |

All inherit flat from `DatabaseError` (no intermediate base). Defined in `database/errors/exceptions.py`.

### Capture technique

Every `try` block in the database layer follows this ordered pattern:

```python
try:
    # ... operation ...
except psycopg2.errors.InvalidTextRepresentation:   # 1. Specific psycopg2 first
    return None
except DatabaseError:                                 # 2. Never double-wrap
    raise
except psycopg2.Error as exc:                        # 3. Domain-specific catch
    raise QueryError("Failed to ...") from exc
except Exception as exc:                             # 4. Generic fallback last
    raise QueryError(
        f"Unexpected ... error ({type(exc).__name__}): {exc}"
    ) from exc
```

Rules:

1. **Specific psycopg2 errors first** (step 1) — only where applicable (e.g. `InvalidTextRepresentation` for invalid UUID → graceful `None`/`[]`).
2. **Never double-wrap `DatabaseError`** (step 2) — this guard is only needed when code inside the `try` block can raise a `DatabaseError` subclass, either explicitly or via an internal helper (e.g. `get_connection()` calls `_get_pool()` which can raise `ConnectionPoolError`). The `except DatabaseError: raise` re-raises it before the generic `except Exception` can catch and wrap it a second time. **If nothing inside the `try` can produce a `DatabaseError`, this guard is unnecessary.**
3. **Domain-specific catch** (step 3) — all `psycopg2.Error` subclasses map to the appropriate exception (`QueryError` for repositories, `ConnectionPoolError` for pool, `MigrationError` for migrations).
4. **Generic fallback last** (step 4) — ensures no exception escapes untyped. Message includes `type(exc).__name__` for debuggability.
5. **Preserve the cause chain** — always `raise ... from exc`.

### Where each exception is raised

- **`connection.py`** → `ConnectionPoolError` (pool creation, pool exhaustion via `getconn()`)
- **`lifecycle.py`** → `ConnectionPoolError` (warmup), `MigrationError` (migrations)
- **`migrations/runner.py`** → `MigrationError`
- **`repositories/*.py`** → `QueryError` (SQL failures), `TokenValidationError` (token validation in `account_repository.py`)
- **`settings.py`** → `SettingsError` (missing/invalid env vars)
- **`repositories/account_repository.py`** → `SettingsError` (raised when encryption key is required but absent and plaintext fallback is disabled)
- **`security/token_crypto.py`** → `TokenDecryptError`, `SettingsError` (malformed `TOKEN_ENCRYPTION_KEY` — fails loud, never falls back to plaintext)
- **`security/app_credentials.py`** → `CredentialReadError`, `UnknownProviderError`

### `AccountStore` token behavioral notes

- `AccountStore.get_tokens()` returns `None` when no usable token exists (no row, no encrypted columns with plaintext fallback disabled, etc.). It never raises business-level exceptions — the service layer is responsible for mapping `None` to `AccountNotConnected`.
- `_backfill_plaintext_tokens` is best-effort: failures are logged as warnings and never propagate. The backfill retries on the next read.
- A malformed `TOKEN_ENCRYPTION_KEY` raises `SettingsError` immediately via `get_fernet()` — it is never silently treated as "key absent".

## Design Principles

- Keep SQL and connection management inside `database/`.
- Keep service and router contracts stable (`database` re-exports).
- Evolve schema with Alembic, not app-startup DDL.
- Store provider app credentials separately from account tokens.
- Store account tokens encrypted, with temporary legacy fallback.

## Public API (`database`)

All external code imports from the package root. The `__init__.py` facade re-exports:

| Symbol | Source module | Purpose |
|---|---|---|
| `mailbox_store` | `repositories/` | Singleton `PgMailboxStore` instance |
| `account_store` | `repositories/` | Singleton `PgAccountStore` instance |
| `email_metadata_store` | `repositories/` | Singleton `PgEmailMetadataStore` instance |
| `user_store` | `repositories/` | Singleton `PgUserStore` instance |
| `session_store` | `repositories/` | Singleton `PgSessionStore` instance |
| `close_pool` | `connection.py` | Shutdown: close all pooled connections |
| `warmup_connection` | `lifecycle.py` | Startup: validate DB reachability (`SELECT 1`) |
| `run_startup_migrations_if_enabled` | `lifecycle.py` | Conditional Alembic `upgrade head` at startup |
| `load_app_credentials` | `security/` | Provider OAuth app credentials from JSON file |

## Contracts

| Contract | Methods | Implementation |
|---|---|---|
| `MailboxStore` | `create`, `list_by_owner`, `get`, `delete` | `PgMailboxStore` |
| `AccountStore` | `list_by_mailbox`, `get`, `upsert`, `delete`, `get_tokens`, `upsert_tokens`, `get_sync_cursor`, `update_sync_cursor` | `PgAccountStore` |
| `EmailMetadataStore` | `upsert_batch`, `list_by_account`, `delete_by_account`, `delete_batch_by_message_ids`, `update_labels_batch` | `PgEmailMetadataStore` |
| `UserStore` | `upsert`, `get_by_id`, `get_by_google_sub`, `delete` | `PgUserStore` |
| `SessionStore` | `create`, `get`, `delete`, `delete_expired` | `PgSessionStore` |

## Queries

| Module | Tables | Operations |
|---|---|---|
| `queries/mailboxes.py` | `mailboxes` | INSERT (with owner_user_id), LIST_BY_OWNER, GET, DELETE |
| `queries/accounts.py` | `accounts` | INSERT/UPSERT, LIST_BY_MAILBOX, GET, DELETE, SELECT_TOKENS, UPSERT_TOKENS, BACKFILL_TOKENS, GET_SYNC_CURSOR, UPDATE_SYNC_CURSOR |
| `queries/email_metadata.py` | `email_metadata` | UPSERT_EMAIL_METADATA_BATCH, LIST_BY_ACCOUNT, DELETE_BY_ACCOUNT |
| `queries/auth.py` | `users`, `sessions` | UPSERT_USER, GET_USER_BY_ID, GET_USER_BY_GOOGLE_SUB, DELETE_USER, INSERT_SESSION, GET_VALID_SESSION, DELETE_SESSION, DELETE_EXPIRED_SESSIONS |

## Migration Workflow (Alembic)

Run from repository root:

```bash
python -m alembic -c backend/database/alembic.ini upgrade head
```

For an existing DB already created outside Alembic baseline:

```bash
python -m alembic -c backend/database/alembic.ini stamp 0001_initial_schema
python -m alembic -c backend/database/alembic.ini upgrade head
```

Production recommendation:

- Run `upgrade head` in CI/CD before API rollout.
- Keep `DB_AUTO_MIGRATE=false` in API runtime by default.

## Token Security Model

- Token columns (`access_token`, `refresh_token`, `access_token_encrypted`, `refresh_token_encrypted`, etc.) live directly in the `accounts` table (merged from a separate `tokens` table in migration 0005).
- New token writes are encrypted (`access_token_encrypted`, `refresh_token_encrypted`).
- `TOKEN_ENCRYPTION_KEY` and `TOKEN_ENCRYPTION_KEY_ID` control encryption behavior.
- Token reads validate full account context (`account_id + mailbox_id + provider`).
- Legacy plaintext fallback is controlled by `TOKEN_PLAINTEXT_FALLBACK_ENABLED`.
- On legacy plaintext read, account store tries lazy backfill to encrypted columns.

## Operational Env Vars

Required:

- `DATABASE_URL`

DB tuning:

- `DB_POOL_MIN_CONN` (default `1`)
- `DB_POOL_MAX_CONN` (default `10`)
- `DB_CONNECT_TIMEOUT_SECONDS` (default `10`)
- `DB_APPLICATION_NAME` (default `mailmanager-api`)

Migration control:

- `DB_AUTO_MIGRATE` (default `false`)
- `DB_ALEMBIC_INI_PATH` (optional override)

Token encryption:

- `TOKEN_ENCRYPTION_KEY` (required for encrypted read/write)
- `TOKEN_ENCRYPTION_KEY_ID` (default `v1`)
- `TOKEN_PLAINTEXT_FALLBACK_ENABLED` (default `true`)

Provider credentials:

- `MIA_GMAIL_CREDENTIALS_PATH` (required — path to Gmail OAuth client JSON)
- `MIA_OUTLOOK_CREDENTIALS_PATH` (required — path to Outlook app credentials JSON)

## Extension Guidance

When adding a provider:

1. Register the provider env var in `settings.py` (`_PROVIDER_CREDENTIALS_ENV_VARS`).
2. Add provider-specific JSON parsing in `security/app_credentials.py` if needed.
3. Update provider validation constraints via a new migration.
4. Add/adjust integration and E2E tests for connect, send, and inbox flows.

## Deprecation Note

The plaintext token columns (`access_token`, `refresh_token`) remain temporarily for migration compatibility.
A future migration should remove them once legacy data is fully backfilled.
