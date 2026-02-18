# API Endpoints Reference

This document defines the current HTTP contract exposed by the FastAPI backend.
All routes are synchronous and currently return `200 OK` on success unless noted otherwise.

## Base URL

Local development default:

- `http://localhost:8000`

## Health

| Method | Path | Description | Success Response |
|---|---|---|---|
| `GET` | `/health` | Health check endpoint. | `{ "status": "ok" }` |

## Mailboxes

Base path: `/mailboxes`

### `POST /mailboxes`

Create a mailbox.

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
  "created_at": "2026-02-16T10:00:00+00:00"
}
```

### `GET /mailboxes`

List all mailboxes.

Response body:

```json
[
  {
    "mailbox_id": "uuid",
    "display_name": "Work",
    "created_at": "2026-02-16T10:00:00+00:00"
  }
]
```

### `GET /mailboxes/{mailbox_id}`

Get a mailbox by ID.

Response body:

```json
{
  "mailbox_id": "uuid",
  "display_name": "Work",
  "created_at": "2026-02-16T10:00:00+00:00"
}
```

### `DELETE /mailboxes/{mailbox_id}`

Delete a mailbox.

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
| `mailbox_not_found` | `404` |
| `account_not_found` | `404` |
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
