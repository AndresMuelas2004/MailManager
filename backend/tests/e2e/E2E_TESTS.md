# E2E Tests (`backend/tests/e2e`)

## Purpose

E2E tests validate the full backend flow against real provider APIs and real Google OIDC authentication. **Nothing is mocked or faked** — every component runs exactly as it would in production.

Covered boundaries:

- Google OIDC login (real browser-based interactive flow)
- Session management (real cookie-based sessions persisted in DB)
- FastAPI routing
- Service orchestration
- Database persistence (PostgreSQL)
- OAuth connect flow (Gmail and Outlook)
- Real Gmail and Outlook API operations (send, fetch)
- User account deletion with CASCADE cleanup

## What Is Real vs Isolated

| Component | Behavior in E2E |
|---|---|
| FastAPI app | Real app created via `create_app()` |
| Google OIDC login | Real interactive browser OAuth flow (`InstalledAppFlow` with `openid email profile` scopes) |
| Session validation | Real `require_session` dependency — cookie verified against DB |
| Email providers | Real Gmail/Outlook APIs |
| OAuth connect flow | Real browser-based interactive flow |
| Database | Real PostgreSQL connection |
| DB cleanup | Module transaction rollback at teardown |

## Prerequisites

The suite is skipped automatically when prerequisites are missing.

Required environment variables:

- `DATABASE_URL`
- `MIA_GMAIL_CREDENTIALS_PATH`
- `MIA_OUTLOOK_CREDENTIALS_PATH`

`GOOGLE_CLIENT_ID` is **not required** — it is derived automatically from `MIA_GMAIL_CREDENTIALS_PATH` at runtime (`_setup_google_client_id` fixture extracts the `client_id` from the credentials file).

Token persistence note:

- E2E connect flow persists account tokens in DB.
- If encryption dependencies/config are unavailable, runtime may use temporary plaintext fallback depending on backend settings.

Validation behavior:

- `DATABASE_URL` must be present.
- Credential env vars must point to existing files.

Runtime requirements:

- Internet access
- Browser available for OAuth authorization steps (Google login + Gmail connect + Outlook connect)

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

The flow is split into 19 endpoint-level tests so failures are pinpointed quickly. If one step fails, subsequent steps are skipped to avoid cascade noise.

## Flow Sequence (19 Steps)

### Auth — login (steps 1–2)

| Step | Action | Endpoint | Interactive? |
|---|---|---|---|
| 1 | Google login (real OIDC) | `POST /auth/google` | Yes — browser opens for Google consent |
| 2 | Get current user | `GET /auth/me` | No |

Step 1 uses `InstalledAppFlow` with `openid email profile` scopes to obtain a real `id_token` via browser OAuth. The token is sent to the backend, verified by `google.oauth2.id_token.verify_oauth2_token`, and the user is created in the database.

### Mailboxes, accounts, emails (steps 3–15)

| Step | Action | Endpoint | Interactive? |
|---|---|---|---|
| 3 | Create mailbox | `POST /mailboxes` | No |
| 4 | Create Gmail and Outlook accounts | `POST /mailboxes/{mid}/accounts` | No |
| 5 | Connect Gmail and Outlook | `POST /mailboxes/{mid}/accounts/{id}/connect` | Yes — browser opens for each provider |
| 6 | Update Gmail label | `PATCH /mailboxes/{mid}/accounts/{id}` | No |
| 7 | Send one email from each provider | `POST /mailboxes/{mid}/emails/send` | No |
| 8 | Sync email metadata | `POST /mailboxes/{mid}/emails/sync-metadata` | No |
| 9 | List accounts | `GET /mailboxes/{mid}/accounts` | No |
| 10 | Get Gmail account detail | `GET /mailboxes/{mid}/accounts/{id}` | No |
| 11 | Delete Outlook account | `DELETE /mailboxes/{mid}/accounts/{id}` | No |
| 12 | List mailboxes | `GET /mailboxes` | No |
| 13 | Get mailbox detail | `GET /mailboxes/{mid}` | No |
| 14 | Delete mailbox | `DELETE /mailboxes/{mid}` | No |
| 15 | Confirm mailbox deletion | `GET /mailboxes/{mid}` -> `404` | No |

### Auth — logout, re-login, delete account (steps 16–19)

| Step | Action | Endpoint | Interactive? |
|---|---|---|---|
| 16 | Logout | `POST /auth/logout` | No |
| 17 | Re-login (reuses id_token) | `POST /auth/google` | No |
| 18 | Delete user account | `DELETE /auth/me` | No |
| 19 | Confirm auth deleted | `GET /auth/me` -> `401` | No |

Step 18 (`DELETE /auth/me`) deletes the user row; CASCADE removes all associated mailboxes, accounts, tokens, and sessions.

## Manual Interaction Notes

- **Step 1**: Browser opens for Google login. The user must authenticate with their Google account to obtain a real `id_token`.
- **Step 5**: OAuth consent must be completed for Gmail and Outlook (one browser popup per provider).
- **Step 17**: Reuses the same `id_token` obtained in step 1 (valid for ~1 hour). No additional browser interaction needed.
- Test runtime depends on how quickly the browser steps are completed.
- Current test payload sends emails to a hardcoded recipient in `test_full_flow.py`.

## Failure Interpretation

Use this order for triage:

1. Missing env var or invalid credentials file -> suite skipped.
2. Google login failure -> credentials file invalid or `client_id` mismatch.
3. OAuth/connect failure -> likely provider auth config issue.
4. Send/fetch failure -> likely provider API permission, token, or account issue.
5. CRUD failure -> likely API/database regression.

## Extending E2E Coverage

When adding a new provider:

1. Add account creation for the provider.
2. Add connect step for the provider.
3. Add send-email step for the provider.
4. Ensure flow assertions include the new provider behavior.

The E2E suite should always represent the full set of supported providers.
