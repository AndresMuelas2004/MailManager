# API Endpoints Reference

Base URL: `http://localhost:8000`

All routes except `/health`, `POST /auth/google`, and `POST /auth/logout` require a valid `session_id` HttpOnly cookie.

## Health

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/health` | — | `{ "status": "ok" }` |

## Auth

| Method | Path | Request | Response |
|---|---|---|---|
| `POST` | `/auth/google` | `{ id_token }` | `{ user: { user_id, email, name?, avatar_url? }, message }` + sets `session_id` cookie |
| `GET` | `/auth/me` | — | `{ user_id, email, name?, avatar_url? }` |
| `POST` | `/auth/logout` | — | `{ status: "logged_out" }` + clears cookie |
| `DELETE` | `/auth/me` | — | `{ status: "account_deleted" }` + clears cookie (cascades all user data) |

## Mailboxes

| Method | Path | Request | Response |
|---|---|---|---|
| `POST` | `/mailboxes` | `{ display_name }` | `{ mailbox_id, display_name, owner_user_id, created_at }` |
| `GET` | `/mailboxes` | — | `[ { mailbox_id, display_name, owner_user_id, created_at } ]` |
| `GET` | `/mailboxes/{mailbox_id}` | — | `{ mailbox_id, display_name, owner_user_id, created_at }` |
| `DELETE` | `/mailboxes/{mailbox_id}` | — | `{ status: "deleted" }` |

## Accounts

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/mailboxes/{mailbox_id}/accounts` | — | `[ { account_id, mailbox_id, provider, display_label, config } ]` |
| `POST` | `/mailboxes/{mailbox_id}/accounts` | `{ provider, display_label, config? }` | `{ account_id, mailbox_id, provider, display_label, config }` |
| `GET` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | — | `{ account_id, mailbox_id, provider, display_label, config }` |
| `PATCH` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | `{ display_label?, config? }` | `{ account_id, mailbox_id, provider, display_label, config }` |
| `DELETE` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | — | `{ status: "deleted" }` |
| `POST` | `/mailboxes/{mailbox_id}/accounts/{account_id}/connect` | — | `{ connected, provider, account_id, account_label, message }` |

## Emails

| Method | Path | Request | Response |
|---|---|---|---|
| `POST` | `/mailboxes/{mailbox_id}/emails/sync-metadata` | — | `{ total_synced, accounts: [ { account_id, provider, emails_synced, sync_cursor? } ] }` |
| `POST` | `/mailboxes/{mailbox_id}/emails/send` | `{ account_id, subject, body, recipients }` | `{ status: "sent" }` |

## Error Contract

```json
{ "error": { "code": "...", "message": "...", "detail": {} } }
```

| Code | HTTP |
|---|---|
| `unauthorized` | `401` |
| `forbidden` | `403` |
| `mailbox_not_found` | `404` |
| `account_not_found` | `404` |
| `user_not_found` | `404` |
| `account_misconfigured` | `400` |
| `account_connect_auth_error` | `401` |
| `account_not_connected` | `409` |
| `email_fetch_error` | `502` |
| `email_send_error` | `502` |
| `external_api_error` | `502` |
| `env_var_error` | `500` |
| `credential_file_error` | `500` |
| `database_connection_error` | `503` |
| `database_migration_error` | `500` |
| `database_query_error` | `503` |
| `token_decryption_error` | `500` |
| `token_integrity_error` | `500` |
| `app_credentials_invalid` | `500` |
| `app_credentials_missing` | `500` |
| `recipients_missing` | `400` |

Validation errors (Pydantic): `422`. Unhandled exceptions: `500` with `code = "api_error"`.
