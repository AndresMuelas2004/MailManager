# Database Package (`api/database`)

This package is the PostgreSQL persistence layer for MailManager.
Schema changes are managed with Alembic migrations.

## Architecture

The package follows an internal layered design with a **single public facade**: all external consumers (services, routers) import exclusively from `api.database` (`__init__.py`), never from internal submodules. This gives full freedom to reorganize internals without breaking any consumer.

```
api/database/
├── __init__.py                  # Public facade (re-exports everything below)
│
├── settings.py                  # Centralized env var reading and validation
├── connection.py                # ThreadedConnectionPool + transactional context manager
├── lifecycle.py                 # App startup helpers (warmup, optional auto-migrate)
├── contracts.py                 # Abstract interfaces (MailboxStore, AccountStore)
│
├── queries/                     # Raw SQL constants only — no Python logic
│   ├── mailboxes.py             #   CRUD for mailboxes table
│   ├── accounts.py              #   CRUD for accounts table
│   └── tokens.py                #   SELECT/UPSERT/BACKFILL/DELETE for tokens table
│
├── repositories/                # Concrete implementations of contracts
│   ├── mailbox_repository.py    #   PgMailboxStore (implements MailboxStore)
│   └── account_repository.py    #   PgAccountStore (implements AccountStore)
│
├── security/                    # Credentials and token encryption
│   ├── app_credentials.py       #   Loads provider OAuth app credentials from JSON files
│   ├── token_crypto.py          #   Fernet encrypt/decrypt helpers
│   └── token_store.py           #   Token persistence with context validation and legacy fallback
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
repositories/ & security/token_store.py
  → import queries from queries/
  → import connection from connection.py
    → connection.py reads pool config from settings.py
      → settings.py reads env vars (DATABASE_URL, pool tuning, encryption keys)
```

Repositories and token_store are the only modules that execute SQL. They combine a query from `queries/` with a connection from `connection.py`, and raise `DatabaseError` on failure.

### Layer boundaries

- **`settings.py`** is the only module that reads `os.environ`.
- **`connection.py`** is the only module that manages the connection pool.
- **`queries/`** contains only SQL string constants — zero imports, zero logic.
- **`repositories/`** and **`security/token_store.py`** are the only modules that execute SQL.
- **`contracts.py`** defines abstract interfaces that decouple services from concrete implementations.
- **`__init__.py`** re-exports everything — external code never imports submodules directly.

## Design Principles

- Keep SQL and connection management inside `api/database`.
- Keep service and router contracts stable (`api.database` re-exports).
- Evolve schema with Alembic, not app-startup DDL.
- Store provider app credentials separately from account tokens.
- Store account tokens encrypted, with temporary legacy fallback.

## Public API (`api.database`)

All external code imports from the package root. The `__init__.py` facade re-exports:

| Symbol | Source module | Purpose |
|---|---|---|
| `mailbox_store` | `repositories/` | Singleton `PgMailboxStore` instance |
| `account_store` | `repositories/` | Singleton `PgAccountStore` instance |
| `get_connection` | `connection.py` | Transactional context manager (auto-commit/rollback) |
| `close_pool` | `connection.py` | Shutdown: close all pooled connections |
| `warmup_connection` | `lifecycle.py` | Startup: validate DB reachability (`SELECT 1`) |
| `init_db` | `lifecycle.py` | Deprecated — calls `warmup_connection()` |
| `run_startup_migrations_if_enabled` | `lifecycle.py` | Conditional Alembic `upgrade head` at startup |
| `load_app_credentials` | `security/` | Provider OAuth app credentials from JSON file |
| `load_account_tokens` | `security/` | Read + decrypt account tokens with context validation |
| `save_account_tokens` | `security/` | Encrypt + write account tokens with context validation |
| `delete_account_tokens_for_records` | `security/` | Batch delete tokens by account IDs |

## Migration Workflow (Alembic)

Run from repository root:

```bash
python -m alembic -c backend/api/database/alembic.ini upgrade head
```

For an existing DB already created outside Alembic baseline:

```bash
python -m alembic -c backend/api/database/alembic.ini stamp 0001_initial_schema
python -m alembic -c backend/api/database/alembic.ini upgrade head
```

Production recommendation:

- Run `upgrade head` in CI/CD before API rollout.
- Keep `DB_AUTO_MIGRATE=false` in API runtime by default.

## Token Security Model

- New token writes are encrypted (`access_token_encrypted`, `refresh_token_encrypted`).
- `TOKEN_ENCRYPTION_KEY` and `TOKEN_ENCRYPTION_KEY_ID` control encryption behavior.
- Token reads validate full account context (`account_id + mailbox_id + provider`).
- Legacy plaintext fallback is controlled by `TOKEN_PLAINTEXT_FALLBACK_ENABLED`.
- On legacy plaintext read, token store tries lazy backfill to encrypted columns.

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

## Extension Guidance

When adding a provider:

1. Add provider support in app credential loading (`security/app_credentials.py`).
2. Update provider validation constraints via a new migration.
3. Add/adjust integration and E2E tests for connect, send, and unread flows.

## Deprecation Note

The plaintext token columns (`access_token`, `refresh_token`) remain temporarily for migration compatibility.
A future migration should remove them once legacy data is fully backfilled.
