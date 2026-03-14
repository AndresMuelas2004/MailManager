> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# E2E Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`general_e2e_rules.md`](./general_e2e_rules.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### `GOOGLE_CLIENT_ID` derived automatically

`GOOGLE_CLIENT_ID` is **not required** as an env var — the `_setup_google_client_id` fixture extracts the `client_id` from the credentials file pointed to by `MIA_GMAIL_CREDENTIALS_PATH` at runtime.

### Test file variants

- `test_full_flow.py` — Full dual-provider flow (Gmail + Outlook).
- `test_full_flow_gmailonly.py` — Gmail-only variant (skips Outlook steps).

Each flow includes numbered tests plus auxiliary steps (08b for DB inspection pause, 99 for cleanup). If one step fails, subsequent steps are skipped.

## Flow Sequence (test_full_flow.py)

### Auth — login (steps 1–2)

| Step | Action | Endpoint | Interactive? |
|---|---|---|---|
| 1 | Google login (real OIDC) | `POST /auth/google` | Yes — browser |
| 2 | Get current user | `GET /auth/me` | No |

### Mailboxes, accounts, emails (steps 3–15)

| Step | Action | Endpoint | Interactive? |
|---|---|---|---|
| 3 | Create mailbox | `POST /mailboxes` | No |
| 4 | Create Gmail and Outlook accounts | `POST .../accounts` | No |
| 5 | Connect Gmail and Outlook | `POST .../connect` | Yes — browser per provider |
| 6 | Update Gmail label | `PATCH .../accounts/{id}` | No |
| 7 | Send email from each provider | `POST .../emails/send` | No |
| 8 | Sync email metadata | `POST .../emails/sync-metadata` | No |
| 8b | DB inspection pause | — | Yes — manual Enter key |
| 9–13 | List/get accounts and mailboxes | various GET | No |
| 14 | Delete mailbox | `DELETE /mailboxes/{mid}` | No |
| 15 | Confirm deletion | `GET /mailboxes/{mid}` → 404 | No |

### Auth — logout, re-login, delete (steps 16–19)

| Step | Action | Endpoint | Interactive? |
|---|---|---|---|
| 16 | Logout | `POST /auth/logout` | No |
| 17 | Re-login (reuses id_token) | `POST /auth/google` | No |
| 18 | Delete user account | `DELETE /auth/me` | No |
| 19 | Confirm auth deleted | `GET /auth/me` → 401 | No |

## Behavioral Contracts — Traps to Avoid

### Step 99 cleanup

Step 99 deletes the test user via **direct SQL DELETE + COMMIT**, triggering CASCADE cleanup. This runs outside the module-level transaction rollback isolation — it explicitly commits to ensure data created during interactive steps (which are committed by the real app) is cleaned up even if earlier steps fail.

### Manual interaction

- **Step 1**: Browser opens for Google login consent.
- **Step 5**: One browser popup per provider for OAuth consent.
- **Step 17**: Reuses the same `id_token` from step 1 (valid ~1 hour). No browser needed.
- Current test payload sends emails to a hardcoded recipient in the test file.
