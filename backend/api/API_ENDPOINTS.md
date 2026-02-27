# API Endpoints Reference

This document defines the current HTTP contract exposed by the FastAPI backend.
All routes are synchronous and currently return `200 OK` on success unless noted otherwise.

All routes except `/health` require a valid `session_id` HttpOnly cookie (set by `POST /auth/google`).

## Base URL

Local development default:

- `http://localhost:8000`

## Health

| Method | Path | Description | Success Response |
|---|---|---|---|
| `GET` | `/health` | Health check endpoint. No auth required. | `{ "status": "ok" }` |

## Auth

Base path: `/auth`

### `POST /auth/google`

Verify a Google OIDC `id_token`, create a user (or update existing), and start a session.

Request body:

```json
{
  "id_token": "google-jwt-token"
}
```

Response body:

```json
{
  "user": {
    "user_id": "uuid",
    "email": "user@example.com",
    "name": "User Name",
    "avatar_url": "https://..."
  },
  "message": "Login successful."
}
```

Sets an HttpOnly `session_id` cookie on success.

### `GET /auth/me`

Return the currently authenticated user.

Response body:

```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "name": "User Name",
  "avatar_url": "https://..."
}
```

### `POST /auth/logout`

Delete the current session and clear the session cookie.

Response body:

```json
{
  "status": "logged_out"
}
```

### `DELETE /auth/me`

Delete the authenticated user and all associated data (mailboxes, accounts, tokens, sessions via CASCADE). Clears the session cookie.

Response body:

```json
{
  "status": "account_deleted"
}
```

Returns `404` with `user_not_found` if the user no longer exists.

## Mailboxes

Base path: `/mailboxes`

### `POST /mailboxes`

Create a mailbox. The authenticated user becomes the owner.

Request body:

```json
{
  "display_name": "Work"
}
```

Response body:

```json
{
  "mailbox_id": "uuid",
  "display_name": "Work",
  "owner_user_id": "uuid",
  "created_at": "2026-02-16T10:00:00+00:00"
}
```

### `GET /mailboxes`

List mailboxes owned by the authenticated user.

Response body:

```json
[
  {
    "mailbox_id": "uuid",
    "display_name": "Work",
    "owner_user_id": "uuid",
    "created_at": "2026-02-16T10:00:00+00:00"
  }
]
```

### `GET /mailboxes/{mailbox_id}`

Get a mailbox by ID. Returns 403 if the mailbox belongs to another user.

Response body:

```json
{
  "mailbox_id": "uuid",
  "display_name": "Work",
  "owner_user_id": "uuid",
  "created_at": "2026-02-16T10:00:00+00:00"
}
```

### `DELETE /mailboxes/{mailbox_id}`

Delete a mailbox. Returns 403 if the mailbox belongs to another user.

Response body:

```json
{
  "status": "deleted"
}
```

## Accounts

Base path: `/mailboxes/{mailbox_id}/accounts`

### `GET /mailboxes/{mailbox_id}/accounts`

List all accounts in the mailbox.

Response body:

```json
[
  {
    "account_id": "uuid",
    "mailbox_id": "uuid",
    "provider": "gmail",
    "display_label": "Primary Gmail",
    "config": {}
  }
]
```

### `POST /mailboxes/{mailbox_id}/accounts`

Create an account under a mailbox.

Request body:

```json
{
  "provider": "gmail",
  "display_label": "Primary Gmail",
  "config": {}
}
```

Response body:

```json
{
  "account_id": "uuid",
  "mailbox_id": "uuid",
  "provider": "gmail",
  "display_label": "Primary Gmail",
  "config": {}
}
```

### `GET /mailboxes/{mailbox_id}/accounts/{account_id}`

Get an account by mailbox and account ID.

Response body:

```json
{
  "account_id": "uuid",
  "mailbox_id": "uuid",
  "provider": "gmail",
  "display_label": "Primary Gmail",
  "config": {}
}
```

### `PATCH /mailboxes/{mailbox_id}/accounts/{account_id}`

Update mutable account fields.

Request body (all fields optional):

```json
{
  "display_label": "Renamed account",
  "config": {
    "folder": "inbox"
  }
}
```

Response body:

```json
{
  "account_id": "uuid",
  "mailbox_id": "uuid",
  "provider": "gmail",
  "display_label": "Renamed account",
  "config": {
    "folder": "inbox"
  }
}
```

### `DELETE /mailboxes/{mailbox_id}/accounts/{account_id}`

Delete an account.

Response body:

```json
{
  "status": "deleted"
}
```

### `POST /mailboxes/{mailbox_id}/accounts/{account_id}/connect`

Run interactive provider authentication for one account and persist tokens.

Response body:

```json
{
  "connected": true,
  "provider": "gmail",
  "account_id": "uuid",
  "account_label": "{mailbox_id}__{account_id}",
  "message": "Account connected successfully."
}
```

## Emails

Base path: `/mailboxes/{mailbox_id}/emails`

### `GET /mailboxes/{mailbox_id}/emails/unread`

Fetch unread emails across all accounts in the mailbox.

Response body:

```json
[
  {
    "message_id": "provider-id",
    "subject": "Hello",
    "sender": "name@example.com",
    "recipients": ["you@example.com"],
    "body": "Message preview",
    "sent_at": "2026-02-16T10:00:00+00:00",
    "is_unread": true,
    "provider": "gmail",
    "thread_id": "optional-thread-id",
    "raw_rfc822_b64url": "optional-raw-rfc822"
  }
]
```

### `POST /mailboxes/{mailbox_id}/emails/send`

Send an email from a specific account.

Request body:

```json
{
  "account_id": "uuid",
  "subject": "Subject",
  "body": "Body",
  "recipients": ["dest@example.com"]
}
```

Response body:

```json
{
  "status": "sent"
}
```

## Error Contract

Application errors use this structure:

```json
{
  "error": {
    "code": "account_not_found",
    "message": "Account '...' not found.",
    "detail": {}
  }
}
```

Mapped API error codes and status codes:

| Code | HTTP Status |
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
| `database_error` | `503` |

Additional notes:

- Validation failures from FastAPI/Pydantic return `422 Unprocessable Entity`.
- Unexpected unhandled exceptions return `500` with `code = "api_error"`.
- Requests without a valid `session_id` cookie return `401` with `code = "unauthorized"`.
- Requests to another user's mailbox return `403` with `code = "forbidden"`.
