# Database Package (`api/database`)

This package is the PostgreSQL persistence layer for MailManager.
Schema changes are managed with Alembic migrations.

## Design Principles

- Keep SQL and connection management inside `api/database`.
- Keep service and router contracts stable (`api.database` re-exports).
- Evolve schema with Alembic, not app-startup DDL.
- Store provider app credentials separately from account tokens.
- Store account tokens encrypted, with temporary legacy fallback.

## Directory Responsibilities

| Path | Responsibility |
|---|---|
| `settings.py` | Reads and validates env vars for DB pool, migrations, and token security. |
| `connection.py` | Connection pool and transaction context (`get_connection`). |
| `lifecycle.py` | Startup helpers (`warmup_connection`, optional startup migrations). |
| `contracts.py` | Persistence interfaces (`MailboxStore`, `AccountStore`). |
| `queries/mailboxes.py` | Raw SQL for mailbox operations. |
| `queries/accounts.py` | Raw SQL for account operations. |
| `queries/tokens.py` | Raw SQL for token load/save/backfill/delete operations. |
| `repositories/mailbox_repository.py` | Mailbox repository implementation. |
| `repositories/account_repository.py` | Account repository implementation. |
| `security/app_credentials.py` | Loads provider app credentials from env-defined JSON files. |
| `security/token_crypto.py` | Fernet encryption/decryption helpers for account tokens. |
| `security/token_store.py` | Encrypted token persistence with context validation and legacy fallback. |
| `migrations/env.py` | Alembic migration runtime config. |
| `migrations/versions/*.py` | Versioned schema migrations. |
| `schema.sql` | Legacy schema snapshot for reference only (not migration source of truth). |

## Public API (`api.database`)

Use package-root imports from `api.database`:

- `mailbox_store`
- `account_store`
- `get_connection`
- `close_pool`
- `warmup_connection`
- `init_db` (deprecated compatibility helper)
- `run_startup_migrations_if_enabled`
- `load_app_credentials`
- `load_account_tokens`
- `save_account_tokens`
- `delete_account_tokens_for_records`

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
