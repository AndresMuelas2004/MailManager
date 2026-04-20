> **Permanent rule — read before editing this file.**
>
> This file is loaded into context on every Claude session. A line here only justifies its tokens if it cannot be reconstructed by reading the code.
>
> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**
> - **YES → delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.
> - **NO → keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, magic constants) that cannot be recomputed — those earn their tokens.
>
> **When updating this file, re-read every section and delete anything that has since migrated into the code.** Staleness is worse than silence.

# API Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Endpoints that skip `require_session`

| Endpoint | Why |
|---|---|
| `GET /health` | Unauthenticated health check — no user context needed. |
| `POST /auth/google` | Creates the session — cannot require a prior one. |
| `POST /auth/logout` | Must work even with expired sessions. |

`DELETE /auth/me` requires `require_session`. After deleting the user row, PostgreSQL `CASCADE` takes care of every associated artefact (mailboxes, accounts, tokens, sessions); the service only clears the session cookie afterwards.

## Service Conventions

- **Ownership check first.** Every action scoped to a mailbox calls `ensure_mailbox_access(mailbox_id, user_id)` **before anything else**. It validates the mailbox exists and the authenticated user owns it, raising `MailboxNotFound` (404) or `Forbidden` (403). Skipping or reordering the call is an authorization bug.
- **Building provider clients.** Only via `build_manager_for_accounts(accounts)` — never instantiate `EmailClient` subclasses directly. The helper wraps `CoreError` and unexpected exceptions into `AccountMisconfigured` (400) so error handling is uniform across endpoints.
- **Secret wrapping.** Load credentials with `load_wrapped_app_credentials(provider)` / `load_wrapped_account_tokens(...)` (`pydantic.SecretStr`). Unwrap with `unwrap_secret()` only at the provider boundary.
- **Cookie management in the service, not the router.** Services that manage session cookies receive the `fastapi.Response` object from the router. Cookies are set/cleared in the service layer.
- **One endpoint per identity provider.** `POST /auth/google` is hardcoded to Google OIDC. When adding another identity provider, add a separate `POST /auth/<provider>` with its own schema and service function — **do not** create a generic endpoint with a `provider` parameter. Keeps each flow's validation and error translation isolated.

## Auth Context Sequence

When an endpoint must authenticate against a provider and then perform a provider call, the service function **must** follow this exact sequence. Skipping or reordering any step leads to silent token staleness, missing error surfacing, or unauthenticated provider calls. `drafts_service.create_draft` is the canonical reference implementation.

1. **Build the manager.** `manager = build_manager_for_accounts([account])` — wraps `EmailConfigError` into `AccountMisconfigured`.
2. **Load wrapped credentials and tokens.** `load_wrapped_app_credentials(provider)` + `load_wrapped_account_tokens(mailbox_id, account_id, provider)`. Tokens are unwrapped only at the provider boundary.
3. **Silent auth.** `updated_tokens = manager.authenticate_all_silent(auth_payloads)`. May refresh tokens in place.
4. **Persist refreshed tokens.** If `updated_tokens` is non-empty, call `account_store.upsert_tokens` for each. Any failure here must surface as the endpoint's primary error class (e.g. `DraftCreationError` for drafts, `EmailFetchError` for sync) — never let a token-persistence failure surface as a generic 500.
5. **Raise on silent auth errors.** `raise_on_silent_auth_errors(manager.get_last_errors(), fallback=<endpoint class>)` — turns per-client `EmailAuthError` into a single `AccountNotConnected` (409). **Call it again after the fetch** (`fetch_all_email_metadata`, `fetch_all_drafts`, …) — auth errors can also surface at fetch time and the same function handles both phases.
6. **Provider call.** Only now call `manager.send_email_from_account`, `manager.create_draft`, `manager.fetch_all_email_metadata`, etc. Wrap in `try / except CoreError / except Exception` per the layer `CLAUDE.md` §9.

## Traps and cross-file asymmetries

### `translate_connect_error` vs `translate_core_error`

For the interactive `/connect` flow, `EmailAuthError` maps to `AccountConnectAuthError` (**401**), not `AccountNotConnected` (409). Reason: a connect-time auth failure means the user's credentials are wrong, not that they need to call `/connect` again — 409 would create a retry loop on the same endpoint.

### `connect_account` response carries `email_address`

After a successful interactive OAuth flow, the service reads `email_address` from the Core layer's best-effort provider fetch and includes it in `AccountConnectResponse`. The field is `str | None`; `None` means the provider email fetch failed. `AccountOut` also exposes `email_address` from the `accounts` table so the frontend can list accounts with their email without a second round-trip.

### Ghost email reconciliation runs only after a full (bootstrap) sync

`_reconcile_ghost_emails` runs inside `sync-metadata` only when `is_full_sync=True`. It diffs stored `provider_message_id`s against `sync_result.upserts`, verifies suspect IDs against the provider via `verify_message_existence`, and deletes the ones the provider no longer reports. Every step is in its own `except Exception` — the reconciliation is best-effort and cannot fail the sync endpoint.

### `manage_trash` — TRASH verification gate + split restore flow

1. **TRASH verification gate.** Before any provider call, all referenced emails are checked to be in TRASH via `get_trash_emails_by_ids`. A missing row raises `EmailNotInTrash` (**409**, not 404 — the email exists but is in the wrong state).
2. **Split restore by `previous_box`.** After `manager.restore_from_trash`, items with a known `previous_box` go to `restore_from_trash_batch` (SQL uses `COALESCE(previous_box, 'ALL_MAIL')`). Items with `previous_box = NULL` require a second provider round-trip (`manager.fetch_messages_metadata` on the new IDs) to discover the post-restore box, then `restore_from_trash_discovered_batch` with the discovered value.

### `move_to_trash` — provider may rewrite the ID

`manager.move_to_trash` returns a `{old_id: new_id}` map. Outlook assigns a new ID on move; Gmail keeps the same ID. The service always writes the new ID into `provider_message_id`, copies the current `box` into `previous_box`, and sets `box = 'TRASH'`. Do not assume ID stability across trash operations.

### Spam — `restore_from_spam` target box is `ALL_MAIL`, not `INBOX`

The `/restore-from-spam` endpoint writes `ALL_MAIL` into the `box` column, consistent with the box-mapping convention that anything not in a special folder defaults to `ALL_MAIL`. Outlook's `/move` Graph endpoint additionally returns a new message ID (captured via `SpamMoveResult` and persisted).

### `send_email` — fire-and-forget metadata persistence

After a successful send, the service tries to persist the sent email's metadata. If that write fails, the error is **logged and swallowed** — the send is already reported as successful because the user cares that the email left the outbox, not that we tracked it. Same pattern applies to the best-effort DB operations inside `send_draft` (draft row delete + metadata insert).

### Outlook drafts — `Prefer: IdType="ImmutableId"` must be repeated on every call

Outlook drafts are created with `Prefer: IdType="ImmutableId"` so the ID stays stable across state transitions. Every subsequent PATCH / DELETE / SEND for that draft **must re-send the header** — Graph does not remember it per-message. Drop it on any follow-up call and Graph interprets the path parameter as a transient ID and returns 404.

### Draft endpoints — `DraftNotFound` pre-check lives before the provider call

`update_draft`, `delete_draft` and `send_draft` all call `draft_store.get(provider_draft_id, account_id)` **before** touching the provider. A 404 from our own DB must not cost a Gmail/Outlook round trip. The `drafts` primary key is composite `(provider_draft_id, account_id)` — both path params are mandatory for any draft mutation.

### Draft send — `provider_message_id` asymmetry between providers

`DraftSendOut.provider_message_id` differs from the draft ID on Gmail (Gmail creates a new Message when sending a draft) and equals it on Outlook (ImmutableId). Callers, tests and DB assertions must not assume equality. Both clients retry transient failures up to 3 total attempts (`_SEND_DRAFT_MAX_ATTEMPTS = 3`, `_SEND_DRAFT_RETRY_DELAY = 1.0`).

### Drafts sync — cap enforced in the client, not the service

`manager.fetch_all_drafts` caps each account at `_DRAFTS_MAX_TOTAL = 100` most-recent drafts. The cap lives inside `GmailClient._list_all_draft_ids` (paginated batch-of-100 skeleton with `GMAIL_BATCH_MAX_WORKERS` workers, default 5, and 4 retries per batch) and inside `OutlookClient.fetch_drafts` (`$top=100&$orderby=lastModifiedDateTime desc` + 4 retries per page). The service never filters — if the user has >100 drafts, the newest 100 win silently and no `truncated` flag is surfaced.

## Email content — HTML sanitization lives outside this file

The HTML sanitization pipeline used by `GET /mailboxes/{mid}/emails/{id}/content` lives in `api/services/email_html_pipeline.py` (`prepare_email_html`, re-exported by `services_helpers` as `sanitize_email_html` for legacy callers). The pipeline's non-obvious invariants and the **TRUNCATE-on-change rule for the `email_content` cache** are documented in the root `repository_guide.md` § "Email HTML rendering cache" — do not duplicate them here. The endpoint itself enforces a metadata pre-check (`email_metadata_store.exists` → 404 `email_not_found`) before the cache read because `email_content` has a composite FK to `email_metadata` (migration 0013); skipping the pre-check would surface FK violations as 500s.

## GET endpoint testing rule

DB-only GET endpoints (`list_emails`, `list_drafts`, …) must be integration-tested against the seeded data from migration 0010 with exact content assertions. GET endpoints that hit the provider (`get_email_full_content` cache-aside) need their own strategy documented per-endpoint. The canonical rules live in `backend/tests/integration/integration_guide.md` § "GET Endpoint Testing Rules".

## Service-layer error classes

All `ApiError` subclasses live in `api/errors/exceptions.py` and must be registered in `_STATUS_MAP` (`api/errors/handlers.py`). The base class defaults to 500.

- **Reuse before inventing.** Check the existing hierarchy before adding a new subclass.
- **Register in the same commit.** An unregistered `ApiError` silently defaults to 500 and its `code` never reaches the client.
- **Unique message per raise site.** The layer `CLAUDE.md` §7 is load-bearing: every `ApiError` raised directly by the service layer must carry a globally-unique `message`, so the message alone pinpoints the raise site. Especially important for the drafts services' outer safety nets (`DraftCreationError`, `DraftUpdateError`, `DraftDeleteError`, `DraftSendError`), where multiple `raise` statements in the same function would otherwise be indistinguishable.
- **Status quirks worth remembering:** `DatabaseQueryError` is 503 (transient-from-the-caller perspective, retryable), not 500. `EmailListError` / `DraftListError` are 500 because a listing failure is the only place that specific operation can fail and there is no retry story. 409s (`EmailNotInTrash`, `AccountNotConnected`, `AccountConnectAuthError` is 401) encode state conflicts, not plain missing resources — do not downgrade them to 404 when reusing.

## Extension

### New identity provider

- Add `POST /auth/<provider>` in `auth_routers.py` (thin route, single service call).
- Add `<provider>_login` in `auth_service.py` (catch `AuthError`, translate via `translate_auth_error`).
- Add request/response schemas in `api/schemas/auth.py`.
- The existing `AuthTokenError` subclasses are provider-agnostic and reusable. See `auth_guide.md` for the auth-layer side of the checklist.

### New draft operation

- Schema in `api/schemas/draft.py`.
- Service function in `api/services/drafts_service.py` following `create_draft`'s canonical sequence: `ensure_mailbox_access` → account lookup → outer `try: ... except ApiError: raise / except Exception: → <DraftXxxError>`.
- Provider interaction via `EmailManager` — extend `EmailManager` + each `*Client`. Provider-First: the provider call runs first, only persist to `drafts` if it succeeds.
- New `DraftXxxError` subclass in `exceptions.py` **and** its status in `handlers.py::_STATUS_MAP`.
- Unit / integration / E2E tests in the corresponding test dirs (see each test guide's Extension Checklist).
