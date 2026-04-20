> **Permanent rule — read before editing this file.**
>
> This file is loaded into context on every Claude session. A line here only justifies its tokens if it cannot be reconstructed by reading the code.
>
> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**
> - **YES → delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.
> - **NO → keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, magic constants) that cannot be recomputed — those earn their tokens.
>
> **When updating this file, re-read every section and delete anything that has since migrated into the code.** Staleness is worse than silence.

# Unit Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Project-Specific Notes

### Coverage inventory is the tree itself

The canonical inventory of what this layer covers is the `tests/unit/` directory tree. When a new service module is added (e.g. `drafts_service.py`), add a sibling `test_<module>.py`. Do not maintain a manual coverage catalog here — it rots faster than the code.

### Service test pattern — one `_patch_common` per service

Service-layer tests use inline `FakeStore` classes combined with `monkeypatch.setattr` to replace the real store module attributes, avoiding database access entirely. Each service test file owns its own `_patch_common`, tailored to that service's dependencies — `test_drafts_service.py` patches `draft_store.create`, `test_emails_service.py` patches the email persistence helpers. **Do not copy `_patch_common` verbatim across files**; match the patch set to the service's actual dependencies, or tests will silently fall through to real DB / provider paths.

### `test_emails_service.py` — patch helpers are independent, not layered

`_patch_read_status` and `_patch_spam` are **not** extensions of `_patch_common`. They apply a narrower patch set: they omit `account_store.get` and the metadata persistence helpers (read-status and spam don't need single-account lookup or metadata persistence), and add `update_email_read_status_batch` / `update_email_spam_status_batch` respectively. Treat them as independent helpers — extending them from `_patch_common` will over-patch.

`_patch_get_content_common` patches `email_metadata_store.exists → True` by default (metadata row present, so the service's pre-check short-circuits); tests that need a missing metadata row override this patch explicitly. It does **not** patch `get_email_content` — each test inside `TestGetEmailFullContent` patches it independently to control the cache-hit vs cache-miss branch.

### `FakeEmailClient` call-record asymmetries

`tests/shared/email_fakes.py::FakeEmailClient` records invocations of draft operations on `*_calls` lists. The lists intentionally use different tuple shapes per operation — do not assume a uniform schema:

- `create_draft_calls` — 5-tuple `(to, cc, bcc, subject, body_html)`.
- `update_draft_calls` — 6-tuple `(provider_draft_id, to, cc, bcc, subject, body_html)`. Extra leading `provider_draft_id`.
- `delete_draft_calls` — `list[str]` of bare `provider_draft_id`s (not tuples).
- `send_draft_calls` — `list[str]` of bare `provider_draft_id`s; `send_draft_return` returns an `EmailMetadata` (the sent message), not a `DraftMetadata`.

### `TestSyncDrafts` — `RuntimeError` asymmetry vs `send_email`

When `fetch_drafts_exc=RuntimeError(...)`, `EmailManager.fetch_all_drafts` captures the error in `_last_errors` — it does **not** wrap it into `EmailExternalAPIError` the way `send_email` does. As a result, the service surfaces `DraftSyncError` (the fallback passed to `raise_on_silent_auth_errors`), not `ExternalAPIError`. Tests asserting 502 `external_api_error` here will fail — assert `draft_sync_error` instead.

### Drafts cap tests live at the client layer, not the service

`_DRAFTS_MAX_TOTAL = 100` is enforced inside `GmailClient._list_all_draft_ids` (single page + paginated) and inside `OutlookClient.fetch_drafts`' `$top=100` loop. `TestSyncDrafts` uses `FakeEmailClient.fetch_drafts_return`, which bypasses both loops entirely and cannot exercise the cap. Any change to `_DRAFTS_MAX_TOTAL` requires updating `test_gmail_client.py::TestFetchDrafts` and `test_outlook_client.py::TestFetchDrafts`.

### `PgDraftStore` error-wrapping invariants

Non-obvious guards verified by `test_draft_repository.py`:

- **`ConnectionPoolError` must propagate unchanged.** The repository's `except DatabaseError: raise` guard distinguishes pool exhaustion from query errors. Every method's test class includes a test that injects `ConnectionPoolError` and asserts it surfaces as-is (not re-wrapped as `QueryError`). If you add a new method, include this test too.
- **`UPDATE ... RETURNING` yielding no row → `QueryError("Draft row to update not found.")`.** This covers the race where the service pre-check (`draft_store.get`) succeeds but another caller deletes the row before the `UPDATE` lands. Without this explicit path the update would silently succeed with a `None` return.
- **`replace_all_for_account` with `[]` intentionally wipes every row for the account.** The UPSERT is skipped but `DELETE_DRAFTS_MISSING_FOR_ACCOUNT` still runs with `keep_ids=[]`. Do not add a guard that short-circuits on empty input — tests rely on the delete running.
