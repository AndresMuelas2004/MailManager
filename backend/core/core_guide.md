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

`EmailManager` stores per-account errors in `_last_errors` (dict keyed by account label). Operations like `fetch_all_email_metadata()`, `fetch_all_drafts()`, and `authenticate_all_silent()` collect per-client errors without aborting other clients. The service layer inspects these via `get_last_errors()` after each operation.

**Gotcha**: `connect_account()` also resets `_last_errors` at entry. The earlier errors are lost. In practice this is not a problem because `connect_account` is only invoked from the interactive `POST .../connect` endpoint and never interleaved with batch operations, but it is worth noting when writing new service functions.

**Note**: `connect_account()` re-raises the error directly (`raise EmailExternalAPIError(...) from exc`) without writing to `_last_errors` — the interactive flow has a single account, so there is nothing to aggregate, and the exception propagation is sufficient.

### `_execute_batch_modify` single-pass vs `_execute_batch_get` retry loop

The Gmail client uses two batch skeletons. Both split the work into chunks of `_BATCH_SIZE = 100` items and dispatch them to a `ThreadPoolExecutor` sized by `GMAIL_BATCH_MAX_WORKERS`. The asymmetry:

- **`_execute_batch_get` (reads)** wraps each chunk in a retry loop (`_BATCH_MAX_RETRIES = 4` attempts with `_BATCH_RETRY_DELAY = 1.0s` between them). Reads are idempotent so retries are safe.
- **`_execute_batch_modify` (writes: read-status, trash, spam)** is single-pass — a chunk that fails is reported as failed, no retry. Writes are not idempotent and accidentally doubling a label-mod operation is worse than a transient 503.

Both clients reuse `_execute_batch_get` for `fetch_drafts` (with `resource="drafts"`), inheriting the retry loop.

### `connect_account` contract

`EmailManager.connect_account(account_label, app_credentials)` is the manager-level wrapper around `client.authenticate()` for the interactive OAuth flow. Its error surface is:

- Re-raises `CoreError` subclasses from the underlying client (e.g. `EmailAuthError`, `EmailMissingAppCredentialsError`) verbatim so the service layer can translate them via `translate_connect_error`.
- Wraps any other unexpected exception in `EmailExternalAPIError`.
- Resets `_last_errors` at entry (see gotcha above).

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

After successful authentication, both clients fetch the authenticated user's email address (best-effort) and include it as `email_address` in the returned token record. Gmail uses `_fetch_sender_email()` (Gmail `getProfile` endpoint). Outlook uses `_fetch_sender_profile()` (Graph `/me`, JWT claims, or sent items fallback). The value is `None` if all fetch strategies fail.

### Silent flow (`authenticate_silent`)

Used before fetch/send. Returns `None` if token is still valid (no refresh needed), or wrapped updated tokens when refreshed.

**`email_address` not returned**: Gmail's silent auth does NOT include `email_address` in the token dict (only the interactive `authenticate` flow fetches it). The `COALESCE` pattern in the `upsert_tokens` SQL query prevents silent-refresh upserts from erasing a previously stored email_address.

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

1. Get current `historyId` from `getProfile` as `new_sync_cursor`. Captured **before** listing messages so that any emails arriving during the bootstrap window are guaranteed to be replayed in the next incremental sync.
2. List message IDs (paginated `messages.list`, `includeSpamTrash=True`).
3. Batch-fetch metadata in chunks of 100 (`format="metadata"`). When credentials are available, chunks run in parallel via `ThreadPoolExecutor`; otherwise falls back to sequential execution.

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

Mark messages as deleted locally without calling the provider API. Returns all provided IDs as "succeeded" so the service layer marks them as `DELETED` in the database. **This is the only operation that intentionally breaks the Provider-First Rule** (`repository_guide.md` section Provider-First Rule): it does not act on the provider before updating the DB.

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
- **`fetch_email_content(provider_message_id) → EmailContent`** — fetch the full body (HTML and/or plain text) for a single email. Gmail requires MIME tree traversal and base64url decoding via the private helper `_extract_body_from_payload` because the Gmail API (`format="full"`) returns the raw MIME structure with nested `parts[]` and base64url-encoded bodies. Outlook's Graph API (`$select=body`) returns the decoded HTML/text content directly — no decoding needed. Both raise `EmailNotAuthenticatedError` if not authenticated and `EmailExternalAPIError` on provider failures.
- **`create_draft(to_recipients, cc_recipients, bcc_recipients, subject, body_html) → DraftMetadata`** — create a draft message at the provider without sending. All fields may be empty (empty drafts are accepted). Gmail builds a `MIMEMultipart("alternative")` message with a single `MIMEText(body_html, "html")` part, base64url-encodes it, and calls `users().drafts().create()`. Outlook builds the JSON payload (`subject`, `body.contentType=HTML`, recipient arrays) and calls `POST /me/messages` **with the `Prefer: IdType="ImmutableId"` extra header**. The header is critical: without it, Outlook returns a mutable ID that changes when the draft is later sent or moved, breaking any subsequent lookups by `provider_draft_id`. The Outlook implementation extends `_graph_request` with a keyword-only `extra_headers` parameter to thread the header through. Both raise `EmailNotAuthenticatedError` if not authenticated and `EmailExternalAPIError` on provider failures.
- **`update_draft(provider_draft_id, to_recipients, cc_recipients, bcc_recipients, subject, body_html) → DraftMetadata`** — replace an existing draft's content at the provider (full-field replacement; every field is sent and overwrites the previous value). Gmail reuses `_build_draft_raw_message` (the same helper used by `create_draft`) to produce the base64url-encoded MIME payload and calls `users().drafts().update(userId="me", id=provider_draft_id, body={"message": {"raw": ...}})`. Gmail preserves `draft.id` on update — the client returns the same `provider_draft_id` it received. Outlook reuses `_build_draft_graph_payload` and calls `PATCH /me/messages/{id}` **with the `Prefer: IdType="ImmutableId"` header repeated on every call** — the stored `provider_draft_id` is an Immutable ID, so Graph must be told again on each subsequent call to interpret the path parameter correctly. Both raise `EmailNotAuthenticatedError` if not authenticated and `EmailExternalAPIError` on provider failures. Timestamps in the returned `DraftMetadata` are best-effort (Gmail does not return them on update; Outlook does, but the service layer ignores them — the DB is the source of truth for `created_at`/`updated_at`).
- **`delete_draft(provider_draft_id) → None`** — delete a draft at the provider. Gmail calls `users().drafts().delete(userId="me", id=provider_draft_id)`. Outlook calls `DELETE /me/messages/{provider_draft_id}` with `Prefer: IdType="ImmutableId"`. Both raise `EmailNotAuthenticatedError` if not authenticated and `EmailExternalAPIError` on provider failures.
- **`get_account_label() → str`** — return the label identifying this account within the app.

### Data Structures — Email Content

### `EmailContent`

Full body content of a single email message:

- `html_body: str | None` — HTML version of the email body. Most modern emails include this.
- `text_body: str | None` — plain text version of the email body. Some simple emails only include this.

An email can have both, only one, or neither (rare). The fields are `None` when the corresponding content type is not present in the email.

### Data Structures — Spam Operations

### `SpamMoveResult`

Result of a spam move/restore operation for a single message:

- `old_id: str` — the original `provider_message_id`.
- `new_id: str` — the ID after the operation. Same as `old_id` for Gmail; different for Outlook (folder move changes the ID).

### Data Structures — Drafts

### `DraftMetadata`

Returned by `create_draft`. Carries the provider-assigned ID plus a round-tripped echo of the input fields:

- `provider_draft_id: str` — the draft identifier returned by the provider. For Outlook, this ID is stable across state transitions thanks to the `Prefer: IdType="ImmutableId"` header used at creation time.
- `to_recipients: list[str]`, `cc_recipients: list[str]`, `bcc_recipients: list[str]` — round-tripped recipients (the same lists the caller passed).
- `subject: str`, `body_html: str` — round-tripped subject and HTML body.
- `created_at: datetime`, `updated_at: datetime` — provider-reported timestamps when available (Outlook returns `createdDateTime`/`lastModifiedDateTime`); otherwise `datetime.now(timezone.utc)` as a soft fallback. The service layer does not forward these to the database; the `drafts` table uses `DEFAULT now()` for both columns, so the provider-reported timestamps have no effect on persistence.

### Draft fetch contract — `EmailClient.fetch_drafts() → list[DraftMetadata]`

Both Gmail and Outlook expose `fetch_drafts()` with identical semantics at the service layer: fetch the most recent drafts for the authenticated account and return them as a flat `list[DraftMetadata]`. Both implementations **cap the result at `_DRAFTS_MAX_TOTAL = 100` drafts per call**.

- **Gmail** (`drafts.list` + N × `drafts.get`): Gmail's `drafts.list` returns only `{id, message:{id, threadId}}`. A second round of per-draft `drafts.get` calls is required to get the full Message. `_list_all_draft_ids` paginates via `nextPageToken` and caps at `_DRAFTS_MAX_TOTAL`. The batch fetch reuses `_execute_batch_get` with `resource="drafts"` (parallel workers + retries). Gmail's `drafts.list` API does not support explicit `orderBy`; it returns drafts in reverse-chronological order by API convention (stable in practice, not guaranteed by the docs).
- **Outlook** (`/me/mailFolders/drafts/messages`): a single paginated endpoint returns the complete `Message` object per draft in one call. Uses `$top={_DRAFTS_PAGE_SIZE}`, `$orderby=lastModifiedDateTime desc`, and `Prefer: IdType="ImmutableId"`. Each page is retried up to `_DRAFTS_MAX_RETRIES = 4` times on transient `EmailExternalAPIError`, with `_DRAFTS_RETRY_DELAY = 1.0s` between attempts. Pagination loop stops as soon as `_DRAFTS_MAX_TOTAL` drafts are collected, regardless of whether `@odata.nextLink` is present.

`_parse_gmail_draft` extracts subject/to/cc/bcc from the Gmail `Message.payload.headers` and the HTML body via `_extract_html_body`. `_parse_outlook_draft` reads `subject`, `body.content`, `toRecipients[].emailAddress.address`, `ccRecipients`, `bccRecipients`, `createdDateTime`, `lastModifiedDateTime` from the Graph Message JSON.

### Manager-level — `EmailManager.delete_draft(account_label, provider_draft_id) → None`

Delegates to the registered client's `delete_draft(provider_draft_id)`. Raises `EmailAccountNotFoundError` if `account_label` is not registered.

### Manager-level — `EmailManager.fetch_all_drafts() → dict[str, list[DraftMetadata]]`

Iterates every registered client, calls `client.fetch_drafts()`, and returns `{account_label: list[DraftMetadata]}`. Per-account failures are **captured in `self._last_errors`** (never re-raised directly) — same error-aggregation pattern as `fetch_all_email_metadata`. It is the **caller's responsibility** to inspect `get_last_errors()` after calling `fetch_all_drafts()` and decide how to surface them (translate, log, ignore). The core layer only guarantees capture; translation into API-layer errors is not part of this contract.

## Provider-Specific Behavior — Outlook Folder Moves

When Outlook moves a message between folders (via `POST /me/messages/{id}/move`), the message receives a **new ID**. The response body contains the moved message object with the updated `id` field. Any code that moves messages between folders must capture this new ID and propagate it to upper layers for database persistence. This applies to spam operations and any future folder-move operations.

## Extension

### New provider checklist

Core layer:

- [ ] Implement `EmailClient` in `backend/core/email/<provider>_client.py`.
- [ ] Implement all abstract methods: `authenticate`, `authenticate_silent`, `fetch_email_metadata`, `send_email`, `verify_message_existence`, `delete_messages`, `restore_from_trash`, `fetch_messages_metadata`, `move_to_trash`, `update_read_status`, `move_to_spam`, `restore_from_spam`, `fetch_email_content`, `create_draft`, `update_draft`, `delete_draft`, `fetch_drafts`, `get_account_label`.
- [ ] `fetch_drafts` MUST enforce `_DRAFTS_MAX_TOTAL` (100) — return the most recent drafts according to the provider's timestamp.
- [ ] Reuse helper functions from `helpers.py`.
- [ ] Add provider branch in `EmailManager._build_client`.
- [ ] Raise typed `CoreError` subclasses for all failure paths.
- [ ] Export new public symbols in `core/email/__init__.py`.
- [ ] The helper reuse policy is enforced via the Helper Reuse Policy section at the top of this guide (not via a hook). The hook scripts (`reuse-reminder.sh`) exist as files but are not currently registered in `.claude/settings.local.json`.

Cross-layer:

- [ ] Add provider env var mapping in `database/settings.py` and ensure `database/security/app_credentials.py` can load the new provider.
- [ ] Update provider CHECK constraint in `database/schema.sql`.
- [ ] Update `_CORE_TO_API_MAP` in `api/services/services_helpers.py` if new error types are introduced.
- [ ] Add unit tests, integration tests, and E2E coverage.
