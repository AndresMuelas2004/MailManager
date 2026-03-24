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

Seven helpers in `services_helpers.py` support the email metadata sync flow:

- `persist_email_metadata_batch(account_id, metadata_list)` — batch upsert to database.
- `load_sync_cursors(label_lookup)` — loads sync cursors per account, keyed by account label.
- `update_sync_cursor(mailbox_id, account_id, cursor)` — persists a new sync cursor.
- `delete_email_metadata_batch(account_id, message_ids)` — deletes email metadata rows by provider message IDs.
- `update_email_metadata_labels_batch(account_id, label_updates)` — updates is_read and box labels for existing rows.
- `update_email_read_status_batch(account_id, message_ids, is_read)` — batch-updates only the `is_read` column for existing rows (used by the read-status endpoint).
- `load_stored_message_ids(account_id)` — loads the set of `provider_message_id`s currently stored in the database for a given account (used by ghost email reconciliation).

### Read-status endpoint

`PATCH /mailboxes/{mailbox_id}/emails/read-status` — batch mark emails as read/unread across one or more accounts.

- **Request**: `ReadStatusRequest` with `is_read: bool` and `items: list[ReadStatusItem]` (each item carries `account_id` + `provider_message_id`).
- **Response**: `ReadStatusResponse` with `updated_count` and per-account details.
- **Error**: `ReadStatusUpdateError` (code `"read_status_update_error"`, HTTP 502) — raised when provider-level updates fail.
- **Flow**: validate ownership via `ensure_mailbox_access` → group items by account → authenticate silently → call `update_read_status` at the provider → persist to DB via `update_email_read_status_batch`.

### Spam endpoints

`POST /mailboxes/{mailbox_id}/emails/spam` — batch move emails to spam across one or more accounts.
`POST /mailboxes/{mailbox_id}/emails/restore-from-spam` — batch restore emails from spam.

- **Request**: `SpamRequest` with `items: list[SpamItem]` (each item carries `account_id` + `provider_message_id`).
- **Response**: `SpamResponse` with `moved_count` and per-account details.
- **Errors**: `SpamMoveError` (code `"spam_move_error"`, HTTP 502) / `SpamRestoreError` (code `"spam_restore_error"`, HTTP 502).
- **Flow**: validate ownership → group items by account → authenticate silently → call `move_to_spam` / `restore_from_spam` at provider → persist to DB via `update_email_spam_status_batch`.
- **Outlook caveat**: the `/move` Graph API endpoint returns a new message ID, which is captured via `SpamMoveResult` and persisted. The DB update writes both the new `provider_message_id` and the new `box` value.
- **`restore_from_spam` box value**: uses `"ALL_MAIL"` as the target box (not `"INBOX"`) because the provider semantics map restored emails to the general mailbox. This is consistent with the box mapping convention where non-special-folder messages default to `"ALL_MAIL"`.

### Spam status persistence helper

`update_email_spam_status_batch(account_id, results, new_box)` — batch update `provider_message_id` and `box` in the database. Uses `UPDATE_SPAM_STATUS_BATCH` which matches on the old `provider_message_id` and writes the new ID and box value.

## Behavioral Contracts — Traps to Avoid

### `translate_connect_error`

For the interactive `/connect` flow. Maps `EmailAuthError` → `AccountConnectAuthError` (401) instead of `AccountNotConnected` (409). Reason: a connect-time auth failure means the user's credentials are wrong, not that they need to call `/connect` again.

### `raise_on_silent_auth_errors`

Inspects the per-account error dict from `manager.authenticate_all_silent()`. Non-auth `CoreError`s are translated and raised immediately. Auth errors are accumulated and raised as a single `AccountNotConnected` (409).

### Post-fetch error inspection

After `fetch_all_email_metadata()`, the service calls the same `raise_on_silent_auth_errors` function used after `authenticate_all_silent()`. This single function inspects the per-account error dict from `manager.get_last_errors()`, translating non-auth `CoreError`s immediately and accumulating auth errors into a single `AccountNotConnected` (409). There is no separate mechanism — both call sites reuse `raise_on_silent_auth_errors`.

### Ghost email reconciliation

`_reconcile_ghost_emails` is a best-effort cleanup flow that runs only after a full sync (bootstrap, i.e. `is_full_sync=True`). It detects "ghost" emails — rows stored in the database that no longer exist at the provider:

1. Load stored `provider_message_id`s for the account via `load_stored_message_ids`.
2. Call `verify_message_existence` on the provider to check which IDs still exist.
3. Compute the difference (stored minus existing) to find ghost IDs.
4. Delete ghost rows via `delete_email_metadata_batch`.

The entire flow is wrapped in a broad `except Exception` — if any step fails, the error is logged and silently skipped. Ghost reconciliation never causes the sync endpoint to fail.

## Extension

### New identity provider

Beyond the general rules checklist:

- Add `POST /auth/<provider>` in `auth_routers.py` (thin route, single service call).
- Add `<provider>_login` in `auth_service.py` (catch `AuthError`, translate via `translate_auth_error`).
- Add request/response schemas in `api/schemas/auth.py`.
- The existing `AuthTokenError` subclasses are provider-agnostic and reusable. See `auth_guide.md` for the auth-layer side of the checklist.
