# E2E Tests (`backend/tests/e2e`)

## Purpose

E2E tests validate the full backend flow against real provider APIs.
No provider calls are mocked in this suite.

Covered boundaries:

- FastAPI routing
- Service orchestration
- Database persistence
- OAuth connect flow
- Real Gmail and Outlook API operations

## What Is Real vs Isolated

| Component | Behavior in E2E |
|---|---|
| FastAPI app | Real app created via `create_app()` |
| Email providers | Real Gmail/Outlook APIs |
| OAuth flow | Real browser-based interactive flow |
| Database | Real PostgreSQL connection |
| DB cleanup | Session transaction rollback at teardown |

## Prerequisites

The suite is skipped automatically when prerequisites are missing.

Required environment variables:

- `DATABASE_URL`
- `MIA_GMAIL_CREDENTIALS_PATH`
- `MIA_OUTLOOK_CREDENTIALS_PATH`

Token persistence note:

- E2E connect flow persists account tokens in DB.
- If encryption dependencies/config are unavailable, runtime may use temporary plaintext fallback depending on backend settings.

Validation behavior:

- `DATABASE_URL` must be present.
- Credential env vars must point to existing files.

Runtime requirements:

- Internet access
- Browser available for OAuth authorization steps

## How to Run

```bash
python -m pytest backend/tests/e2e -v -s
```
Why `-s` matters:

- OAuth URLs may be printed when browser auto-open fails.
- Output is needed for manual interaction and debugging.

## Test File Layout

Main flow file:

- `test_full_flow.py`

The flow is intentionally split into 13 endpoint-level tests so failures are pinpointed quickly.
If one step fails, subsequent steps are skipped to avoid cascade noise.

## Flow Sequence (13 Steps)

| Step | Action | Endpoint |
|---|---|---|
| 1 | Create mailbox | `POST /mailboxes` |
| 2 | Create Gmail and Outlook accounts | `POST /mailboxes/{mid}/accounts` |
| 3 | Connect Gmail and Outlook | `POST /mailboxes/{mid}/accounts/{id}/connect` |
| 4 | Update Gmail label | `PATCH /mailboxes/{mid}/accounts/{id}` |
| 5 | Send one email from each provider account | `POST /mailboxes/{mid}/emails/send` |
| 6 | Fetch unread emails | `GET /mailboxes/{mid}/emails/unread` |
| 7 | List accounts | `GET /mailboxes/{mid}/accounts` |
| 8 | Get Gmail account detail | `GET /mailboxes/{mid}/accounts/{id}` |
| 9 | Delete Outlook account | `DELETE /mailboxes/{mid}/accounts/{id}` |
| 10 | List mailboxes | `GET /mailboxes` |
| 11 | Get mailbox detail | `GET /mailboxes/{mid}` |
| 12 | Delete mailbox | `DELETE /mailboxes/{mid}` |
| 13 | Confirm mailbox deletion | `GET /mailboxes/{mid}` -> `404` |

## Manual Interaction Notes

- OAuth consent must be completed for Gmail and Outlook during step 3.
- Test runtime depends on how quickly those browser steps are completed.
- Current test payload sends emails to a hardcoded recipient in `test_full_flow.py`.

## Failure Interpretation

Use this order for triage:

1. Missing env var or invalid credentials file -> suite skipped.
2. OAuth/connect failure -> likely provider auth config issue.
3. Send/fetch failure -> likely provider API permission, token, or account issue.
4. CRUD failure -> likely API/database regression.

## Extending E2E Coverage

When adding a new provider:

1. Add account creation for the provider.
2. Add connect step for the provider.
3. Add send-email step for the provider.
4. Ensure flow assertions include the new provider behavior.

The E2E suite should always represent the full set of supported providers.
