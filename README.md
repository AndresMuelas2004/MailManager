# MailManager

MailManager is a multi-account email management platform with a FastAPI backend and a React frontend.
It lets you group Gmail and Outlook accounts under mailbox entities, connect them with OAuth 2.0, fetch inbox messages across providers, and send emails from any connected account.

## Highlights

- Multi-mailbox model to isolate contexts (work, personal, clients).
- Multi-provider support: Gmail and Outlook are implemented.
- Unified inbox per mailbox across all connected accounts.
- Send email from a specific account in a mailbox.
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

Example (PowerShell):

```powershell
$env:DATABASE_URL = "postgresql://user:pass@localhost:5432/mailmanager"
$env:MIA_GMAIL_CREDENTIALS_PATH = "C:\\secrets\\gmail_oauth.json"
$env:MIA_OUTLOOK_CREDENTIALS_PATH = "C:\\secrets\\outlook_oauth.json"
$env:TOKEN_ENCRYPTION_KEY = "<FERNET_KEY>"
$env:TOKEN_ENCRYPTION_KEY_ID = "v1"
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
# (Optional) Place OAuth credentials in credentials/
mkdir credentials
# cp /path/to/gmail_oauth.json credentials/gmail_credentials.json
# cp /path/to/outlook_oauth.json credentials/outlook_credentials.json

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
| `TOKEN_ENCRYPTION_KEY` | Yes (recommended) | Fernet key for encrypted account tokens in DB. |
| `TOKEN_ENCRYPTION_KEY_ID` | No | Identifier for active encryption key. Default: `v1`. |
| `TOKEN_PLAINTEXT_FALLBACK_ENABLED` | No | Enables temporary legacy plaintext token reads. Default: `true`. |
| `MIA_GMAIL_CREDENTIALS_PATH` | Yes | Path to Gmail OAuth credentials JSON file. |
| `MIA_OUTLOOK_CREDENTIALS_PATH` | Yes | Path to Outlook app credentials JSON file. |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID for OIDC authentication. |
| `AUTH_SESSION_LIFETIME_DAYS` | No | Session duration in days. Default: `7`. |
| `AUTH_COOKIE_SECURE` | No | HTTPS-only session cookies. Default: `false`. |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated CORS origins. Default: `http://localhost:5173`. |
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

Auth:

- `POST /auth/google`
- `GET /auth/me`
- `POST /auth/logout`
- `DELETE /auth/me`

Detailed endpoint contracts: `backend/api/API_ENDPOINTS.md`

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

Primary API error codes include:

- `api_error`
- `mailbox_not_found`
- `account_not_found`
- `user_not_found`
- `account_misconfigured`
- `recipients_missing`
- `unauthorized`
- `account_connect_auth_error`
- `forbidden`
- `account_not_connected`
- `app_credentials_invalid`
- `app_credentials_missing`
- `env_var_error`
- `credential_file_error`
- `database_connection_error`
- `database_query_error`
- `database_migration_error`
- `token_decryption_error`
- `token_integrity_error`
- `email_fetch_error`
- `email_send_error`
- `external_api_error`

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

- `backend/tests/unit/UNIT_TESTS.md`
- `backend/tests/integration/INTEGRATION_TESTS.md`
- `backend/tests/e2e/E2E_TESTS.md`

## Additional Documentation

- API endpoints: `backend/api/API_ENDPOINTS.md`
- API layer guide: `backend/api/API_GUIDE.md`
- Auth layer guide: `backend/auth/AUTH_GUIDE.md`
- Database package: `backend/database/DATABASE.md`
- Email client implementation guide: `backend/core/email/CLIENT_GUIDE.md`
- Frontend setup: `frontend/README.md`
- Agent guidance: `CLAUDE.md`
