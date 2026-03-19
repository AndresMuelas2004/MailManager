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

- Returns `None` when no usable token exists (no row, encrypted columns absent with fallback disabled, etc.). It **never raises** business-level exceptions — the service layer maps `None` to `AccountNotConnected`.
- `_backfill_plaintext_tokens` is best-effort: failures are logged as warnings and never propagate. The backfill retries on the next read.
- A malformed `TOKEN_ENCRYPTION_KEY` raises `SettingsError` immediately via `get_fernet()` — it is never silently treated as "key absent".

## Extension

### Adding a new provider

1. Register the provider env var in `settings.py` (`_PROVIDER_CREDENTIALS_ENV_VARS`).
2. Add provider-specific JSON parsing in `security/app_credentials.py` if needed.
3. Update provider validation constraints via a new Alembic migration.
4. Add/adjust integration and E2E tests for connect, send, and inbox flows.
