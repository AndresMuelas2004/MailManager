# API Endpoints Reference

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{"status": "ok"}`. No input required. |

---

## Mailboxes

Base path: `/mailboxes`

| Method | Path | In | Out | Description |
|--------|------|----|-----|-------------|
| `POST` | `/mailboxes` | `MailboxCreate` (name) | `MailboxOut` | Creates a new mailbox record. |
| `GET` | `/mailboxes` | — | `list[MailboxOut]` | Lists all mailboxes. |
| `GET` | `/mailboxes/{mailbox_id}` | path: `mailbox_id` | `MailboxOut` | Retrieves a single mailbox by ID. |
| `DELETE` | `/mailboxes/{mailbox_id}` | path: `mailbox_id` | `{"detail": "..."}` | Deletes the mailbox and all its accounts. |

---

## Accounts

Base path: `/mailboxes/{mailbox_id}/accounts`

| Method | Path | In | Out | Description |
|--------|------|----|-----|-------------|
| `GET` | `…/accounts` | path: `mailbox_id` | `list[AccountOut]` | Lists all accounts under the mailbox. |
| `POST` | `…/accounts` | path: `mailbox_id`, body: `AccountCreate` | `AccountOut` | Creates a new account for the mailbox. |
| `GET` | `…/accounts/{account_id}` | path: `mailbox_id`, `account_id` | `AccountOut` | Fetches a single account by ID. |
| `PATCH` | `…/accounts/{account_id}` | path: `mailbox_id`, `account_id`, body: `AccountUpdate` | `AccountOut` | Updates mutable fields of an account. |
| `DELETE` | `…/accounts/{account_id}` | path: `mailbox_id`, `account_id` | `{"detail": "..."}` | Deletes the account and invalidates the manager cache. |
| `POST` | `…/accounts/{account_id}/connect` | path: `mailbox_id`, `account_id` | `AccountConnectResponse` | Runs provider authentication to verify and connect the account. |

---

## Emails

Base path: `/mailboxes/{mailbox_id}/emails`

| Method | Path | In | Out | Description |
|--------|------|----|-----|-------------|
| `GET` | `…/emails/unread` | path: `mailbox_id` | `list[EmailOut]` | Fetches unread emails from all accounts in the mailbox. |
| `POST` | `…/emails/send` | path: `mailbox_id`, body: `EmailSendRequest` | `{"detail": "..."}` | Sends an email using a specific account under the mailbox. |
