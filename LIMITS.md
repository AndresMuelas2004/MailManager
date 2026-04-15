# Limits & Quotas

Operational limits enforced by MailManager. These values are hardcoded in the backend and apply equally to all users and providers unless noted otherwise.

---

## Email

| Limit | Value | Details |
|-------|-------|---------|
| Emails per sync (bootstrap) | **500 per account** | On first sync (bootstrap), the app fetches at most the 500 most recent emails from the provider. Older emails are not retrievable. |
| Incremental sync event threshold | **100 events** (Gmail only) | If a Gmail incremental sync detects more than 100 combined events (new, deleted, label changes), it aborts and falls back to a full bootstrap sync. |
| Email content | **Fetched on demand** | Full HTML/text body is not fetched during sync. It is retrieved from the provider when the user opens an email, then cached locally. |
| Email deletion | **Local only — sole exception to the Provider-First Rule** | Deleting emails is the **only operation that intentionally breaks the Provider-First Rule**. No provider API call is ever made (uniform no-op across Gmail and Outlook). The email is **not removed from the user's real mailbox** at the provider — it is only soft-deleted from the application's local database (`box` set to `DELETED`). Once deleted, the email will **never appear again in MailManager**, unless the user goes into the original client (Gmail/Outlook) and restores it manually from there; in that case, the next sync will pick it up again and it will reappear in the app. |
| Attachments | **Not supported** | Sending emails and creating/updating drafts do not accept attachments. The `EmailClient` send/draft APIs only accept text fields (subject, body, recipients). No attachment handling exists in the core, providers (Gmail/Outlook), API, or frontend. |

## Drafts

| Limit | Value | Details |
|-------|-------|---------|
| Drafts per sync | **100 per account** | Each draft sync fetches at most the 100 most recent drafts from the provider. Older drafts are not retrievable. |
| Draft body | **Included in sync** | Unlike emails, the full body of each draft is fetched during sync and stored locally. No on-demand fetch needed. |

## Sync behavior

| Behavior | Details |
|----------|---------|
| Draft sync strategy | **Replace** — each sync upserts fetched drafts and deletes local rows that no longer exist at the provider. |
| Email sync strategy | **Bootstrap + incremental** — first sync fetches up to 500 emails; subsequent syncs use delta/history to apply changes. |
| No historical recovery | There is no mechanism to fetch emails or drafts older than the cap. If a user needs older items, the cap must be increased in the code. |

## Internal / infrastructure

| Limit | Value | Details |
|-------|-------|---------|
| Gmail batch size | **100 per batch request** | Gmail API batch operations (metadata fetch, trash, read status) process 100 items per HTTP batch call. |
| Gmail parallel workers | **5** (configurable via `GMAIL_BATCH_MAX_WORKERS` env var) | Number of concurrent threads for Gmail batch operations. |
| Batch retry attempts | **5 total** (1 initial + 4 retries) | Both Gmail batch operations and Outlook draft page fetches retry up to 4 times on transient errors. |
| Outlook draft page size | **100** | Outlook fetches drafts in pages of 100 items. |
