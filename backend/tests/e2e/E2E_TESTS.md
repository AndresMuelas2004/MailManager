# E2E Tests

## Purpose

End-to-end tests that exercise the full API flow against **real** Gmail and Outlook APIs. Nothing is faked — real OAuth, real email sending, real token persistence. Database writes are isolated via a transaction that is rolled back at session teardown.

## Prerequisites

1. **Environment variables** must be set and pointing to real files/directories:
   - `DATABASE_URL` — PostgreSQL connection string
   - `MIA_GMAIL_CREDENTIALS_PATH` — path to Gmail OAuth client JSON
   - `MIA_OUTLOOK_CREDENTIALS_PATH` — path to Outlook app credentials JSON
2. **Internet access** — tests call live provider APIs.
3. **A browser** — OAuth flows open the browser for user authorization.

If any env var is missing or points to an invalid path, the suite is automatically skipped.

## How to Run

```bash
python -m pytest backend/tests/e2e -v -s
```

The `-s` flag is **required** so pytest does not capture stdout — the user needs to see OAuth URLs if the browser doesn't open automatically.

## Flow Sequence

| Step | Action | Endpoint |
|------|--------|----------|
| 1 | Create mailbox | `POST /mailboxes` |
| 2 | Create Gmail account | `POST /mailboxes/{mid}/accounts` |
| 3 | Create Outlook account | `POST /mailboxes/{mid}/accounts` |
| 4 | Connect Gmail (browser OAuth) | `POST .../accounts/{id}/connect` |
| 5 | Connect Outlook (browser OAuth) | `POST .../accounts/{id}/connect` |
| 6 | Update Gmail label | `PATCH .../accounts/{id}` |
| 7 | Send email from Gmail | `POST .../emails/send` |
| 8 | Send email from Outlook | `POST .../emails/send` |
| 9 | Fetch unread emails | `GET .../emails/unread` |
| 10 | List accounts | `GET .../accounts` |
| 11 | Get Gmail account detail | `GET .../accounts/{id}` |
| 12 | Delete Outlook account | `DELETE .../accounts/{id}` |
| 13 | List mailboxes | `GET /mailboxes` |
| 14 | Get mailbox | `GET /mailboxes/{mid}` |
| 15 | Delete mailbox | `DELETE /mailboxes/{mid}` |
| 16 | Verify mailbox deleted | `GET /mailboxes/{mid}` → 404 |

## Manual Steps

During the test, the browser will open **twice** (once per provider). You must complete the OAuth authorization flow each time. Test duration depends on how fast you click.

## Extensibility Rule

> **IMPORTANT:** When a new email client/provider is added to the system, you **MUST** update this test to include:
> 1. One account creation step for the new provider
> 2. One connect step for the new provider
> 3. One send-email step from that account
>
> There must be **as many accounts as supported providers** and **as many email sends as accounts**.
