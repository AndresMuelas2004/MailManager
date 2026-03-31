> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# E2E Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### Fully automated — no interactive steps

The E2E suite runs without any browser interaction or manual input. Authentication is handled by inserting a session directly into the database via `psycopg2`, bypassing the interactive Google OAuth flow.

Three endpoints are **excluded** from the automated suite because they require interactive OAuth or depend on it:

| Endpoint | Reason |
|---|---|
| `POST /auth/google` | Initiates interactive browser OAuth flow |
| `POST /mailboxes/{mid}/accounts/{aid}/connect` | Initiates interactive per-provider OAuth flow |
| `DELETE /auth/me` | Cannot create a test user without `POST /auth/google` |

These endpoints are verified manually by the developer with scripts.

### `GOOGLE_CLIENT_ID` derived automatically

`GOOGLE_CLIENT_ID` is **not required** as an env var — the `_setup_google_client_id` fixture extracts the `client_id` from the credentials file pointed to by `MIA_GMAIL_CREDENTIALS_PATH` at runtime.

### Test configuration in `e2e_config.py`

Pre-existing test account identifiers are centralized in `e2e_config.py` with env var overrides. These accounts must exist in the database with valid OAuth refresh tokens before running the suite.

### Pre-existing test accounts — one per provider

The E2E suite requires **one real, authenticated account per supported email provider** (i.e., per client implementation in `backend/core/email/`). Each account is linked to a real mailbox owned by the developer and must have valid OAuth tokens in the database.

Current accounts:

| provider | account_id | mailbox_id | display_label |
|---|---|---|---|
| gmail | `9805b672-032b-4d74-9696-4db53a5eb512` | `28a83414-36f5-4115-ab61-977d5a06a8e1` | pruebaGmail |
| outlook | `3c55eb17-9d5e-4d31-a3b5-14c6c24279b9` | `b61e15d5-153e-42ee-a4c6-2c943bd13c07` | pruebaOutlook |

**Extension rule**: when a new email provider is added to `backend/core/email/`, a corresponding test account must be created and registered in `e2e_config.py`, and the E2E suite must be extended with provider-specific tests (sync, send, read-status, spam, trash) for that account.

### Session injected via direct DB insert

The `e2e_session` fixture creates a real session row in the `sessions` table using a separate `psycopg2` connection (not the app's pool). The session cookie is set on the `TestClient`. `require_session` validates it against the real database.

### Test independence model

No global "skip all after first failure". Each test checks its own prerequisites via `flow_state` keys using the `_require()` helper. If a prerequisite is missing (because the producing test failed), the dependent test shows `SKIPPED`. Independent tests always run.

## Flow Sequence (test_full_flow.py)

### Section 1: Health (test 01)

| Test | Endpoint | Dependencies |
|---|---|---|
| 01 | `GET /health` | independent |

### Section 2: Auth read (test 02)

| Test | Endpoint | Dependencies |
|---|---|---|
| 02 | `GET /auth/me` | independent |

### Section 3: CRUD — temp mailbox + accounts (tests 03–14)

| Test | Endpoint | Dependencies |
|---|---|---|
| 03 | `POST /mailboxes` | independent → produces `temp_mid` |
| 04 | `POST .../accounts` (gmail) | requires `temp_mid` → produces `temp_gmail_id` |
| 05 | `POST .../accounts` (outlook) | requires `temp_mid` → produces `temp_outlook_id` |
| 06 | `GET /mailboxes` | requires `temp_mid` |
| 07 | `GET /mailboxes/{mid}` | requires `temp_mid` |
| 08 | `GET .../accounts` | requires `temp_mid` |
| 09 | `GET .../accounts/{aid}` (gmail) | requires `temp_gmail_id` |
| 10 | `GET .../accounts/{aid}` (outlook) | requires `temp_outlook_id` |
| 11 | `PATCH .../accounts/{aid}` | requires `temp_gmail_id` |
| 12 | `DELETE .../accounts/{aid}` | requires `temp_outlook_id` |
| 13 | `DELETE /mailboxes/{mid}` | requires `temp_mid` → produces `temp_mid_deleted` |
| 14 | `GET /mailboxes/{mid}` → 404 | requires `temp_mid_deleted` |

### Section 4: Provider operations — pre-existing accounts (tests 15–22)

| Test | Endpoint | Dependencies |
|---|---|---|
| 15 | `POST .../emails/sync-metadata?account_id=` (gmail, single-account bootstrap) | independent → produces `gmail_path1_done` |
| 16 | `POST .../emails/sync-metadata?account_id=` (outlook, single-account bootstrap) | independent → produces `outlook_path1_done` |
| 17 | `POST .../emails/sync-metadata` (gmail, all-accounts sync) | independent |
| 18 | `POST .../emails/sync-metadata` (outlook, all-accounts sync) | independent |
| 19 | `POST .../emails/send` (gmail) | independent |
| 20 | `POST .../emails/send` (outlook) | independent |
| 21 | `PATCH .../emails/read-status` (gmail) | independent |
| 22 | `PATCH .../emails/read-status` (outlook) | independent |

### Section 5: Spam operations — pre-existing accounts (tests 23–26)

| Test | Endpoint | Dependencies |
|---|---|---|
| 23 | `POST .../emails/spam` (gmail) | independent (syncs first internally) → produces `gmail_spam_done` |
| 24 | `POST .../emails/restore-from-spam` (gmail) | requires `gmail_spam_done` → produces `gmail_spam_restore_done` |
| 25 | `POST .../emails/spam` (outlook) | independent (syncs first internally) → produces `outlook_spam_done` |
| 26 | `POST .../emails/restore-from-spam` (outlook) | requires `outlook_spam_done` |

Each spam test syncs metadata first, picks 10 `ALL_MAIL` emails, moves them to spam, and verifies the DB `box` column changed. Restore tests reverse the operation on 10 `SPAM` emails. Tests skip if fewer than 10 qualifying emails exist.

### Section 6: Trash lifecycle — pre-existing accounts (tests 27–31)

| Test | Endpoint | Dependencies |
|---|---|---|
| 27 | `POST .../emails/move-to-trash` (gmail + outlook) | requires `gmail_path1_done` AND `outlook_path1_done` → produces `move_to_trash_done` |
| 28 | `POST .../emails/trash` (gmail, restore) | requires `move_to_trash_done` → produces `gmail_trash_restore_done` |
| 29 | `POST .../emails/trash` (gmail, delete) | requires `move_to_trash_done` → produces `gmail_delete_done` |
| 30 | `POST .../emails/trash` (outlook, delete) | requires `move_to_trash_done` → produces `outlook_delete_done` |
| 31 | `POST .../emails/trash` (outlook, restore) | requires `move_to_trash_done` → produces `outlook_restore_done` |

### Section 7: Auth lifecycle — MUST BE LAST (tests 32–33)

| Test | Endpoint | Dependencies |
|---|---|---|
| 32 | `POST /auth/logout` | independent → produces `logged_out` |
| 33 | `GET /auth/me` → 401 | requires `logged_out` |

## Behavioral Contracts — Traps to Avoid

### Safety-net cleanup in fixture teardown

The `created_resources` fixture tracks temp mailbox IDs and session IDs. On teardown, the `e2e_session` fixture deletes these via direct SQL, ensuring no orphan data remains even if tests fail mid-flow.

### Pre-existing test data is sacred

The pre-existing user, mailboxes, and accounts (defined in `e2e_config.py`) must NEVER be deleted, edited, or modified by the test suite. Provider operation tests (sync, send) use these accounts but only perform additive/idempotent operations.

### Auth lifecycle tests must be last

`POST /auth/logout` (test 32) invalidates the session cookie. Any test running after it will get 401. This is why Section 7 is the final section.

### Section 7. Extension Checklist

When adding a new provider:

- [ ] Add account creation for the provider.
- [ ] Add connect step for the provider.
- [ ] Add operation steps (send, fetch, etc.) for the provider.
- [ ] Ensure flow assertions include the new provider behavior.

The E2E suite should always represent the full set of supported providers.