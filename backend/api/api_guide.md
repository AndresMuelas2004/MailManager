> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# API Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
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

Six helpers in `services_helpers.py` support the email metadata sync flow:

- `persist_email_metadata_batch(account_id, metadata_list)` — batch upsert to database.
- `load_sync_cursors(label_lookup)` — loads sync cursors per account, keyed by account label.
- `update_sync_cursor(mailbox_id, account_id, cursor)` — persists a new sync cursor.
- `delete_email_metadata_batch(account_id, message_ids)` — deletes email metadata rows by provider message IDs.
- `update_email_metadata_labels_batch(account_id, label_updates)` — updates is_read and box labels for existing rows.
- `load_stored_message_ids(account_id)` — loads all `provider_message_id`s stored for an account. Used by ghost email reconciliation after bootstrap sync.

### Trash management helpers

Four helpers in `services_helpers.py` support the trash management flow:

- `get_trash_emails_by_ids(account_id, message_ids)` — returns list of dicts for emails in TRASH matching the given IDs.
- `mark_as_deleted_batch(account_id, message_ids)` — marks TRASH emails as DELETED in the database.
- `restore_from_trash_batch(account_id, rows)` — restores TRASH emails with a known `previous_box`, updating `provider_message_id`, `box` (from DB's `COALESCE(previous_box, 'ALL_MAIL')`), and clearing `previous_box`. Rows are tuples of `(old_id, new_id, account_id)`.
- `restore_from_trash_discovered_batch(account_id, rows)` — restores TRASH emails where `previous_box` was NULL. The caller provides the discovered box (fetched from the provider after restore). Rows are tuples of `(old_id, new_id, account_id, discovered_box)`.

### Move-to-trash helpers

One helper in `services_helpers.py` supports the move-to-trash flow:

- `move_to_trash_batch(account_id, rows)` — updates `provider_message_id` (in case the provider assigned a new ID), saves the current `box` into `previous_box`, and sets `box = 'TRASH'` in the database. Rows are tuples of `(old_id, new_id, account_id)`. Returns count of affected rows.

### Read-status endpoint

`PATCH /mailboxes/{mailbox_id}/emails/read-status` — batch mark emails as read/unread across one or more accounts.

- **Request**: `ReadStatusRequest` with `is_read: bool` and `items: list[ReadStatusItem]` (each item carries `account_id` + `provider_message_id`).
- **Response**: `ReadStatusResponse` with `updated_count` and per-account details.
- **Error**: `ReadStatusUpdateError` (code `"read_status_update_error"`, HTTP 502) — raised when provider-level updates fail.
- **Flow**: validate ownership via `ensure_mailbox_access` → group items by account → authenticate silently → call `update_read_status` at the provider → persist to DB via `update_read_status_batch`.

## Behavioral Contracts — Traps to Avoid

### `translate_connect_error`

For the interactive `/connect` flow. Maps `EmailAuthError` → `AccountConnectAuthError` (401) instead of `AccountNotConnected` (409). Reason: a connect-time auth failure means the user's credentials are wrong, not that they need to call `/connect` again.

### `raise_on_silent_auth_errors`

Inspects the per-account error dict from `manager.authenticate_all_silent()`. Non-auth `CoreError`s are translated and raised immediately. Auth errors are accumulated and raised as a single `AccountNotConnected` (409).

### Post-fetch error inspection

After `fetch_all_email_metadata()`, the service checks `manager.get_last_errors()` for per-client failures and raises either `AccountNotConnected` (auth errors) or `EmailFetchError` (other errors).

### `manage_trash` — trash operation flow

Handles permanent delete and restore of emails from trash. Key behavioral contracts:

1. **TRASH verification gate**: before any provider call, all referenced emails are verified to be in TRASH via `get_trash_emails_by_ids`. If any email is missing from trash, raises `EmailNotInTrash` (409 Conflict) — not 404, because the email exists but is not in the expected state.
2. **Provider-first rule**: provider delete/restore executes before any DB update. Only messages where the provider call succeeded are persisted locally (see root CLAUDE.md § 2.9).
3. **Per-account grouping**: items are grouped by `account_id`. Auth context is built only for referenced accounts.
4. **Delete branch**: calls `manager.delete_messages`, then `mark_as_deleted_batch` for succeeded IDs.
5. **Restore branch**: calls `manager.restore_from_trash` (passing `None` for items with unknown `previous_box`), then splits the result by `previous_box` state:
   - **Known** (`previous_box` is not NULL): routed to `restore_from_trash_batch`, which reads `COALESCE(previous_box, 'ALL_MAIL')` from the DB.
   - **Unknown** (`previous_box` is NULL): calls `manager.fetch_messages_metadata` on the new IDs to discover the post-restore box from the provider, then routes to `restore_from_trash_discovered_batch` with the discovered box.

Error classes: `EmailNotInTrash` (409) and `TrashOperationError` (500 — catch-all for unexpected failures).

### `move_to_trash` — move-to-trash operation flow

Moves emails to trash at the provider and updates the database. Key behavioral contracts:

1. **Provider-first rule**: calls `manager.move_to_trash` at the provider before any DB update. Only messages where the provider call succeeded are persisted locally (see root CLAUDE.md § 2.9).
2. **Per-account grouping**: items are grouped by `account_id`. Auth context is built only for referenced accounts.
3. **ID mapping**: `move_to_trash` returns `{old_id: new_id}` — Outlook assigns new IDs on move, Gmail keeps the same ID. The service builds tuples `(old_id, new_id, account_id)` from the mapping.
4. **DB update**: calls `move_to_trash_batch` with tuples, which updates `provider_message_id`, copies the current `box` into `previous_box`, and sets `box = 'TRASH'`.
5. **Result reporting**: returns `MoveToTrashResult` with the total count of affected rows (affected: int).

Error classes: `MoveToTrashError` (502 — provider-side failure, code `move_to_trash_error`).

Request/response schemas: `MoveToTrashRequest`, `MoveToTrashResult`.

### Ghost email reconciliation

After a full (bootstrap) sync, `_reconcile_ghost_emails` detects emails stored in the DB that the provider no longer returns. It loads stored IDs, compares against bootstrap results, verifies suspects at the provider via `verify_message_existence`, and hard-deletes confirmed ghosts. **Best-effort**: any error at any step silently skips reconciliation for that account.

### `send_email` — fire-and-forget metadata persistence

After a successful send, the service persists the sent email's metadata. If persistence fails, the error is logged but swallowed — the send is still reported as successful. This is deliberate: the user cares that the email was sent, not that we tracked it internally.

## Extension

### New identity provider

Beyond the general rules checklist:

- Add `POST /auth/<provider>` in `auth_routers.py` (thin route, single service call).
- Add `<provider>_login` in `auth_service.py` (catch `AuthError`, translate via `translate_auth_error`).
- Add request/response schemas in `api/schemas/auth.py`.
- The existing `AuthTokenError` subclasses are provider-agnostic and reusable. See `auth_guide.md` for the auth-layer side of the checklist.
