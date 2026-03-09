# API Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`general_api_rules.md`](./general_api_rules.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### Endpoints that skip `require_session`

| Endpoint | Why |
|---|---|
| `GET /health` | Unauthenticated health check — no user context needed |
| `POST /auth/google` | Creates the session — cannot require a prior one |
| `POST /auth/logout` | Must work even with expired sessions |

### One endpoint per identity provider

`POST /auth/google` is hardcoded to Google OIDC. When adding a new provider, add a separate `POST /auth/<provider>` — not a generic endpoint with a `provider` parameter. This keeps each flow's schema and service logic isolated.

### Cookie management

Services that manage session cookies receive the `fastapi.Response` object from the router. Cookie setting/clearing happens in the service layer, not in routers.

## Service Conventions

### Ownership check

Every action scoped to a mailbox calls `ensure_mailbox_access(mailbox_id, user_id)` first. It validates the mailbox exists and the authenticated user owns it, raising `MailboxNotFound` (404) or `Forbidden` (403).

### Building provider clients

Build via `build_manager_for_accounts(accounts)` — never instantiate `EmailClient` subclasses directly. This helper creates an `EmailManager` and registers all account records, translating `CoreError` and unexpected exceptions to `AccountMisconfigured`.

### Secret wrapping

Load credentials with `load_wrapped_app_credentials(provider)` / `load_wrapped_account_tokens(mailbox_id, account_id, provider)` (uses `pydantic.SecretStr`). Unwrap with `unwrap_secret()` before persisting.

### Metadata sync helpers

Five helpers in `services_helpers.py` support the email metadata sync flow:

- `persist_email_metadata_batch(account_id, metadata_list)` — batch upsert to database.
- `load_sync_cursors(label_lookup)` — loads sync cursors per account, keyed by account label.
- `update_sync_cursor(mailbox_id, account_id, cursor)` — persists a new sync cursor.
- `delete_email_metadata_batch(account_id, message_ids)` — deletes email metadata rows by provider message IDs.
- `update_email_metadata_labels_batch(account_id, label_updates)` — updates is_read and box labels for existing rows.

## Behavioral Contracts — Traps to Avoid

### `translate_connect_error`

For the interactive `/connect` flow. Maps `EmailAuthError` → `AccountConnectAuthError` (401) instead of `AccountNotConnected` (409). Reason: a connect-time auth failure means the user's credentials are wrong, not that they need to call `/connect` again.

### `raise_on_silent_auth_errors`

Inspects the per-account error dict from `manager.authenticate_all_silent()`. Non-auth `CoreError`s are translated and raised immediately. Auth errors are accumulated and raised as a single `AccountNotConnected` (409).

### Post-fetch error inspection

After `fetch_all_email_metadata()`, the service checks `manager.get_last_errors()` for per-client failures and raises either `AccountNotConnected` (auth errors) or `EmailFetchError` (other errors).

## Extension

### New identity provider

Beyond the general rules checklist:

- Add `POST /auth/<provider>` in `auth_routers.py` (thin route, single service call).
- Add `<provider>_login` in `auth_service.py` (catch `AuthError`, translate via `translate_auth_error`).
- Add request/response schemas in `api/schemas/auth.py`.
- The existing `AuthTokenError` subclasses are provider-agnostic and reusable. See `auth_guide.md` for the auth-layer side of the checklist.
