# E2E Tests

## Purpose

End-to-end tests that exercise the full API flow against **real** Gmail and Outlook APIs. Nothing is faked: real OAuth, real email sending, real token persistence. Database writes are isolated via a transaction that is rolled back at session teardown.

## Prerequisites

1. **Environment variables** must be set and pointing to real files/directories:
   - `DATABASE_URL`: PostgreSQL connection string
   - `MIA_GMAIL_CREDENTIALS_PATH`: path to Gmail OAuth client JSON
   - `MIA_OUTLOOK_CREDENTIALS_PATH`: path to Outlook app credentials JSON
2. **Internet access**: tests call live provider APIs.
3. **A browser**: OAuth flows open the browser for user authorization.

If any env var is missing or points to an invalid path, the suite is automatically skipped.

## How to Run

```bash
python -m pytest backend/tests/e2e -v -s
```

The `-s` flag is required so pytest does not capture stdout: the user needs to see OAuth URLs if the browser does not open automatically.

## Test Structure

`test_full_flow.py` is split into **13 tests** (one per endpoint-level step in the flow). This gives a clear report like `N passed` and pinpoints the first failing endpoint.

If a step fails, remaining steps are marked as `skipped` automatically to avoid cascade failures caused by missing state from previous steps.

## Flow Sequence (13 tests)

| Test | Action | Endpoint |
|------|--------|----------|
| 1 | Create mailbox | `POST /mailboxes` |
| 2 | Create Gmail + Outlook accounts | `POST /mailboxes/{mid}/accounts` |
| 3 | Connect Gmail + Outlook (browser OAuth) | `POST /mailboxes/{mid}/accounts/{id}/connect` |
| 4 | Update Gmail label | `PATCH /mailboxes/{mid}/accounts/{id}` |
| 5 | Send email from Gmail + Outlook | `POST /mailboxes/{mid}/emails/send` |
| 6 | Fetch unread emails | `GET /mailboxes/{mid}/emails/unread` |
| 7 | List accounts | `GET /mailboxes/{mid}/accounts` |
| 8 | Get Gmail account detail | `GET /mailboxes/{mid}/accounts/{id}` |
| 9 | Delete Outlook account | `DELETE /mailboxes/{mid}/accounts/{id}` |
| 10 | List mailboxes | `GET /mailboxes` |
| 11 | Get mailbox | `GET /mailboxes/{mid}` |
| 12 | Delete mailbox | `DELETE /mailboxes/{mid}` |
| 13 | Verify mailbox deleted | `GET /mailboxes/{mid}` -> `404` |

## Manual Steps

During the test, the browser opens **twice** (once per provider). You must complete the OAuth authorization flow each time. Test duration depends on how fast you complete those authorizations.

## Extensibility Rule

When a new email client/provider is added to the system, you must update this flow to include:

1. One account creation call for the new provider.
2. One connect call for the new provider.
3. One send-email call from that provider account.

There must be as many provider accounts as supported providers, and as many send-email calls as provider accounts.