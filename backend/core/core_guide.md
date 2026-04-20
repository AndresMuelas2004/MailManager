> **Permanent rule — read before editing this file.**
>
> This file is loaded into context on every Claude session. A line here only justifies its tokens if it cannot be reconstructed by reading the code.
>
> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**
> - **YES → delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.
> - **NO → keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, magic constants) that cannot be recomputed — those earn their tokens.
>
> **When updating this file, re-read every section and delete anything that has since migrated into the code.** Staleness is worse than silence.

# Email Client Implementation Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Helper Reuse Policy

Before writing new logic in `gmail_client.py`, `outlook_client.py`, or `email_manager.py`:

1. **Check `helpers.py` first.** Shared utilities (`parse_expiry`, `unwrap_app_credentials`, `unwrap_user_tokens`, `wrap_account_tokens`, `http_error_detail`, `inline_cid_images`, `decode_mime_body`) already cover the cross-provider needs.
2. **Then check private helpers in the file being edited.** Reuse or extend existing `_*` methods instead of duplicating.
3. **Extract when duplicated.** If both clients end up with similar logic, move the common part to `helpers.py` so both import it.

Applies to every modification — not just when adding a new provider.

## `_last_errors` — per-account error aggregation

`EmailManager` accumulates per-account failures in `_last_errors` (dict keyed by account label). Batch operations (`fetch_all_email_metadata`, `fetch_all_drafts`, `authenticate_all_silent`) collect per-client errors without aborting the others; the service layer inspects them afterwards via `get_last_errors()`.

**Gotchas:**
- `connect_account()` **resets** `_last_errors` at entry — any earlier errors are lost. Fine in practice because the interactive `/connect` endpoint never interleaves with batch operations, but worth remembering when writing new service functions.
- `connect_account()` re-raises the error directly (`raise EmailExternalAPIError(...) from exc`) instead of storing it in `_last_errors` — the interactive flow has a single account, so there is nothing to aggregate.

## `_execute_batch_get` retries; `_execute_batch_modify` does **not**

Gmail has two batch skeletons. Both chunk by `_BATCH_SIZE = 100` and dispatch to a `ThreadPoolExecutor`. The asymmetry is intentional:

- **`_execute_batch_get`** (reads) wraps each chunk in a retry loop (`_BATCH_MAX_RETRIES = 4`, `_BATCH_RETRY_DELAY = 1.0s`). Reads are idempotent — retrying is safe.
- **`_execute_batch_modify`** (read-status, trash, spam) is **single-pass**. A failing chunk is reported as failed; no retry. Writes are not idempotent, and accidentally doubling a label modification is worse than reporting a transient failure.

`fetch_drafts` reuses `_execute_batch_get` with `resource="drafts"`, so it inherits the retry loop.

## Service-stamped `EmailMetadata.account_id`

Provider clients leave `EmailMetadata.account_id` as `""`. The service layer stamps it before persistence. **Trap:** always stamp before calling `persist_email_metadata_batch` — skipping it writes empty strings into the DB, and if a client sets it the service overwrites anyway. Do not try to fix this by stamping in the client; the cross-layer contract is that the service owns it.

## Authentication — silent-refresh invariants

- **`email_address` is fetched only during the interactive `authenticate` flow**, never during silent refresh. The `upsert_tokens` SQL uses `COALESCE(%(email_address)s, email_address)` so silent refreshes don't erase a previously stored value. Do not "fix" silent auth to also fetch it — Gmail's silent flow doesn't expose it without a second round-trip.
- **Outlook rotates refresh tokens; Gmail doesn't.** Outlook's auth server may return a new `refresh_token` on every refresh — always persist the returned refresh token. Gmail's refresh token is stable in practice. The upsert path handles both uniformly, but don't skip writing `refresh_token` for Outlook on the assumption that it's unchanged.

## Email metadata sync — invariants

- **Box mapping priority** inside each client is `TRASH > SPAM > SENT > otherwise ALL_MAIL`. Any new Gmail label or Outlook folder must be threaded through this priority (`_FOLDER_TO_BOX` on Outlook, label check on Gmail); **do not introduce a new `box` value without also updating the DB CHECK constraint**.
- **Gmail bootstrap captures `historyId` *before* listing messages.** Any emails arriving during the list window are thus replayed on the next incremental sync. Do not reorder the two calls.
- **Gmail incremental falls back to bootstrap when event count > `_INCREMENTAL_EVENT_THRESHOLD = 100`.** Batch-fetching thousands of accumulated events costs more than a full re-sync.
- **Outlook delta is per-folder.** Microsoft Graph v1.0 does not support delta at the mailbox level, so the client iterates `_DELTA_FOLDERS` (`inbox`, `sentitems`, `drafts`, `deleteditems`, `junkemail`, `archive`) and stores a versioned JSON cursor `{"v": 1, "folders": {"inbox": "<deltaLink>", …}}`. A non-JSON / unversioned cursor (legacy single-URL format) decodes to `None` and triggers `EmailExternalAPIError → bootstrap fallback`.
- **Outlook fault tolerance:** during bootstrap delta init, a failing folder is logged and excluded from the cursor. During incremental, a failing folder keeps its previous deltaLink in the new cursor. If **all** folders fail during incremental, an error is raised to force bootstrap fallback — never accept an "incremental succeeded with zero events" when every folder errored.

## Trash — `delete_messages` intentionally breaks Provider-First

Both Gmail and Outlook use a **no-op** approach for `delete_messages`: the provider API is not called; deletion is marked only in the local DB. This is the one documented exception to the repo's Provider-First Rule (see `repository_guide.md`).

**Why:** Gmail's `gmail.modify` scope cannot call `messages.delete` (that requires the restricted `mail.google.com` scope). Since one provider can't perform permanent deletion without a scope upgrade, we adopt a uniform no-op across all providers so behaviour is consistent and predictable.

**Effect:** the provider retains the messages in Trash until its own retention policy purges them (Gmail ~30 days; Outlook per-tenant). The DB marks them `box = 'DELETED'` as a soft-delete guard — see the `DELETED` CASE logic documented in `database_guide.md`.

## Outlook — folder moves always rewrite the ID

`POST /me/messages/{id}/move` returns a new message object with a new `id`. Any code that moves a message between folders (spam, trash, any future operation) **must** capture the new ID from the response and propagate it to the service layer for DB persistence. Do not assume `new_id == old_id` on Outlook — that assumption is true only on Gmail.

## Outlook — percent-encode every message ID in the URL path

Outlook Immutable IDs are base64-like strings containing `+`, `/`, and `=`, none of which are safe in URL path segments. Every call to `_graph_request` that interpolates a message/draft ID into the URL path **must** wrap it with `urllib.parse.quote(id, safe='')`. Without this, Graph returns 400 / 404 on any ID containing those characters.

## Outlook drafts — `Prefer: IdType="ImmutableId"` must be re-sent on every call

Drafts are created with `Prefer: IdType="ImmutableId"` so the ID survives state transitions. Graph does **not** remember that preference per-message — every follow-up call (PATCH / DELETE / send) must re-send the header. Drop it on any follow-up and Graph reinterprets the stored Immutable ID as a transient ID and returns 404. The implementation threads this via `_graph_request`'s keyword-only `extra_headers` parameter.

## Drafts — provider asymmetries

- **Cap per account:** both providers enforce `_DRAFTS_MAX_TOTAL = 100` most-recent drafts. Gmail inside `_list_all_draft_ids` + `_execute_batch_get(resource="drafts")` (parallel workers controlled by `GMAIL_BATCH_MAX_WORKERS`, default 5). Outlook inside the paginated `$top=100&$orderby=lastModifiedDateTime desc` loop + 4 retries per page.
- **Gmail ordering is by convention, not by docs.** `drafts.list` has no `orderBy` parameter and returns drafts in reverse-chronological order in practice. If this ever becomes unreliable, the cap semantics break — track it.
- **Send-draft ID asymmetry:** Gmail's `drafts().send()` returns a Message with a **new** `id` (and auto-deletes the draft). Outlook's `POST /messages/{id}/send` returns 202; the message ID stays the **same** thanks to ImmutableId. Callers and tests must not assume equality.
- **Send-draft retry policy:** both clients retry up to 3 attempts (`_SEND_DRAFT_MAX_ATTEMPTS = 3`, `_SEND_DRAFT_RETRY_DELAY = 1.0s`). Gmail retries only on `_RETRYABLE_STATUS_CODES` (429, 5xx); Outlook retries every `EmailExternalAPIError` — by design, because Graph returns a narrower error surface.

## Extension — new provider checklist

Core layer:

- [ ] Subclass `EmailClient` in `backend/core/email/<provider>_client.py`. Implement every abstract method on the contract — the class will not import without them.
- [ ] `fetch_drafts` MUST enforce `_DRAFTS_MAX_TOTAL = 100` by the provider's timestamp field (most recent first).
- [ ] Raise typed `CoreError` subclasses on every failure path; no bare `Exception` leaks.
- [ ] Reuse helpers from `helpers.py` (see Helper Reuse Policy above).
- [ ] Add a provider branch in `EmailManager._build_client`.
- [ ] Export new public symbols in `core/email/__init__.py`.

Cross-layer:

- [ ] Add provider env var mapping in `database/settings.py`; extend `database/security/app_credentials.py` if JSON parsing differs.
- [ ] Update the provider CHECK constraint in `database/schema.sql` via a new Alembic migration (and `migrations/runner.py` — see `database_guide.md`).
- [ ] Extend `_CORE_TO_API_MAP` in `api/services/services_helpers.py` if the provider introduces new error types.
- [ ] Add unit, integration, and E2E coverage (see each test guide's Extension Checklist).
