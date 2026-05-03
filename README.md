# MailManager

MailManager is a multi-account email management platform with a FastAPI backend and a React frontend.
It lets you group Gmail and Outlook accounts under mailbox entities, connect them with OAuth 2.0, fetch inbox messages across providers, and send emails from any connected account.

## Highlights

- Multi-mailbox model to isolate contexts (work, personal, clients).
- Multi-provider support: Gmail and Outlook are implemented.
- Unified inbox per mailbox across all connected accounts.
- Send email from a specific account in a mailbox.
- Draft creation that mirrors the draft at the provider (Gmail and Outlook).
- Draft update that replaces draft content at the provider (PATCH, Provider-First).
- Draft deletion at the provider with local cleanup (Provider-First Rule).
- Draft synchronization pulls the most recent drafts from every connected account into the local database (capped at 100 per account).
- Batch read/unread status management across accounts.
- Trash management: move emails to trash, permanently delete, or restore.
- Spam operations: move to spam and restore from spam with cross-provider support.
- OAuth 2.0 interactive connect flow plus silent re-authentication.
- PostgreSQL persistence for mailboxes, accounts, and tokens.
- Strict layered architecture with centralized API error mapping.

## Architecture

Request flow:

```text
Routers (api/routers)
  -> Routers helpers (api/routers/routers_helpers.py)
  -> Services (api/services)
    -> Auth (auth/)
    -> Database (database/)
    -> Core (core/email)
      -> EmailManager
        -> GmailClient / OutlookClient
```

Layer contracts:

- `Routers`: HTTP interface only. No business logic.
- `Services`: orchestration, validation, and error translation.
- `Auth`: framework-agnostic authentication (Google OIDC, session management).
- `Database`: PostgreSQL persistence and token storage (independent layer).
- `Core`: provider-specific email behavior and client orchestration.

## Repository Structure

```text
MailManager/
|-- backend/
|   |-- api/
|   |   |-- routers/
|   |   |-- services/
|   |   |-- schemas/
|   |   `-- errors/
|   |-- auth/
|   |-- database/
|   |-- core/
|   |   `-- email/
|   |-- tests/
|   |   |-- unit/
|   |   |-- integration/
|   |   |-- e2e/
|   |   `-- shared/
|   `-- main.py
|-- frontend/
|   |-- src/
|   `-- package.json
|-- requirements.txt
`-- README.md
```

## Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL
- Gmail OAuth app credentials JSON (Google Cloud)
- Outlook app credentials JSON (Azure app registration)
- Docker and Docker Compose (optional, for containerized deployment)

## Getting Started

### 1. Clone and install backend dependencies

```bash
git clone <your-repo-url>
cd MailManager

python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

MailManager reads environment variables from the OS environment. The backend also supports a `backend/.env` file via `python-dotenv` (`override=False`, so OS-level variables take precedence). See `backend/.env.example` for a template.

Required:

- `DATABASE_URL`
- `MIA_GMAIL_CREDENTIALS_PATH`
- `MIA_OUTLOOK_CREDENTIALS_PATH`
- `TOKEN_ENCRYPTION_KEY`
- `GOOGLE_CLIENT_ID`

Example (PowerShell):

```powershell
$env:DATABASE_URL = "postgresql://user:pass@localhost:5432/mailmanager"
$env:MIA_GMAIL_CREDENTIALS_PATH = "C:\\secrets\\gmail_oauth.json"
$env:MIA_OUTLOOK_CREDENTIALS_PATH = "C:\\secrets\\outlook_oauth.json"
$env:TOKEN_ENCRYPTION_KEY = "<FERNET_KEY>"
$env:GOOGLE_CLIENT_ID = "<YOUR_GOOGLE_CLIENT_ID>"
```

Generate a Fernet key (one-time):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Apply database migrations

```bash
python -m alembic -c backend/database/alembic.ini upgrade head
```

For existing databases initialized before Alembic:

```bash
python -m alembic -c backend/database/alembic.ini stamp 0001_initial_schema
python -m alembic -c backend/database/alembic.ini upgrade head
```

### 4. Run backend

```bash
cd backend
python main.py
```

Backend URL: `http://localhost:8000`

### 5. Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://localhost:5173`

### Docker (alternative)

Instead of manual setup, run everything with Docker Compose:

```bash
# Configure the credentials volume in docker-compose.yml
# The volume mount path is developer-specific — edit the 'volumes' entry
# to point to your local OAuth credentials directory.

docker compose up --build
```

This starts PostgreSQL and the backend (port 8000). The frontend service is currently commented out in `docker-compose.yml`. Run Alembic migrations before exposing the API.

```bash
docker compose down      # stop all services
docker compose down -v   # stop and delete database volume
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL DSN used by connection pool and Alembic migrations. |
| `DB_POOL_MIN_CONN` | No | Minimum pooled DB connections. Default: `1`. |
| `DB_POOL_MAX_CONN` | No | Maximum pooled DB connections. Default: `10`. |
| `DB_CONNECT_TIMEOUT_SECONDS` | No | Connection timeout for PostgreSQL. Default: `10`. |
| `DB_APPLICATION_NAME` | No | PostgreSQL `application_name`. Default: `mailmanager-api`. |
| `DB_AUTO_MIGRATE` | No | If `true`, API startup runs `alembic upgrade head`. Default: `false`. |
| `DB_ALEMBIC_INI_PATH` | No | Custom Alembic config path. |
| `TOKEN_ENCRYPTION_KEY` | Yes | Fernet key for encrypted account tokens in DB. |
| `TOKEN_ENCRYPTION_KEY_ID` | No | Identifier for active encryption key. Default: `v1`. |
| `TOKEN_PLAINTEXT_FALLBACK_ENABLED` | No | Enables temporary legacy plaintext token reads. Default: `true`. |
| `MIA_GMAIL_CREDENTIALS_PATH` | Yes | Path to Gmail OAuth credentials JSON file. |
| `MIA_OUTLOOK_CREDENTIALS_PATH` | Yes | Path to Outlook app credentials JSON file. |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID for OIDC authentication. |
| `GMAIL_BATCH_MAX_WORKERS` | No | Max parallel workers for Gmail batch operations. Default: `5`. |
| `AUTH_SESSION_LIFETIME_DAYS` | No | Session duration in days. Default: `7`. |
| `AUTH_COOKIE_SECURE` | No | HTTPS-only session cookies. Default: `false`. |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated CORS origins. Default: `http://localhost:5173`. |

### Frontend environment variables

The following variable is consumed only by the Vite dev server / frontend bundle. It is **not** read by the backend; configure it in `frontend/.env`.

| Variable | Required | Description |
|---|---|---|
| `VITE_API_BASE_URL` | No | Frontend override for the backend URL. Defaults to `http://localhost:8000`. |

Outlook credential file keys: `client_id`, `client_secret`, `tenant`, `redirect_uri`, `scopes`.

## API Summary

Health:

- `GET /health`

Mailboxes:

- `POST /mailboxes`
- `GET /mailboxes`
- `GET /mailboxes/{mailbox_id}`
- `DELETE /mailboxes/{mailbox_id}`

Accounts:

- `GET /mailboxes/{mailbox_id}/accounts`
- `POST /mailboxes/{mailbox_id}/accounts`
- `GET /mailboxes/{mailbox_id}/accounts/{account_id}`
- `PATCH /mailboxes/{mailbox_id}/accounts/{account_id}`
- `DELETE /mailboxes/{mailbox_id}/accounts/{account_id}`
- `POST /mailboxes/{mailbox_id}/accounts/{account_id}/connect`

Emails:

- `POST /mailboxes/{mailbox_id}/emails/sync-metadata`
- `POST /mailboxes/{mailbox_id}/emails/send`
- `PATCH /mailboxes/{mailbox_id}/emails/read-status`
- `POST /mailboxes/{mailbox_id}/emails/trash`
- `POST /mailboxes/{mailbox_id}/emails/move-to-trash`
- `POST /mailboxes/{mailbox_id}/emails/spam`
- `POST /mailboxes/{mailbox_id}/emails/restore-from-spam`
- `GET /mailboxes/{mailbox_id}/emails` — Required query param: `box=ALL_MAIL|SENT|SPAM|TRASH`. Optional: `account_id`, `q` (free-text search, 2-200 chars, accent/case-insensitive substring across subject + sender), `limit` (default 200, max 500), `offset` (default 0).
- `GET /mailboxes/{mailbox_id}/emails/{provider_message_id}/content` — Required query param: `account_id`.

Drafts:

- `POST /mailboxes/{mailbox_id}/accounts/{account_id}/drafts` — Create a draft at the provider and persist it locally (Provider-First; Outlook uses `Prefer: IdType="ImmutableId"`).
- `PATCH /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{provider_draft_id}` — Replace an existing draft's content at the provider (full-field replacement) and persist the new values locally. Provider-First with a pre-check: the draft must exist in the local DB (404 `draft_not_found` otherwise) before any provider call. Gmail uses `users().drafts().update()`; Outlook uses `PATCH /me/messages/{id}` with `Prefer: IdType="ImmutableId"` repeated on every call. `created_at` is preserved; `updated_at` is refreshed.
- `DELETE /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{draft_id}` — Delete a draft at the provider and remove the local row (Provider-First). Returns `{"status": "deleted"}`.
- `POST /mailboxes/{mailbox_id}/drafts/sync` — Fetch the most recent drafts from the provider(s) into the local database (full replace per account, capped at 100 drafts per account most recent by date). Optional query param `account_id`: when provided, syncs only that account; when omitted, syncs every account in the mailbox. Gmail uses parallel batched `drafts.get` calls (workers configurable via `GMAIL_BATCH_MAX_WORKERS`, default 5); Outlook uses `$top=100` + `$orderby=lastModifiedDateTime desc` paginated fetch with per-page retries.
- `POST /mailboxes/{mailbox_id}/accounts/{account_id}/drafts/{provider_draft_id}/send` — Send an existing draft at the provider and remove it from local storage. Provider-First with 3-attempt retry in the client layer. On success: deletes the local `drafts` row and persists the sent email metadata to `email_metadata` (both best-effort). Gmail returns a new `message_id`; Outlook keeps the same ID (ImmutableId).
- `GET /mailboxes/{mailbox_id}/drafts` — List drafts for the mailbox (DB-only, no provider calls). Optional query param `account_id`: when provided, returns drafts of that account; when omitted, returns the unified view across all accounts in the mailbox. Ordered by `created_at DESC`.

Auth:

- `POST /auth/google`
- `GET /auth/me`
- `POST /auth/logout`
- `DELETE /auth/me`

Detailed endpoint contracts: `backend/api/api_guide.md`

## Error Response Format

All API errors follow this schema:

```json
{
  "error": {
    "code": "account_not_found",
    "message": "Account '...' not found.",
    "detail": {}
  }
}
```

Each API error code maps to a fixed HTTP status. The list below shows every code with its status. The full reference (with usage notes per class) lives in `backend/api/api_guide.md` under "Service-Layer Error Classes".

- `api_error` — 500 (default for any unmapped class)
- `mailbox_not_found` — 404
- `account_not_found` — 404
- `email_not_found` — 404
- `draft_not_found` — 404
- `user_not_found` — 404
- `account_misconfigured` — 400
- `recipients_missing` — 400
- `unauthorized` — 401
- `account_connect_auth_error` — 401
- `forbidden` — 403
- `account_not_connected` — 409
- `email_not_in_trash` — 409
- `app_credentials_invalid` — 500
- `app_credentials_missing` — 500
- `env_var_error` — 500
- `credential_file_error` — 500
- `database_connection_error` — 503
- `database_query_error` — 503
- `database_migration_error` — 500
- `token_decryption_error` — 500
- `token_encryption_error` — 500
- `token_integrity_error` — 500
- `trash_operation_error` — 500
- `email_list_error` — 500
- `draft_list_error` — 500
- `mailbox_operation_error` — 500
- `account_operation_error` — 500
- `session_operation_error` — 500
- `user_operation_error` — 500
- `email_fetch_error` — 502
- `email_send_error` — 502
- `external_api_error` — 502
- `read_status_update_error` — 502
- `move_to_trash_error` — 502
- `spam_move_error` — 502
- `spam_restore_error` — 502
- `email_content_fetch_error` — 502
- `draft_creation_error` — 502
- `draft_update_error` — 502
- `draft_delete_error` — 502
- `draft_sync_error` — 502

## Testing

```bash
# All tests
python -m pytest backend/tests

# Unit tests
python -m pytest backend/tests/unit -v

# Integration tests (requires DATABASE_URL)
python -m pytest backend/tests/integration -v

# E2E tests (requires DATABASE_URL and provider credentials)
python -m pytest backend/tests/e2e -v -s
```

Testing docs:

- `backend/tests/unit/unit_guide.md`
- `backend/tests/integration/integration_guide.md`
- `backend/tests/e2e/e2e_guide.md`

## Additional Documentation

### Layer guides (project-specific)

- API layer guide: `backend/api/api_guide.md`
- Auth layer guide: `backend/auth/auth_guide.md`
- Database guide: `backend/database/database_guide.md`
- Core (email) guide: `backend/core/core_guide.md`

### General rules (architecture standards)

- `backend/api/CLAUDE.md`
- `backend/auth/CLAUDE.md`
- `backend/database/CLAUDE.md`
- `backend/core/CLAUDE.md`
- `backend/tests/unit/CLAUDE.md`
- `backend/tests/integration/CLAUDE.md`
- `backend/tests/e2e/CLAUDE.md`

### Other

- Frontend setup: `frontend/README.md`
- Agent guidance: `CLAUDE.md`
