# Email Client Implementation Guide

> **General rules**: this layer MUST respect every rule defined in
> [`general_core_rules.md`](./general_core_rules.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### `_last_errors` pattern

`EmailManager` stores per-account errors in `_last_errors` (dict keyed by account label). Operations like `fetch_all_email_metadata()` and `authenticate_all_silent()` collect per-client errors without aborting other clients. The service layer inspects these via `get_last_errors()` after each operation.

### Sync cursor contract

`fetch_all_email_metadata()` accepts an optional `sync_cursors` dict keyed by account label. Each client receives its cursor (or `None` for bootstrap). This is an `EmailManager`-level contract — individual clients receive their cursor as a parameter.

### `account_id` left empty — stamped by the service layer

`EmailMetadata.account_id` is left as `""` by provider clients. The service layer stamps it before persistence. This is a cross-layer contract: if a client sets it, the service overwrites it; if the service forgets to stamp it, the database will store an empty string. **Trap**: always stamp before calling `persist_email_metadata_batch`.

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

- `sync_cursor=None` → bootstrap (Path 1): fetch up to `max_total` messages from scratch.
- `sync_cursor` present → attempt incremental (Path 2). Falls back to bootstrap on invalid cursor or if not yet implemented.

### Box mapping convention

```
labelIds contains "TRASH" → box = "TRASH"
labelIds contains "SPAM"  → box = "SPAM"
labelIds contains "SENT"  → box = "SENT"
otherwise                 → box = "ALL_MAIL"
```

### Gmail batch fetch approach

List message IDs (paginated `messages.list`, `includeSpamTrash=True`) → batch-fetch metadata in chunks of 100 (`format="metadata"`) → get current `historyId` from `getProfile` as `new_sync_cursor`.

> Las constantes de batch (`_BATCH_SIZE`, `_BATCH_MAX_RETRIES`, `_BATCH_RETRY_DELAY`) son reutilizadas por scripts de desarrollo (`backend/Scripts/`) para extensiones como ejecución paralela de chunks.

### Gmail incremental sync (History API)

When `sync_cursor` is present and valid: paginate history, resolve deletes, filter label changes, batch-fetch metadata for added/changed messages, batch-fetch label updates. Falls back to bootstrap on invalid `historyId`.

### Outlook metadata sync (Delta Query)

Delta queries are **per folder** — Microsoft Graph v1.0 does not support delta at the mailbox level. The client iterates over `_DELTA_FOLDERS` (`inbox`, `sentitems`, `drafts`, `deleteditems`, `junkemail`), issuing `/me/mailFolders/{folder}/messages/delta` for each.

Bootstrap: for each folder, paginate until `@odata.deltaLink`. All messages become upserts. The cursor stored is a JSON object encoding per-folder deltaLinks: `{"v": 1, "folders": {"inbox": "https://...", ...}}`.

Incremental: decode the JSON cursor. For each folder that has a deltaLink, re-issue it. Messages with `@removed` become deletes; all others become upserts. `label_updates` always empty (Graph delta returns full objects for any change, so all modifications go to upserts).

Cursor format and legacy detection: the cursor is a JSON string with `{"v": 1, "folders": {...}}`. If `_decode_folder_cursors` encounters a non-JSON or differently versioned cursor (legacy format from old single-URL approach), it returns `None`, which triggers `EmailExternalAPIError` in `_incremental_email_metadata`, causing fallback to bootstrap.

Folder-to-box mapping: determined by folder name via `_FOLDER_TO_BOX` (`deleteditems`→TRASH, `junkemail`→SPAM, `sentitems`→SENT, all others→ALL_MAIL). No runtime folder ID resolution needed.

Fault tolerance: if a folder fails during bootstrap, it is skipped (logged) and excluded from the cursor. During incremental sync, a failed folder keeps its previous deltaLink in the new cursor. If **all** folders fail during incremental, an error is raised to trigger bootstrap fallback.

## Extension

### New provider checklist

Core layer:

- [ ] Implement `EmailClient` in `backend/core/email/<provider>_client.py`.
- [ ] Reuse helper functions from `helpers.py`.
- [ ] Add provider branch in `EmailManager._build_client`.
- [ ] Raise typed `CoreError` subclasses for all failure paths.
- [ ] Export new public symbols in `core/email/__init__.py`.

Cross-layer:

- [ ] Add provider env var mapping in `database/settings.py` and ensure `database/security/app_credentials.py` can load the new provider.
- [ ] Update provider CHECK constraint in `database/schema.sql`.
- [ ] Update `_CORE_TO_API_MAP` in `api/services/services_helpers.py` if new error types are introduced.
- [ ] Add unit tests, integration tests, and E2E coverage.
