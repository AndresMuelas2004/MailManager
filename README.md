# MailManager

A multi-account email management platform with a FastAPI backend and a React frontend. MailManager lets users group multiple email accounts (Gmail, Outlook) under unified mailboxes, fetch unread messages across providers in a single call, and send emails from any connected account.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Database](#database)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Extensibility](#extensibility)

## Features

- **Multi-mailbox management** &mdash; Create isolated mailboxes that group email accounts by context (work, personal, clients).
- **Multi-provider support** &mdash; Gmail and Outlook fully implemented. The architecture supports adding new providers with minimal effort.
- **Unified inbox** &mdash; Fetch unread emails from every connected account in a single API call.
- **Send from any account** &mdash; Compose and send emails through any connected provider account.
- **OAuth 2.0 authentication** &mdash; Interactive and silent flows with PKCE, automatic token refresh, and rotation handling (Outlook).
- **PostgreSQL persistence** &mdash; Mailboxes, accounts, and tokens stored with cascading deletes and connection pooling.
- **Layered architecture** &mdash; Strict separation between HTTP surface, business logic, persistence, and provider-specific code, backed by a two-tier error hierarchy with centralized mapping.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   Frontend                       │
│          React + Vite + TypeScript               │
└────────────────────┬─────────────────────────────┘
                     │ HTTP/JSON
┌────────────────────▼─────────────────────────────┐
│  Routers (api/routers/)                          │
│  Thin HTTP surface — zero business logic         │
├──────────────────────────────────────────────────┤
│  Services (api/services/)                        │
│  Orchestration, validation, error translation    │
├─────────────────┬────────────────────────────────┤
│  Database       │  Core (core/email/)            │
│ (api/database/) │  EmailManager + EmailClients   │
│  PostgreSQL     │  Provider-specific logic       │
│  persistence    ├────────────────────────────────┤
│                 │  GmailClient │ OutlookClient   │
└─────────────────┴────────────────────────────────┘
```

| Layer | Responsibility | Constraints |
|-------|---------------|-------------|
| **Routers** | HTTP endpoints, request parsing | No business logic; delegate to services |
| **Services** | Orchestration, validation, error mapping | Only layer that talks to both Database and Core |
| **Database** | PostgreSQL persistence | No imports from Core |
| **Core** | Provider logic, multi-account orchestration | No imports from API layer |

## Tech Stack

### Backend

| Technology | Purpose |
|-----------|---------|
| Python 3.12+ | Runtime |
| FastAPI | Web framework |
| Uvicorn | ASGI server |
| PostgreSQL | Relational database |
| psycopg2 | PostgreSQL driver with connection pooling |
| Pydantic v2 | Schema validation and secrets handling |
| google-api-python-client | Gmail API integration |
| google-auth-oauthlib | Gmail OAuth 2.0 |
| pytest | Testing framework |

### Frontend

| Technology | Purpose |
|-----------|---------|
| React 19 | UI library |
| TypeScript | Type safety |
| Vite | Build tool and dev server |
| Tailwind CSS 4 | Utility-first styling |
| React Router 7 | Client-side routing |

## Project Structure

```
MailManager/
├── backend/
│   ├── main.py                     # Uvicorn entrypoint
│   ├── api/
│   │   ├── app.py                  # FastAPI app factory, lifespan, CORS
│   │   ├── routers/                # health, mailboxes, accounts, emails
│   │   ├── services/               # Business logic and orchestration
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── errors/                 # ApiError hierarchy and HTTP mapping
│   │   └── database/               # PostgreSQL persistence layer
│   ├── core/
│   │   └── email/                  # Provider clients, EmailManager, errors
│   └── tests/
│       ├── unit/                   # Isolated tests with FakeEmailClient
│       ├── integration/            # API tests with TestClient + isolated DB
│       └── e2e/                    # Full-flow tests against real providers
├── frontend/
│   ├── src/
│   │   ├── api/                    # HTTP client, typed endpoints, DTOs
│   │   ├── app/                    # Router, layout, providers
│   │   ├── pages/                  # Page components
│   │   ├── features/               # Feature-based modules
│   │   └── components/             # Shared UI components
│   └── package.json
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL (local or remote instance)
- A Google Cloud project with the Gmail API enabled and an OAuth 2.0 client
- An Azure AD app registration with Microsoft Graph Mail permissions

### Backend

```bash
git clone https://github.com/AndresMuelas2004/MailApp.git
cd MailApp

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Configure environment variables (see next section)

cd backend
python main.py
# → http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## Environment Variables

Set these before starting the backend:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://user:pass@localhost:5432/mailmanager`) |
| `MIA_GMAIL_CREDENTIALS_PATH` | Path to the Gmail OAuth client credentials JSON |
| `MIA_OUTLOOK_CREDENTIALS_PATH` | Path to the Outlook app credentials JSON |

**Gmail** &mdash; Download the OAuth 2.0 client JSON from Google Cloud Console (Desktop application type). The file must contain an `installed` or `web` block with `client_id`, `client_secret`, and token URIs.

**Outlook** &mdash; Create a JSON file with this structure:

```json
{
  "client_id": "your-azure-client-id",
  "client_secret": "your-azure-client-secret",
  "tenant": "common",
  "redirect_uri": "http://localhost:8080/callback",
  "scopes": [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "offline_access"
  ]
}
```

## Database

MailManager uses PostgreSQL for all persistent data. The schema is defined in [`backend/api/database/schema.sql`](backend/api/database/schema.sql) and applied automatically on startup via `init_db()`.

| Table | Purpose |
|-------|---------|
| `mailboxes` | Mailbox records with display name |
| `accounts` | Email accounts linked to a mailbox, with provider type and config |
| `tokens` | OAuth tokens per account (access, refresh, expiry, scopes) |

All DDL is idempotent (`CREATE TABLE IF NOT EXISTS`). Foreign keys use `ON DELETE CASCADE`, so deleting a mailbox automatically removes its accounts and tokens.

See [`backend/api/database/DATABASE.md`](backend/api/database/DATABASE.md) for implementation details.

## API Reference

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server health check |

### Mailboxes

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/mailboxes` | List all mailboxes |
| `POST` | `/mailboxes` | Create a new mailbox |
| `GET` | `/mailboxes/{mailbox_id}` | Get a single mailbox |
| `DELETE` | `/mailboxes/{mailbox_id}` | Delete a mailbox and its accounts |

### Accounts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/mailboxes/{mailbox_id}/accounts` | List accounts in a mailbox |
| `POST` | `/mailboxes/{mailbox_id}/accounts` | Add an account |
| `PATCH` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | Update account metadata |
| `DELETE` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | Remove an account |
| `POST` | `/mailboxes/{mailbox_id}/accounts/{account_id}/connect` | Start OAuth flow |

### Emails

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/mailboxes/{mailbox_id}/emails/unread` | Fetch unread emails from all connected accounts |
| `POST` | `/mailboxes/{mailbox_id}/emails/send` | Send an email from a specific account |

### Error Responses

All errors follow a consistent structure:

```json
{
  "error": {
    "code": "account_not_found",
    "message": "Account not found.",
    "detail": { "account_id": "..." }
  }
}
```

| Code | Status | Trigger |
|------|--------|---------|
| `mailbox_not_found` | 404 | Mailbox does not exist |
| `account_not_found` | 404 | Account does not exist |
| `account_misconfigured` | 400 | Invalid provider or missing credentials |
| `account_connect_auth_error` | 401 | Provider authentication failed during `/connect` |
| `provider_auth_error` | 401 | OAuth authentication failure |
| `account_not_connected` | 409 | Account has not completed OAuth |
| `email_fetch_error` | 502 | Provider failure during fetch |
| `email_send_error` | 502 | Provider failure during send |
| `external_api_error` | 502 | Generic external API failure |
| `storage_error` | 503 | Database failure |
| `env_var_error` | 500 | Missing environment variable |

## Testing

```bash
# All tests
python -m pytest backend/tests

# Unit tests only
python -m pytest backend/tests/unit

# Integration tests (requires DATABASE_URL)
python -m pytest backend/tests/integration

# E2E tests (requires DATABASE_URL + provider credentials + browser)
python -m pytest backend/tests/e2e -v -s

# Single file or pattern
python -m pytest backend/tests/unit/core/email/test_email_manager.py
python -m pytest backend/tests -k "test_fetch"
```

| Layer | Scope | Dependencies |
|-------|-------|-------------|
| **Unit** | Core email logic in isolation | None &mdash; uses `FakeEmailClient` |
| **Integration** | Full request flow through the API | PostgreSQL (each test in a rolled-back transaction) |
| **E2E** | Complete flow against real providers | PostgreSQL + provider credentials + browser |

See [`INTEGRATION_TESTS.md`](backend/tests/integration/INTEGRATION_TESTS.md) and [`E2E_TESTS.md`](backend/tests/e2e/E2E_TESTS.md) for details.

## Extensibility

Adding a new email provider is straightforward. See [`CLIENT_GUIDE.md`](backend/core/email/CLIENT_GUIDE.md) for the full guide. In short:

1. Implement the `EmailClient` abstract interface.
2. Register the provider in `EmailManager._build_client`.
3. Add the credentials env var in `token_store._ENV_CREDENTIALS`.
4. Update the `provider` CHECK constraint in `schema.sql`.
