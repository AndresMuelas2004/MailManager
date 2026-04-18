# Repository Guide — Project-Specific (maintained by Claude)

This file contains details specific to MailManager. Update it when the project changes (new providers, new endpoints, architectural shifts). Do not modify any `CLAUDE.md` file.

## Project Overview

**MailManager** is a multi-account email management application.

- **Backend**: FastAPI (Python).
- **Frontend**: React + Vite + TypeScript + Tailwind.
- **Email providers**: Gmail and Outlook (both fully implemented).
- **Authentication**: Google OIDC.
- **Database**: PostgreSQL with Alembic migrations.

## Request Flow

```
Routers (FastAPI)
  → routers_helpers.py (require_session → user_id)
  → Services (api/services/)
    → Auth (auth/)            — Google OIDC verification
    → Database (database/)    — PostgreSQL persistence
    → Core (core/)
      → EmailManager (core/email/email_manager.py)
        → GmailClient, OutlookClient
```

Note: the `GET /mailboxes/{mailbox_id}/emails` listing endpoint reads only from the local database (Services → Database, no provider API calls).
Note: the `GET /mailboxes/{mailbox_id}/emails/{id}/content` endpoint uses a cache-aside pattern — first verifies the email exists in `email_metadata` (404 `email_not_found` otherwise), then checks the `email_content` table, and on cache miss fetches from the provider API, runs the HTML through the dedicated rendering pipeline (`api.services.email_html_pipeline.prepare_email_html`, re-exported from `services_helpers` as `sanitize_email_html`), persists in DB, then returns. The pipeline is composed of seven pure functions in order: (1) `_normalize_charset_meta` strips any bogus `<meta charset="us-ascii">` / `<meta http-equiv="Content-Type" content="…charset=windows-1252">` and, **only when the input has a `<head>`**, injects a canonical `<meta charset="utf-8">` right after it so downstream parsers (lxml in premailer, html5lib in bleach) treat the Python `str` as UTF-8 instead of honouring a wrong declared charset (which would otherwise produce mojibake on accented characters); when there is no `<head>` the canonical meta is **not** injected — a Python `str` is already Unicode-decoded and prepending `<meta>` before any `<!DOCTYPE>` would push lxml into quirks mode; (2) `_unwrap_mso_conditionals` keeps the payload of downlevel-revealed comments (`<!--[if !mso]><!-- -->…<!--<![endif]-->` and the compact `<!--[if !mso]><!-->…<!--<![endif]-->` short form) and **discards** downlevel-hidden blocks entirely (`<!--[if mso | IE]>…<![endif]-->`, `<!--[if gte mso 9]><xml>…</xml><![endif]-->`, etc.) — those are Outlook-only layouts that must stay invisible in our iframe viewer (a non-Outlook client), and unwrapping them caused visible duplication whenever templates shipped both an MSO-only and a non-MSO variant of the same hero/logo (Medusa Festival #20, Santander Open Academy #73); when discarding hidden blocks leaves an empty body (>200 bytes discarded **and** <50 visible chars left), `_unwrap_mso_conditionals` logs `logger.warning("MSO-only email detected: discarded N bytes …")` so legacy MSO-only newsletters become observable instead of disappearing silently — no automatic fallback is applied; (3) `_sanitize_style_blocks` parses every `<style>` block with cssutils, filters properties against `_ALLOWED_CSS_PROPERTIES`, drops unsafe property values (`expression(…)`, `javascript:`, `vbscript:`), keeps only the at-rules in `_ALLOWED_CSS_AT_RULES` (`@media`, `@supports`, `@font-face`) and discards the rest (`@import`, `@keyframes`, `@namespace`, `@charset`) — each rule is wrapped in its own `try/except` so a single unparseable sibling rule (`calc(100% - )`, vendor-specific syntax, etc.) cannot wipe the whole block and take down preheader-hiding rules like `.preheader{display:none}` with it (bugs #5, #22, #51, #73, #84, #143, #315); the at-rule decision uses a `{rule_type: at_rule_name}` map consulted against `_ALLOWED_CSS_AT_RULES` (single source of truth — change the constant, not the function); this is also what lets responsive newsletter templates (eDreams, Netcapital, HubSpot-style) render their desktop layout inside the iframe because the `@media (min-width:…)` override now survives; (4) `_inline_css_via_premailer` runs premailer with `keep_style_tags=True` so inlinable rules go onto element `style=""` attributes for compatibility *and* the sanitised `<style>` tag survives for media queries / pseudo-classes; (5a) `_flatten_document_wrappers` strips head-only constructs that must not leak into the body fragment — `<!DOCTYPE>`, `<title>…</title>` (otherwise bleach would keep the inner text and render the subject as visible body content — Pencil.dev #36), `<meta>`, `<link>`, `<base>`, stray `<xml>` islands (MSO leftovers), plus the `<html>`/`<head>`/`<body>` wrapper tags themselves — and **preserves the outer `<body>`'s `style`/`bgcolor`** by promoting them into a synthetic wrapping `<div style="…">` so the iframe's own `body{background:#fff}` reset does not cover HubSpot/Netcapital's lavender frame (bugs #8, #9); the wrapper's style attribute is escaped with `html.escape(quote=True)` so a `<body>` style mixing single and double quotes (e.g. `font-family:"Helvetica Neue",'Arial'`) cannot break the wrapper attribute (CSSSanitizer cleans the CSS later); (5b) `_mirror_geometry_to_attributes` mirrors `width`/`height` values from inline styles back onto HTML attributes on `<img>`/`<td>`/`<th>`/`<table>` so signature tables and inline logos keep their intended dimensions even if the inline style is later stripped — the defensive guard counts `img`/`td`/`th`/`table` elements (via `_CRITICAL_ELEMENT_RE`) before and after the lxml reparse, abandoning the step when the post-reparse count drops below half the input (lxml's cosmetic byte deltas — entity escaping, attribute requoting — no longer trigger false positives the way the previous 50 %-byte guard did); (6) `_strip_script_blocks` removes `<script>` blocks with their content (but *not* `<style>` anymore — its content was sanitised in step 3); (7) `_clean_with_bleach` applies the final tag/attribute/protocol allowlist with `"style"` in `_ALLOWED_TAGS` and `CSSSanitizer(allowed_css_properties=_ALLOWED_CSS_PROPERTIES, allowed_svg_properties=frozenset())` filtering inline `style=""` attributes. Allowed protocols: `http`, `https`, `mailto`, `cid`, `data`. During the provider fetch, inline images referenced as `<img src="cid:…">`, `background="cid:…"`, or `style="background-image:url(cid:…)"` (the latter produced by premailer when it inlines `<style>` rules) are resolved to `data:image/<type>;base64,…` URLs by traversing Gmail's `multipart/related` tree (with an extra `attachments().get()` call when the part carries only an `attachmentId`) or by requesting Outlook's `GET /me/messages/{id}/attachments?$select=contentType,contentBytes,contentId,isInline` when `hasAttachments` is true; both providers apply the shared helper `core.email.helpers.inline_cid_images` with per-image soft fallback. Gmail's body decoder (`_extract_body_from_payload`) delegates base64 + charset decoding to the shared helper `core.email.helpers.decode_mime_body`, which implements a UTF-8-first strategy with validated fallback: try strict UTF-8 first (any well-formed UTF-8 body decodes correctly), on `UnicodeDecodeError` fall back to the charset declared in the part's `Content-Type` header, and as last resort decode UTF-8 with `errors="replace"`. This prevents the mojibake that happened when senders mislabelled UTF-8 bodies as `iso-8859-1` or `windows-1252` — Outlook (Graph API) does charset negotiation server-side so it is unaffected. Content rows are tied to metadata via a composite foreign key `email_content.(provider_message_id, account_id) → email_metadata.(provider_message_id, account_id) ON DELETE CASCADE`, so metadata deletes and account deletes transitively cascade into content (migration 0013). Migration 0014 truncates `email_content` once to invalidate any HTML cached before the CSS-inlining + `cid:` pipeline was introduced; migration 0015 does the same after `data:` URLs were added to the sanitizer's allowed protocols; migration 0016 does the same after MSO unwrap + `url(cid:…)` resolution + Gmail charset detection; migration 0017 does the same after charset meta normalisation + geometry attribute restoration; migration 0018 does the same after the pipeline refactor (extraction into `email_html_pipeline.py`, `<style>` preservation with sanitised `@media`/`@supports`/`@font-face` rules, and Gmail's UTF-8-first body decode); migration 0019 does the same after head-only tag scrub + `<body>` background promotion + MSO-hidden discard + resilient per-rule `<style>` sanitisation + geometry reparse guard.
Note: the `POST /mailboxes/{mailbox_id}/accounts/{account_id}/drafts` endpoint follows the Provider-First Rule — the draft is created at the provider first (Gmail `drafts.create` or Outlook `POST /me/messages` with `Prefer: IdType="ImmutableId"`), and only on success persisted to the local `drafts` table.
Note: the `PATCH /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{provider_draft_id}` endpoint also follows the Provider-First Rule with a pre-check — `ensure_mailbox_access` → account lookup → `draft_store.get` (404 `draft_not_found` if the draft is not in the local DB, without wasting a provider round trip) → silent auth → provider update (Gmail `users().drafts().update()` or Outlook `PATCH /me/messages/{id}` with `Prefer: IdType="ImmutableId"` repeated because the stored ID is an Immutable ID) → only on success, `draft_store.update` persists the new recipients/subject/body and refreshes `updated_at`. The local `created_at` is preserved across updates.
Note: the `GET /mailboxes/{mailbox_id}/drafts` listing endpoint reads only from the local database (Services → Database, no provider API calls). Query param `account_id` is optional: when provided, returns drafts of that account; when omitted, returns the unified view across all accounts in the mailbox.
Note: the `POST /mailboxes/{mailbox_id}/drafts/sync` endpoint fetches drafts from the provider(s) and replaces the local rows for each synced account atomically (UPSERT + delete-missing). Query param `account_id` is optional: when provided, syncs only that account; when omitted, syncs every account in the mailbox. Both providers cap the fetch at `_DRAFTS_MAX_TOTAL = 100` drafts per account (most recent). Gmail uses the existing parallel-batch-of-100 skeleton (5 workers × 4 retries); Outlook paginates with `$top=100` + `$orderby=lastModifiedDateTime desc` + 4 retries per page.
Note: the `DELETE /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{draft_id}` endpoint follows the Provider-First Rule — the draft is deleted at the provider first (Gmail `users().drafts().delete()` or Outlook `DELETE /me/messages/{id}` with `Prefer: IdType="ImmutableId"`), and only on success the local `drafts` row is removed. Response: `{"status": "deleted"}`.
Note: the `POST /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{provider_draft_id}/send` endpoint follows the Provider-First Rule — the draft is sent at the provider first (Gmail `drafts().send()` or Outlook `POST /me/messages/{id}/send` with `Prefer: IdType="ImmutableId"`), with 3 total attempts on transient failures. Only on success are DB changes applied: the `drafts` row is deleted and the sent email metadata is persisted to `email_metadata` — both as best-effort (failures are logged but do not fail the response). Gmail returns a new `message_id` for the sent email; Outlook keeps the same ID thanks to ImmutableId.

## Key Identifiers

- `mailbox_id` — groups accounts under a mailbox.
- `account_id` — unique per account record.
- `account_label` — `"{mailbox_id}__{account_id}"`, used by `EmailManager` for client identification.
- `display_label` — required on account creation (`min_length=1`, `NOT NULL`); the service layer falls back to `"{provider}:{account_id}"` when rendering responses for legacy records.
- `user_id` — UUID identifying an authenticated user (from `users` table).
- `owner_user_id` — FK on `mailboxes` linking to the owning user (NOT NULL, CASCADE on user delete).
- `email_address` — the email address of the connected account, fetched best-effort from the provider during `connect_account`. Stored as plain text (not encrypted) in the `accounts` table. May be `NULL` if the fetch failed.
- `provider_draft_id` — the draft identifier returned by the provider (Gmail `drafts.create` or Outlook `POST /me/messages` with `Prefer: IdType="ImmutableId"`). Together with `account_id`, forms the composite PK of the `drafts` table.

## Testing

- **Unit tests** (`backend/tests/unit/`) — use `FakeEmailClient` from `tests/shared/email_fakes.py`. Cover service logic, auth settings, error translation.
- **Integration tests** (`backend/tests/integration/`) — use `FastAPI TestClient`, monkeypatch `build_manager_for_accounts` with fakes, isolate via `isolated_db` (transaction rollback). `require_session` overridden to return a fixed test user_id.
- Both test layers share `FakeEmailClient`, `build_metadata`, and database fakes (`FakeCursor`, `FakeConnection`) via `tests/shared/`.
- **E2E tests** (`backend/tests/e2e/`) — automated like unit and integration tests. They test all endpoints except interactive OAuth flows (`POST /auth/google`, `POST .../connect`) and `DELETE /auth/me` (cannot create a test user without the interactive login). Real third-party APIs and real DB persistence. Pre-configured test accounts are already inserted in the database with valid tokens and must never be deleted — E2E tests can be run without additional setup.

## Frontend

Stack: React + Vite + TypeScript + Tailwind + lucide-react (icons). Structure:

- `src/api/` — HTTP client (`client/`), typed endpoints (`endpoints/`), DTOs (`types/`).
- `src/app/` — Layout, providers (AuthProvider, AuthContext), routing (RequireAuth guard).
- `src/features/auth/` — Login page with Google Identity Services integration (implemented).
- `src/features/` — Other features scaffolded (mailboxes, accounts, emails, drafts, users).
- `src/components/` — Shared components (scaffolded).
- `src/types/` — TypeScript declarations (GIS types).
- `src/lib/` — Shared constants and utilities.
- `src/styles/` — Global CSS.

External dependency: Google Identity Services script loaded via `<script>` tag in `index.html`. Requires `VITE_GOOGLE_CLIENT_ID` env var matching the backend's `GOOGLE_CLIENT_ID`.

## Docker

`docker-compose.yml` orchestrates `db` (PostgreSQL 16) and `backend` (port 8000). The frontend service is currently commented out. Backend waits for database via `service_healthy`. OAuth credentials mounted as a read-only volume; the host path is developer-specific (configured in docker-compose.yml).

## Extensibility

- **New email provider**: follow the Core layer's `*_guide.md` (referenced from `backend/core/CLAUDE.md`).
- **New identity provider**: follow the Auth layer's `*_guide.md` (referenced from `backend/auth/CLAUDE.md`).
- **New API endpoint**: follow the API layer's `*_guide.md` (referenced from `backend/api/CLAUDE.md`).
Adding a new email provider or identity provider impacts multiple layers (Core, Database, API, Auth, Tests). Before starting, review the Extension / Checklist section in each affected layer's `*_guide.md` to understand the full scope of changes required.

## Provider-First Rule

For any operation that modifies email state both at the provider and in our database, always call the provider API first. Only update the DB for messages where the provider call succeeded. Never persist a state change locally if the provider rejected or failed the operation. This ensures our DB always reflects the real state of the user's mailbox at the provider.
**Current exceptions:** Both providers (Gmail and Outlook) use a uniform no-op approach for `delete_messages` -- the provider API is not called and deletion is performed only in the local database. See `core_guide.md` (Trash Management Operations > `delete_messages`) for the detailed rationale.

## Environment

PostgreSQL is installed natively on this machine, not via Docker. Do not attempt to use Docker for database operations.

## Document Maintenance

Update this file when: architecture layers change, new providers are introduced, commands change, or key identifiers are added. Do not modify any `CLAUDE.md` file.
