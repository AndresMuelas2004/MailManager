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

### `DELETE /auth/me` — account deletion

Requires `require_session` (authenticated). Deletes the user row; PostgreSQL `CASCADE` handles all associated data (mailboxes, accounts, tokens, sessions). After deletion the service clears the session cookie. Raises `UserNotFound` (404) if the user does not exist.

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

### Metadata sync endpoint

`POST /mailboxes/{mailbox_id}/emails/sync-metadata?account_id=<optional>` — fetch and persist email metadata.

- **Query params**: `account_id` (optional UUID). When provided, syncs only the specified account; when omitted, syncs all accounts in the mailbox.
- **Response**: `SyncResultOut` with `total_synced` and per-account `AccountSyncDetail` entries.
- **Error**: `EmailFetchError` (code `"email_fetch_error"`, HTTP 502) — raised on provider-level or unexpected failures during sync.
- **Flow**: validate ownership via `ensure_mailbox_access` → if `account_id` provided, validate it belongs to the mailbox via `account_store.get`; if omitted, load all accounts via `account_store.list_by_mailbox` → build manager → authenticate silently → fetch metadata → persist results.

### Metadata sync helpers

Seven helpers in `services_helpers.py` support the email metadata sync flow:

- `persist_email_metadata_batch(account_id, metadata_list)` — batch upsert to database.
- `load_sync_cursors(label_lookup)` — loads sync cursors per account, keyed by account label.
- `update_sync_cursor(mailbox_id, account_id, cursor)` — persists a new sync cursor.
- `delete_email_metadata_batch(account_id, message_ids)` — deletes email metadata rows by provider message IDs.
- `update_email_metadata_labels_batch(account_id, label_updates)` — updates is_read and box labels for existing rows.
- `update_email_read_status_batch(account_id, message_ids, is_read)` — batch-updates only the `is_read` column for existing rows (used by the read-status endpoint).
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

### Email listing endpoint

`GET /mailboxes/{mailbox_id}/emails?box=<BOX>&account_id=<optional>` — list email metadata filtered by box.

- **Query params**: `box` (required, one of `ALL_MAIL`, `SENT`, `SPAM`, `TRASH`), `account_id` (optional UUID).
- **Response**: `list[EmailMetadataOut]` — flat list of email metadata objects sorted by `received_at DESC`.
- **Error**: `EmailListError` (code `"email_list_error"`, HTTP 500) — raised on database-level failures during listing.
- **Flow**: validate ownership via `ensure_mailbox_access` → if `account_id` provided, validate it belongs to the mailbox via `account_store.get`, then query `list_by_account_and_box`; if omitted, query `list_by_mailbox_and_box` (JOINs with `accounts` table).
- **No provider calls**: this endpoint reads only from the local database. Provider sync is handled by `POST .../sync-metadata`.
- **Extensibility note**: the `box` parameter is the single filtering axis for email classification. When new email categories are added (e.g. promotions, social, updates), the approach is to extend the allowed `box` values in the `Literal` type, the database CHECK constraint, and the box mapping logic in provider clients — then reuse this same `list_emails` endpoint with the new box value. Do not create separate listing endpoints per category; always funnel through this endpoint by expanding the `box` enum.
- **Testing rule**: this endpoint must be integration-tested using the seeded fake data from migration 0010 with exact content assertions. See `integration_guide.md` § "GET endpoint testing rules" for the mandatory rules.

### GET endpoints — integration test coverage rule

GET endpoints that read exclusively from the database (no provider API calls) can be fully covered by integration tests (real FastAPI + real PostgreSQL) with the same fidelity as E2E tests. GET endpoints that involve external calls (e.g. cache-aside with provider fallback) require additional test strategies — see each endpoint's documentation for details. See `integration_guide.md` § "GET endpoint testing rules" for the mandatory rules that apply when adding or modifying database-only GET endpoints.

### Email content endpoint

`GET /mailboxes/{mailbox_id}/emails/{provider_message_id}/content?account_id=<required>` — return the full email body (HTML and/or plain text).

- **Query params**: `account_id` (required, `min_length=1`).
- **Response**: `EmailContentOut` with `html_body: str | None` and `text_body: str | None`.
- **Error**: `EmailContentFetchError` (code `"email_content_fetch_error"`, HTTP 502) — raised on provider-level or unexpected failures when fetching content.
- **Flow**: validate ownership via `ensure_mailbox_access` → validate account exists → check DB cache via `get_email_content` helper → if cached, return immediately → if not cached, build manager → authenticate silently → fetch from provider via `manager.fetch_email_content` → sanitize HTML via `sanitize_email_html` → best-effort persist via `persist_email_content` → return content.
- **Best-effort persist**: if the DB write fails after content is fetched, the error is logged but swallowed — the content is still returned to the user. Same pattern as `send_email` metadata persistence.
- **HTML sanitization**: `sanitize_email_html` strips dangerous tags (`<script>`, `<iframe>`, etc.), blocks `javascript:`/`data:` protocols in `href` and `src`, and preserves safe email formatting tags. Applied before persisting to DB.

### Email content helpers

Two helpers in `services_helpers.py` support the email content flow:

- `get_email_content(account_id, provider_message_id)` — reads cached content from the `email_content` table. Returns dict or `None`.
- `persist_email_content(account_id, provider_message_id, html_body, text_body)` — upserts content to DB. CAN raise — the caller wraps it in `try/except` for best-effort.

### Draft creation endpoint

`POST /mailboxes/{mailbox_id}/accounts/{account_id}/drafts` — create a draft at the provider and persist it locally.

- **Path params**: `mailbox_id`, `account_id` (both in the URL path; this differs from the email send endpoint which carries `account_id` in the request body).
- **Request**: `DraftCreate` with all fields optional and defaulted: `to_recipients: list[str] = []`, `cc_recipients: list[str] = []`, `bcc_recipients: list[str] = []`, `subject: str = ""`, `body_html: str = ""`. Empty drafts are accepted (matches Gmail/Outlook native behavior).
- **Response**: `DraftOut` with `provider_draft_id`, `account_id`, recipients, `subject`, `body_html`, `created_at`, `updated_at`.
- **Error**: `DraftCreationError` (code `"draft_creation_error"`, HTTP 502) — raised on provider-side or unexpected failures during draft creation.
- **Flow**: validate ownership via `ensure_mailbox_access` → fetch the account via `account_store.get` (404 if missing) → build manager via `build_manager_for_accounts` → silent auth + token refresh persistence → **Provider-First**: call `manager.create_draft(...)` (translated `CoreError` via `translate_core_error(fallback=DraftCreationError)`) → only on success, build the row dict and call `draft_store.create(...)` → return `DraftOut` from the persisted row.
- **Outlook critical**: the Outlook client passes `Prefer: IdType="ImmutableId"` when creating the draft so the message ID stays stable across state transitions (critical for the future send-draft endpoint, which would reuse the same ID).
- **Service module**: lives in `api/services/drafts_service.py` with a local `_persist_refreshed_tokens` helper. The service is the only one that imports `draft_store` from `database`.

## Behavioral Contracts — Traps to Avoid

### `connect_account` response includes `email_address`

After a successful interactive OAuth flow, the service extracts the `email_address` from the token payload (populated by the Core layer's best-effort fetch) and includes it in `AccountConnectResponse`. The field is `str | None` — `None` when the provider email fetch failed. The `AccountOut` schema also includes `email_address` (populated from the `accounts` table) so the frontend can display it when listing accounts.

### `translate_connect_error`

For the interactive `/connect` flow. Maps `EmailAuthError` → `AccountConnectAuthError` (401) instead of `AccountNotConnected` (409). Reason: a connect-time auth failure means the user's credentials are wrong, not that they need to call `/connect` again.

### `raise_on_silent_auth_errors`

Inspects the per-account error dict from `manager.authenticate_all_silent()`. Non-auth `CoreError`s are translated and raised immediately. Auth errors are accumulated and raised as a single `AccountNotConnected` (409).

### Post-fetch error inspection

After `fetch_all_email_metadata()`, the service calls the same `raise_on_silent_auth_errors` function used after `authenticate_all_silent()`. This single function inspects the per-account error dict from `manager.get_last_errors()`, translating non-auth `CoreError`s immediately and accumulating auth errors into a single `AccountNotConnected` (409). There is no separate mechanism — both call sites reuse `raise_on_silent_auth_errors`.

### Ghost email reconciliation

`_reconcile_ghost_emails` is a best-effort cleanup flow that runs only after a full sync (bootstrap, i.e. `is_full_sync=True`). It detects "ghost" emails — rows stored in the database that no longer exist at the provider:

1. Load stored `provider_message_id`s for the account via `load_stored_message_ids`.
2. Extract `bootstrap_ids` from `sync_result.upserts` (the IDs returned by the fresh bootstrap sync).
3. Compute `suspect_ids` = stored IDs NOT IN `bootstrap_ids` (emails the bootstrap did not return).
4. Call `verify_message_existence` on the provider to check which suspect IDs still exist.
5. Compute ghost IDs = suspect IDs NOT IN the set returned by `verify_message_existence`.
6. Delete ghost rows via `delete_email_metadata_batch`.

Each step is wrapped in its own `except Exception` block — if any step fails, the error is logged and reconciliation is silently skipped for that account. Ghost reconciliation never causes the sync endpoint to fail.

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

### `send_email` — fire-and-forget metadata persistence

After a successful send, the service persists the sent email's metadata. If persistence fails, the error is logged but swallowed — the send is still reported as successful. This is deliberate: the user cares that the email was sent, not that we tracked it internally.

## Service-Layer Error Classes

Complete, authoritative list of every `ApiError` subclass registered in `_STATUS_MAP` (see `backend/api/errors/handlers.py`). Services should reuse these classes rather than invent new ones. When a new subclass is added to `exceptions.py`, register it in `_STATUS_MAP` **and** add a row here.

### Resource / ownership (404–409)

| Class | Code | HTTP | Usage |
|---|---|---|---|
| `MailboxNotFound` | `mailbox_not_found` | 404 | Mailbox not found or ownership check failed mid-query. |
| `AccountNotFound` | `account_not_found` | 404 | Account not found inside its mailbox during an operation. |
| `UserNotFound` | `user_not_found` | 404 | Authenticated user does not exist in the database (e.g. during `DELETE /auth/me` or `GET /auth/me`). |
| `EmailNotInTrash` | `email_not_in_trash` | 409 | A `manage_trash` pre-check rejected an email that was not currently in the `TRASH` box. |
| `AccountNotConnected` | `account_not_connected` | 409 | Silent auth failed or tokens are missing — the user must reconnect the account. Raised by `raise_on_silent_auth_errors`. |

### Auth / access control (400–403)

| Class | Code | HTTP | Usage |
|---|---|---|---|
| `Unauthorized` | `unauthorized` | 401 | Missing or invalid session cookie. |
| `AccountConnectAuthError` | `account_connect_auth_error` | 401 | `EmailAuthError` translated specifically during the interactive `POST .../connect` flow. |
| `Forbidden` | `forbidden` | 403 | Authenticated user does not own the requested mailbox. Raised by `ensure_mailbox_access`. |
| `AccountMisconfigured` | `account_misconfigured` | 400 | `EmailConfigError` family (bad provider name, malformed tokens, invalid expiry). Usually translated from `build_manager_for_accounts`. |
| `RecipientsMissing` | `recipients_missing` | 400 | Send or draft call rejected because no recipients were supplied. |

### Provider-side / external API (502)

| Class | Code | HTTP | Usage |
|---|---|---|---|
| `EmailFetchError` | `email_fetch_error` | 502 | Provider-side failure when fetching/syncing email metadata. |
| `EmailSendError` | `email_send_error` | 502 | Provider-side failure when sending an email. |
| `EmailContentFetchError` | `email_content_fetch_error` | 502 | Provider-side or unexpected failure when fetching full email content. |
| `DraftCreationError` | `draft_creation_error` | 502 | Provider-side or unexpected failure during draft creation. |
| `ExternalAPIError` | `external_api_error` | 502 | Generic catch-all for translated `EmailExternalAPIError`. Use more specific subclasses where possible. |
| `MoveToTrashError` | `move_to_trash_error` | 502 | Provider-side failure during `move_to_trash`. |
| `ReadStatusUpdateError` | `read_status_update_error` | 502 | Provider-side failure during `update_read_status`. |
| `SpamMoveError` | `spam_move_error` | 502 | Provider-side failure during `move_to_spam`. |
| `SpamRestoreError` | `spam_restore_error` | 502 | Provider-side failure during `restore_from_spam`. |

### Database / persistence (500–503)

| Class | Code | HTTP | Usage |
|---|---|---|---|
| `DatabaseConnectionError` | `database_connection_error` | 503 | Pool exhausted or unable to acquire a connection. |
| `DatabaseQueryError` | `database_query_error` | 503 | SQL execution failure reaching the client. |
| `DatabaseMigrationError` | `database_migration_error` | 500 | Schema migration failure at startup. |
| `EmailListError` | `email_list_error` | 500 | Database-level failure when listing email metadata (not translated to `DatabaseQueryError` because it is the only place the list operation can fail). |
| `TrashOperationError` | `trash_operation_error` | 500 | Internal bookkeeping failure inside `manage_trash` (not a provider error). |

### Token / credential security (500)

| Class | Code | HTTP | Usage |
|---|---|---|---|
| `TokenEncryptionError` | `token_encryption_error` | 500 | Failure while encrypting account tokens before storage. |
| `TokenDecryptionError` | `token_decryption_error` | 500 | Failure while decrypting stored tokens. |
| `TokenIntegrityError` | `token_integrity_error` | 500 | Stored token record is malformed/inconsistent. |
| `AppCredentialsInvalid` | `app_credentials_invalid` | 500 | Developer-provided app credentials are structurally invalid. |
| `AppCredentialsMissing` | `app_credentials_missing` | 500 | Developer-provided app credentials are absent entirely. |
| `CredentialFileError` | `credential_file_error` | 500 | Failure reading/parsing a credential file on disk. |
| `EnvVarError` | `env_var_error` | 500 | Missing or invalid environment variable detected at boot. |

## Service Conventions — Auth context ordering

When an endpoint must authenticate against a provider and then perform a provider call, the service function **must** follow this exact sequence. Skipping or reordering any step leads to silent token staleness, missing error surfacing, or unauthenticated provider calls.

1. **Build the manager.** `manager = build_manager_for_accounts([account])` — wraps `EmailConfigError` translation into `AccountMisconfigured`.
2. **Load wrapped credentials and tokens.** `load_wrapped_app_credentials(provider)` and `load_wrapped_account_tokens(mailbox_id, account_id, provider)`. Tokens are unwrapped only at the provider boundary.
3. **Silent auth.** `updated_tokens = manager.authenticate_all_silent(auth_payloads)`. This may refresh tokens in place.
4. **Persist refreshed tokens.** If `updated_tokens` is non-empty, call `account_store.upsert_tokens` for each updated account. Any failure here must surface as the endpoint's primary error class (e.g. `DraftCreationError` for drafts, `EmailFetchError` for sync).
5. **Raise on silent auth errors.** `raise_on_silent_auth_errors(manager.get_last_errors(), fallback=<endpoint-specific class>)` — this is what turns per-client `EmailAuthError` into `AccountNotConnected` (409).
6. **Provider call.** Only now call `manager.send_email_from_account`, `manager.create_draft`, `manager.fetch_all_email_metadata`, etc. Wrap in `try / except CoreError / except Exception` per CLAUDE.md §9.

The `drafts_service.create_draft` function is the canonical reference implementation of this sequence.

## Extension

### New identity provider

Beyond the general rules checklist:

- Add `POST /auth/<provider>` in `auth_routers.py` (thin route, single service call).
- Add `<provider>_login` in `auth_service.py` (catch `AuthError`, translate via `translate_auth_error`).
- Add request/response schemas in `api/schemas/auth.py`.
- The existing `AuthTokenError` subclasses are provider-agnostic and reusable. See `auth_guide.md` for the auth-layer side of the checklist.
