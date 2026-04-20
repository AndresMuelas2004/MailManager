> **Permanent rule — read before editing this file.**
>
> This file is loaded into context on every Claude session. A line here only justifies its tokens if it cannot be reconstructed by reading the code.
>
> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**
> - **YES → delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.
> - **NO → keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, magic constants) that cannot be recomputed — those earn their tokens.
>
> **When updating this file, re-read every section and delete anything that has since migrated into the code.** Staleness is worse than silence.

# E2E Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### Fully automated — no interactive steps

The suite runs without any browser interaction. Authentication is handled by inserting a session directly into the `sessions` table via `psycopg2` (separate from the app's pool); `require_session` then validates it against the real database.

Three endpoints are **excluded** from the automated suite because they require interactive OAuth or depend on it, and are verified manually with scripts:

| Endpoint | Reason |
|---|---|
| `POST /auth/google` | Initiates interactive browser OAuth flow |
| `POST /mailboxes/{mid}/accounts/{aid}/connect` | Initiates interactive per-provider OAuth flow |
| `DELETE /auth/me` | Cannot create a test user without `POST /auth/google` |

### `GOOGLE_CLIENT_ID` derived automatically

`GOOGLE_CLIENT_ID` is **not** required as an env var — `_setup_google_client_id` extracts the `client_id` from the credentials file pointed to by `MIA_GMAIL_CREDENTIALS_PATH` at runtime.

### Test configuration in `e2e_config.py`

Pre-existing test account identifiers are centralized in `e2e_config.py` with env var overrides. These accounts must exist in the real database with valid OAuth refresh tokens before running the suite — the suite never creates or deletes them.

| Identifier | Env override | Default |
|---|---|---|
| `TEST_USER_ID` | `E2E_TEST_USER_ID` | developer's pre-seeded user UUID |
| `GMAIL_MAILBOX_ID` | `E2E_GMAIL_MAILBOX_ID` | `28a83414-36f5-4115-ab61-977d5a06a8e1` |
| `OUTLOOK_MAILBOX_ID` | `E2E_OUTLOOK_MAILBOX_ID` | `b61e15d5-153e-42ee-a4c6-2c943bd13c07` |
| `GMAIL_ACCOUNT_ID` | `E2E_GMAIL_ACCOUNT_ID` | `9805b672-032b-4d74-9696-4db53a5eb512` |
| `OUTLOOK_ACCOUNT_ID` | `E2E_OUTLOOK_ACCOUNT_ID` | `3c55eb17-9d5e-4d31-a3b5-14c6c24279b9` |
| `SEND_RECIPIENT` | `E2E_SEND_RECIPIENT` | `muelonmuelon12@gmail.com` |

`SEND_RECIPIENT` is the destination address used by every send and draft test. Override via `E2E_SEND_RECIPIENT` when running the suite where the default address is not available.

### Pre-existing test accounts — one per provider

The suite requires **one real, authenticated account per client implementation in `backend/core/email/`**. Each account is linked to a real mailbox owned by the developer and must have valid OAuth refresh tokens in the `accounts` table before the suite is run.

The `display_label` values live only in the database (not in any code file), so they must be documented here:

| provider | account_id | mailbox_id | display_label |
|---|---|---|---|
| gmail | `9805b672-032b-4d74-9696-4db53a5eb512` | `28a83414-36f5-4115-ab61-977d5a06a8e1` | `pruebaGmail` |
| outlook | `3c55eb17-9d5e-4d31-a3b5-14c6c24279b9` | `b61e15d5-153e-42ee-a4c6-2c943bd13c07` | `pruebaOutlook` |

**Extension rule**: when a new provider is added to `backend/core/email/`, create a corresponding real account in the database, register its identifiers in `e2e_config.py`, add the row to this table, and extend the suite with provider-specific tests (see Extension Checklist below).

### Test independence — no global skip-all

Each test checks its own prerequisites via `flow_state` keys using the `_require()` helper. If a dependency test fails, only the dependent test is `SKIPPED`; independent tests still run. There is no global "skip everything after the first failure" behavior.

## Traps and Behavioral Contracts

### Auth lifecycle tests must be LAST in the flow

`POST /auth/logout` invalidates the session cookie — any test running after it gets 401. The logout test and the 401-verification test live in the final section of `test_full_flow.py` for this reason. When adding new tests, always insert them **before** the logout section.

### Pre-existing test data is sacred

The pre-existing user, mailboxes, and accounts defined in `e2e_config.py` must NEVER be deleted, edited, or otherwise mutated by the suite. Provider operation tests (sync, send, drafts, spam, trash) use these accounts but only with additive/idempotent operations, plus cleanup of what the test itself created.

### Draft tests — cleanup pattern

Each draft test creates a draft at the real provider, verifies it, and cleans up via the DELETE endpoint or raw SQL `DELETE FROM drafts WHERE ...` in a `finally` block (safety net for the case where the send/update/delete failed mid-test). The verify step and the cleanup live in the **same** test function (per `common_mistakes.md` § 1) — do not split them into separate tests.

When drafts are **synced** from the provider (Section 5c), the draft is intentionally left at the provider after the test; only local rows are cleared via `_clear_local_drafts`. Provider-side cleanup for drafts is covered by the explicit delete and send sections.

### Provider-specific behavior worth knowing

- **Outlook** wraps plain HTML bodies in a full `<html>/<body>` structure via the Graph API. Outlook tests assert body content by containment (`"E2E updated body" in data["body_html"]`), not byte-for-byte equality. Gmail preserves the input HTML as-is.
- **Send-draft response IDs differ by provider**: Gmail returns a **new** `provider_message_id` (Gmail creates a new Message on send, different from the draft ID). Outlook returns the **same** ID as the draft thanks to `Prefer: IdType="ImmutableId"` used at draft creation.

### Safety-net cleanup in fixture teardown

The `created_resources` fixture tracks temp mailbox IDs and session IDs. On teardown, `e2e_session` deletes them via direct SQL, ensuring no orphan data remains even if a test fails mid-flow.

### `create_e2e_schema` — session-scoped, autouse

Runs Alembic migrations against the real E2E database once per session using `backend/database/alembic.ini`. If the database exists but has no `alembic_version` row, it stamps the existing tables as `0001_initial_schema` before upgrading to `head`. This keeps the suite idempotent across cold starts and post-migration runs.

## Extension Checklist — Adding a New Provider

When adding a new provider:

- [ ] Add account creation for the provider.
- [ ] Add connect step for the provider.
- [ ] Add operation steps (send, fetch, read-status, spam, trash) for the provider.
- [ ] Add a draft creation test for the provider.
- [ ] Add two draft sync tests (single-account and mailbox-wide) for the provider.
- [ ] Add a draft listing test for the provider.
- [ ] Add a draft update test for the provider — must create a draft first and clean up the local row afterward.
- [ ] Add a draft deletion test for the provider.
- [ ] Add a draft send test for the provider — must create a draft first, send it, and verify the local row was deleted. Safety-net cleanup in a `finally` block.
- [ ] Ensure flow assertions include the new provider behavior.

The E2E suite should always represent the full set of supported providers.
