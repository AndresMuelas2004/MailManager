> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# Email Client Implementation Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Helper Reuse Policy

When modifying `gmail_client.py`, `outlook_client.py`, or `email_manager.py`, always maximise code reuse before writing new logic:

1. **Shared helpers first** — check `helpers.py` for functions that already solve the problem (`parse_expiry`, `unwrap_app_credentials`, `unwrap_user_tokens`, `wrap_account_tokens`, `http_error_detail`). If the new logic is useful to more than one client, extract it to `helpers.py`.
2. **Internal helpers second** — scan the file being modified for existing private methods (`_*`). Reuse or extend them instead of duplicating logic.
3. **Extract when duplicated** — if both clients end up with similar logic, move the common part to `helpers.py` so both import it.

This policy applies to every modification — not only when adding a new provider.

## Design Decisions

### `_last_errors` pattern

`EmailManager` stores per-account errors in `_last_errors` (dict keyed by account label). Operations like `fetch_all_email_metadata()` and `authenticate_all_silent()` collect per-client errors without aborting other clients. The service layer inspects these via `get_last_errors()` after each operation.

### Sync cursor contract

`fetch_all_email_metadata()` accepts an optional `sync_cursors` dict keyed by account label. Each client receives its cursor (or `None` for bootstrap). This is an `EmailManager`-level contract — individual clients receive their cursor as a parameter.

### `account_id` left empty — stamped by the service layer

`EmailMetadata.account_id` is left as `""` by provider clients. The service layer stamps it before persistence. This is a cross-layer contract: if a client sets it, the service overwrites it; if the service forgets to stamp it, the database will store an empty string. **Trap**: always stamp before calling `persist_email_metadata_batch`.

## Data Structures

### `SyncResult`

Returned by `fetch_email_metadata`. Fields:

- `upserts: list[EmailMetadata]` — full metadata to insert or update.
- `new_cursor: str` — opaque sync cursor for the next call.
- `deletes: list[str]` — `provider_message_id`s to remove from persistence (default empty).
- `label_updates: list[LabelUpdate]` — partial updates for already-persisted messages (default empty).
- `is_full_sync: bool` — `True` during bootstrap, `False` during incremental (default `False`).

### `LabelUpdate`

Partial update carrying only label-derived fields for an existing message:

- `provider_message_id: str`
- `is_read: bool`
- `box: str` — one of `"ALL_MAIL"`, `"SENT"`, `"SPAM"`, `"TRASH"`, `"DELETED"`

## Error Hierarchy

```
CoreError
└── EmailError
    ├── EmailAuthError
    │   ├── EmailMissingTokenError
    │   ├── EmailMissingRefreshTokenError
    │   ├── EmailRefreshFailedError
    │   └── EmailNotAuthenticatedError
    ├── EmailConfigError
    │   ├── EmailAccountRecordError
    │   ├── EmailProviderConfigError
    │   ├── EmailInvalidExpiryError
    │   ├── EmailInvalidCredentialsDataError
    │   ├── EmailInvalidTokenDataError
    │   ├── EmailMissingAppCredentialsError
    │   └── EmailDuplicateAccountLabelError
    ├── EmailAccountNotFoundError
    ├── EmailRecipientsMissingError
    └── EmailExternalAPIError
```

All errors carry a `code` string and `message`. The service layer translates these into API-layer errors via `_CORE_TO_API_MAP`.

## Behavioral Contracts — Authentication Flows

### Interactive flow (`authenticate`)

Used by `POST /connect`. Executes provider-specific OAuth:
- Gmail: `InstalledAppFlow.run_local_server(...)`
- Outlook: manual PKCE flow with local callback HTTP server

### Silent flow (`authenticate_silent`)

Used before fetch/send. Returns `None` if token is still valid (no refresh needed), or wrapped updated tokens when refreshed.

**Provider-specific refresh behavior** — critical difference:
- **Gmail**: refresh token is commonly stable across refreshes.
- **Outlook**: may rotate refresh tokens on each refresh. Always persist the returned refresh token.

## Behavioral Contracts — Email Metadata Sync

### Bootstrap vs incremental

- `sync_cursor=None` → bootstrap (Path 1): fetch up to `max_total` messages from scratch. Sets `SyncResult.is_full_sync = True`.
- `sync_cursor` present → attempt incremental (Path 2). Falls back to bootstrap on invalid cursor or if not yet implemented.

### Box mapping convention

```
labelIds contains "TRASH" → box = "TRASH"
labelIds contains "SPAM"  → box = "SPAM"
labelIds contains "SENT"  → box = "SENT"
otherwise                 → box = "ALL_MAIL"
```

### Gmail — batch fetch approach

1. List message IDs (paginated `messages.list`, `includeSpamTrash=True`).
2. Batch-fetch metadata in chunks of 100 (`format="metadata"`). When credentials are available, chunks run in parallel via `ThreadPoolExecutor`; otherwise falls back to sequential execution.
3. Get current `historyId` from `getProfile` as `new_sync_cursor`.

**Parallel execution**: controlled by `GMAIL_BATCH_MAX_WORKERS` environment variable (default `5`). Each parallel chunk builds its own thread-local HTTP transport because `httplib2` is not thread-safe. Retry logic (up to `_BATCH_MAX_RETRIES` = 4 retries (5 total attempts), `_BATCH_RETRY_DELAY` = 1s between retries) applies per chunk. Messages that permanently fail are logged and skipped.

### Gmail — incremental sync (History API)

When `sync_cursor` is present and valid: paginate history, resolve deletes, filter label changes, batch-fetch metadata for added/changed messages, batch-fetch label updates. Falls back to bootstrap on invalid `historyId`.

**Event threshold**: if the total number of event IDs (adds + deletes + label changes) exceeds `_INCREMENTAL_EVENT_THRESHOLD` (100), incremental sync aborts and falls back to bootstrap. This prevents expensive batch fetches when a large number of changes have accumulated.

### Outlook — metadata sync (Delta Query)

Delta queries are **per folder** — Microsoft Graph v1.0 does not support delta at the mailbox level. The client iterates over `_DELTA_FOLDERS` (`inbox`, `sentitems`, `drafts`, `deleteditems`, `junkemail`, `archive`), issuing `/me/mailFolders/{folder}/messages/delta` for each.

**Bootstrap** (three-step approach):

1. **Resolve special folder IDs** (`_resolve_special_folder_ids`): fetch Graph IDs for `sentitems`, `deleteditems`, and `junkemail` via `GET /me/mailFolders/{folder}?$select=id`. Returns a `{folder_id: box}` mapping for message classification.
2. **Fetch recent messages** (`_fetch_recent_messages`): `GET /me/messages` with `$orderby=receivedDateTime desc`, paginating up to `max_total`. Each message's `parentFolderId` is matched against the folder ID mapping to assign the correct box (unmatched defaults to `ALL_MAIL`).
3. **Initialize delta cursors**: for each folder in `_DELTA_FOLDERS`, drain its delta query with `max_collect=0` (collecting zero messages, only obtaining the `deltaLink`). The cursor stored is a JSON object encoding per-folder deltaLinks: `{"v": 1, "folders": {"inbox": "https://...", ...}}`.

**Incremental**: decode the JSON cursor. For each folder that has a deltaLink, re-issue it. Messages with `@removed` become deletes. Messages missing the `"from"` field (partial delta responses) are routed to `label_updates`. All other messages become upserts.

**Cursor format and legacy detection**: the cursor is a JSON string with `{"v": 1, "folders": {...}}`. If `_decode_folder_cursors` encounters a non-JSON or differently versioned cursor (legacy format from old single-URL approach), it returns `None`, which triggers `EmailExternalAPIError` in `_incremental_email_metadata`. This error propagates up to `fetch_email_metadata` where it is caught, causing fallback to bootstrap.

**Folder-to-box mapping**: determined by folder name via `_FOLDER_TO_BOX` (`deleteditems`→TRASH, `junkemail`→SPAM, `sentitems`→SENT, all others→ALL_MAIL). During bootstrap, classification uses `parentFolderId` resolved against Graph folder IDs. During incremental, classification uses the folder name from the delta query context.

**Fault tolerance**: if a folder fails during bootstrap delta initialization, it is skipped (logged) and excluded from the cursor. During incremental sync, a failed folder keeps its previous deltaLink in the new cursor. If **all** folders fail during incremental, an error is raised to trigger bootstrap fallback.

## Trash Management Operations

### `delete_messages(message_ids) → list[str]`

Mark messages as deleted locally without calling the provider API. Returns all provided IDs as "succeeded" so the service layer marks them as `DELETED` in the database. **This is the only operation that intentionally breaks the Provider-First Rule** (root `CLAUDE.md` § 2.9): it does not act on the provider before updating the DB.

**Why**: Gmail's `gmail.modify` scope cannot call `messages.delete` (requires the restricted `mail.google.com` scope). Since one provider cannot perform permanent deletion, we adopt a uniform no-op approach across all providers — regardless of whether their individual scopes support it — so the behavior is consistent and predictable.

**Effect**: the provider retains the messages in Trash until its own retention policy purges them (Gmail: 30 days auto-clean; Outlook: per-tenant retention). The `DELETED` box value in the DB is a soft-delete marker that prevents sync from overwriting the user's explicit delete intent (see `DELETED` box value section below).

- **Gmail**: no-op. Returns all IDs.
- **Outlook**: no-op. Returns all IDs.

### `restore_from_trash(items) → dict[str, str]`

Restore messages from trash at the provider. `items` maps `provider_message_id → destination_box` (or `None` when the original box is unknown). Returns `{original_id: new_id}` for successfully restored messages.

- **Gmail**: splits items into two groups based on the destination value:
  - **Known** (`destination_box` is not `None`): batch `messages.modify` with `removeLabelIds: ["TRASH"]` and `addLabelIds` from `_BOX_TO_GMAIL_LABELS` mapping (`ALL_MAIL` → `["INBOX"]`, `SPAM` → `["SPAM"]`, other → `[]`).
  - **Unknown** (`destination_box` is `None`): batch `messages.untrash`, which lets Gmail restore the message's original label state automatically.
  - ID does not change in either case (`original_id == new_id`).
- **Outlook**: `POST /messages/{id}/move` with `destinationId` (well-known folder name). `None` destination defaults to `inbox`. Serial loop. **The message ID changes** — the response contains the new message object with the new `id` field. Returns `{old_id: new_id}`. Folder mapping via `_BOX_TO_FOLDER`: `ALL_MAIL→inbox`, `SENT→sentitems`, `SPAM→junkemail`.

### `move_to_trash(message_ids) → dict[str, str]`

Move messages to trash at the provider. Returns `{original_id: new_id}` for successfully trashed messages. For providers where the ID doesn't change on trash, `original_id == new_id`.

- **Gmail**: batch `messages.trash` in chunks of `_BATCH_SIZE` (100). Uses the same batch callback pattern as other batch operations. ID does not change on trash (`original_id == new_id`).
- **Outlook**: calls `POST /messages/{id}/move` with `destinationId` set to `deleteditems`. Serial loop per message. **The message ID changes** — the response contains the new message object with the new `id` field. Returns `{old_id: new_id}`.

### `DELETED` box value

A soft-delete marker. When the sync pipeline encounters a `DELETED` row and the provider reports `box = 'TRASH'`, the `CASE` logic in `UPSERT_EMAIL_METADATA_BATCH` and `UPDATE_LABELS_BATCH` preserves `DELETED` (prevents sync from overwriting the user's explicit delete). If sync reports a box **other than** `TRASH` for a `DELETED` row, it means the user restored the email manually at the provider, and the row is updated to the new box.

### `previous_box` column

Set by the `move_to_trash` operation. Before setting `box = 'TRASH'`, the current `box` value is copied into `previous_box`. The `restore` action reads `previous_box` to determine the destination folder. When `previous_box` is `NULL` (e.g. the email was already in trash when first synced), the service layer uses `fetch_messages_metadata` to discover the post-restore box from the provider instead of falling back to a hardcoded default.

## Public Operations

Beyond `authenticate`, `authenticate_silent`, and `fetch_email_metadata`, the `EmailClient` contract requires:

- **`send_email(subject, body, recipients) → EmailMetadata`** — send a plain text email. Returns metadata of the sent message.
- **`verify_message_existence(message_ids) → list[str]`** — return the subset of IDs that still exist at the provider. Used to confirm deletions or detect stale references.
- **`delete_messages(message_ids) → list[str]`** — permanently delete messages at the provider (see Trash Management Operations above).
- **`restore_from_trash(items) → dict[str, str]`** — restore messages from trash (see Trash Management Operations above).
- **`fetch_messages_metadata(message_ids) → list[EmailMetadata]`** — fetch current metadata for specific messages by ID. Returns metadata with `box` determined by the provider's label/folder state. Messages that cannot be fetched are silently skipped. Gmail: reuses the internal batch-fetch mechanism (`_execute_batch_get` + `_parse_metadata_response`). Outlook: resolves special folder IDs, fetches each message individually via `_graph_request`, classifies by `parentFolderId`.
- **`move_to_trash(message_ids) → dict[str, str]`** — move messages to trash at the provider (see Trash Management Operations above).
- **`update_read_status(message_ids, is_read) → list[str]`** — mark messages as read or unread at the provider. Returns the list of `provider_message_id`s that were successfully updated. Messages not found at the provider are silently skipped (no error raised). Gmail adds/removes the `UNREAD` label via batch `messages.modify`. Outlook patches each message with `PATCH /me/messages/{id}` setting `{"isRead": bool}`. Raises `EmailNotAuthenticatedError` if the client is not authenticated (guard), and `EmailExternalAPIError` on provider-level failures.
- **`move_to_spam(message_ids) → list[SpamMoveResult]`** — move messages to spam at the provider. Gmail adds the `SPAM` label via batch `messages.modify`. Outlook uses `POST /me/messages/{id}/move` with `destinationId: "junkemail"`. Returns `SpamMoveResult` pairs with `old_id` and `new_id`. **Outlook caveat**: the `/move` endpoint returns a new message ID; `SpamMoveResult.new_id` captures this (for Gmail, `new_id == old_id`). Raises `EmailNotAuthenticatedError` if not authenticated; silently skips failures for individual messages.
- **`restore_from_spam(message_ids) → list[SpamMoveResult]`** — restore messages from spam. Gmail removes the `SPAM` label and adds `INBOX` (replicating the "Not Spam" button behavior). Outlook uses `POST /me/messages/{id}/move` with `destinationId: "inbox"`. Same ID-change caveat as `move_to_spam`.
- **`get_account_label() → str`** — return the label identifying this account within the app.

### Data Structures — Spam Operations

### `SpamMoveResult`

Result of a spam move/restore operation for a single message:

- `old_id: str` — the original `provider_message_id`.
- `new_id: str` — the ID after the operation. Same as `old_id` for Gmail; different for Outlook (folder move changes the ID).

## Provider-Specific Behavior — Outlook Folder Moves

When Outlook moves a message between folders (via `POST /me/messages/{id}/move`), the message receives a **new ID**. The response body contains the moved message object with the updated `id` field. Any code that moves messages between folders must capture this new ID and propagate it to upper layers for database persistence. This applies to spam operations and any future folder-move operations.

## Extension

### New provider checklist

Core layer:

- [ ] Implement `EmailClient` in `backend/core/email/<provider>_client.py`.
- [ ] Implement all abstract methods: `authenticate`, `authenticate_silent`, `fetch_email_metadata`, `send_email`, `verify_message_existence`, `delete_messages`, `restore_from_trash`, `fetch_messages_metadata`, `move_to_trash`, `update_read_status`, `move_to_spam`, `restore_from_spam`, `get_account_label`.
- [ ] Reuse helper functions from `helpers.py`.
- [ ] Add provider branch in `EmailManager._build_client`.
- [ ] Raise typed `CoreError` subclasses for all failure paths.
- [ ] Export new public symbols in `core/email/__init__.py`.
- [ ] Add a PostToolUse hook in `.claude/settings.local.json` for the new `*_client.py` (see `.claude/hooks/reuse-reminder.sh`).

Cross-layer:

- [ ] Add provider env var mapping in `database/settings.py` and ensure `database/security/app_credentials.py` can load the new provider.
- [ ] Update provider CHECK constraint in `database/schema.sql`.
- [ ] Update `_CORE_TO_API_MAP` in `api/services/services_helpers.py` if new error types are introduced.
- [ ] Add unit tests, integration tests, and E2E coverage.
