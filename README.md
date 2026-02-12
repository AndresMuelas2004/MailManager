# MailManager

A multi-account email management platform with a FastAPI backend and a React frontend. MailManager lets users group multiple email accounts (Gmail, Outlook) under unified mailboxes, fetch unread messages across providers in a single call, and send emails from any connected account.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Authentication Flows](#authentication-flows)
- [Testing](#testing)
- [Extensibility](#extensibility)
- [License](#license)

## Features

- **Multi-mailbox management** &mdash; Create isolated mailboxes that group email accounts by context (work, personal, clients).
- **Multi-provider support** &mdash; Gmail and Outlook are fully implemented. The architecture is designed for easy addition of new providers.
- **Unified inbox** &mdash; Fetch unread emails from every connected account in a single API call.
- **Send from any account** &mdash; Compose and send emails through any connected provider account.
- **OAuth 2.0 with PKCE** &mdash; Secure interactive and silent authentication flows. Tokens are refreshed automatically without user interaction.
- **Token lifecycle management** &mdash; Per-account token storage with automatic refresh, rotation handling (Outlook), and secure persistence.
- **Strict layered architecture** &mdash; Clean separation between HTTP surface, business logic, persistence, and provider-specific code.
- **Atomic storage operations** &mdash; JSON-based persistence with thread-safe writes and atomic file replacement to prevent data corruption.
- **Comprehensive error handling** &mdash; Two-tier error hierarchy (Core and API) with centralized mapping and structured error responses.

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
│  Storage        │  Core (core/email/)            │
│  (api/storage/) │  EmailManager + EmailClients   │
│  Persistence    │  Provider-specific logic       │
│  abstraction    ├────────────────────────────────┤
│                 │  GmailClient │ OutlookClient   │
└─────────────────┴────────────────────────────────┘
```

**Layer rules enforced throughout the codebase:**

| Layer | Responsibility | Constraints |
|-------|---------------|-------------|
| **Routers** | HTTP endpoints, request parsing | No business logic; delegate to services |
| **Services** | Orchestration, validation, error mapping | Only layer that talks to both Storage and Core |
| **Storage** | Data persistence (JSON files) | No imports from Core |
| **Core** | Provider logic, multi-account orchestration | No imports from API layer |

## Tech Stack

### Backend

| Technology | Purpose |
|-----------|---------|
| **Python 3.12+** | Runtime |
| **FastAPI** | Web framework |
| **Uvicorn** | ASGI server |
| **Pydantic v2** | Schema validation, secrets handling |
| **google-api-python-client** | Gmail API integration |
| **google-auth-oauthlib** | Gmail OAuth 2.0 |
| **urllib + manual PKCE** | Outlook OAuth 2.0 (Microsoft Graph) |
| **pytest** | Testing framework |

### Frontend

| Technology | Purpose |
|-----------|---------|
| **React 19** | UI library |
| **TypeScript 5.9** | Type safety |
| **Vite 7** | Build tool and dev server |
| **Tailwind CSS 4** | Utility-first styling |
| **React Router 7** | Client-side routing |

## Project Structure

```
MailManager/
├── backend/
│   ├── main.py                          # Uvicorn entrypoint
│   ├── api/
│   │   ├── app.py                       # FastAPI app factory, CORS, router registration
│   │   ├── routers/
│   │   │   ├── health.py                # GET /health
│   │   │   ├── mailboxes.py             # CRUD /mailboxes
│   │   │   ├── accounts.py              # CRUD /mailboxes/{id}/accounts + /connect
│   │   │   └── emails.py                # GET unread, POST send
│   │   ├── services/
│   │   │   ├── mailboxes_service.py     # Mailbox business logic
│   │   │   ├── accounts_service.py      # Account lifecycle + OAuth orchestration
│   │   │   ├── emails_service.py        # Fetch/send orchestration
│   │   │   └── services_helpers.py      # Manager factory, error translation
│   │   ├── schemas/                     # Pydantic request/response models
│   │   ├── errors/
│   │   │   ├── exceptions.py            # ApiError hierarchy
│   │   │   └── handlers.py              # Exception → HTTP status mapping
│   │   └── storage/
│   │       ├── base.py                  # MailboxStore / AccountStore interfaces
│   │       ├── json_store.py            # JSON file persistence (atomic writes)
│   │       └── token_store.py           # Per-account token I/O
│   ├── core/
│   │   └── email/
│   │       ├── email_client.py          # Abstract EmailClient interface
│   │       ├── email_manager.py         # Multi-account orchestrator
│   │       ├── gmail_client.py          # Gmail provider implementation
│   │       ├── outlook_client.py        # Outlook provider implementation
│   │       ├── errors.py                # CoreError hierarchy
│   │       └── CLIENT_GUIDE.md          # Guide for adding new providers
│   └── tests/
│       ├── unit/                        # Unit tests with FakeEmailClient
│       └── integration/                 # API tests with TestClient + isolated storage
├── frontend/
│   ├── src/
│   │   ├── api/                         # HTTP client, endpoints, DTOs
│   │   ├── app/                         # Router, layout, providers
│   │   ├── pages/                       # Page components
│   │   ├── features/                    # Feature modules (accounts, emails)
│   │   └── components/                  # Shared UI components
│   ├── package.json
│   └── vite.config.ts
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- A Google Cloud project with the Gmail API enabled and an OAuth 2.0 Desktop client
- An Azure AD app registration with Microsoft Graph Mail permissions (for Outlook)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/<your-username>/MailManager.git
cd MailManager

# Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (see section below)

# Start the API server
cd backend
python main.py
# Server runs at http://localhost:8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
# App runs at http://localhost:5173
```

### Environment Variables

Create a `.env` file or export these variables before starting the backend:

| Variable | Description |
|----------|-------------|
| `MIA_GMAIL_CREDENTIALS_PATH` | Path to the Gmail OAuth client credentials JSON (downloaded from Google Cloud Console) |
| `MIA_OUTLOOK_CREDENTIALS_PATH` | Path to the Outlook app credentials JSON (from Azure AD or manually created) |
| `MIA_TOKEN_PATH` | Directory where per-account token files are stored |

**Gmail credentials** &mdash; Download the OAuth 2.0 client JSON from Google Cloud Console (Desktop application type). The file should contain an `installed` or `web` block with `client_id`, `client_secret`, and token URIs.

**Outlook credentials** &mdash; Create a JSON file with the following structure:

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
| `POST` | `/mailboxes/{mailbox_id}/accounts` | Add a new account (Gmail or Outlook) |
| `PATCH` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | Update account metadata |
| `DELETE` | `/mailboxes/{mailbox_id}/accounts/{account_id}` | Remove an account |
| `POST` | `/mailboxes/{mailbox_id}/accounts/{account_id}/connect` | Start OAuth flow for the account |

### Emails

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/mailboxes/{mailbox_id}/emails/unread` | Fetch unread emails from all connected accounts |
| `POST` | `/mailboxes/{mailbox_id}/emails/send` | Send an email from a specific account |

### Error Response Format

All errors follow a consistent structure:

```json
{
  "error": {
    "code": "account_not_found",
    "message": "Account not found.",
    "detail": {
      "account_id": "acc_123",
      "core_code": "email_account_not_found"
    }
  }
}
```

## Authentication Flows

### Interactive Connection

When a user calls `POST /connect`, the backend:

1. Loads OAuth app credentials from the environment.
2. Starts a local HTTP server on an auto-assigned port.
3. Opens the provider's consent page in the user's browser.
4. Receives the authorization code via redirect callback.
5. Exchanges the code for access and refresh tokens.
6. Persists tokens to disk and returns a success response.

Gmail uses `google-auth-oauthlib` with `InstalledAppFlow`. Outlook implements the full OAuth 2.0 Authorization Code flow with PKCE manually.

### Silent Token Refresh

Before every fetch or send operation, the service authenticates silently:

1. Loads stored tokens from disk.
2. Checks token expiry.
3. If valid, proceeds immediately.
4. If expired, uses the refresh token to obtain new credentials.
5. Persists updated tokens (Outlook may rotate refresh tokens on every refresh).

No user interaction is required for silent refresh.

## Testing

```bash
# Run all tests
python -m pytest backend/tests

# Unit tests only
python -m pytest backend/tests/unit

# Integration tests only
python -m pytest backend/tests/integration

# Run a specific test file
python -m pytest backend/tests/unit/core/email/test_email_manager.py

# Run tests by name pattern
python -m pytest backend/tests -k "test_fetch"
```

- **Unit tests** use `FakeEmailClient` to test core logic in isolation.
- **Integration tests** use FastAPI's `TestClient` with monkeypatched providers and isolated temporary storage to avoid touching production data.

## Extensibility

### Adding a New Email Provider

The codebase is designed for straightforward provider addition. See [`backend/core/email/CLIENT_GUIDE.md`](backend/core/email/CLIENT_GUIDE.md) for a step-by-step guide. In summary:

1. Create a new class implementing the `EmailClient` abstract interface (5 methods).
2. Add a branch in `EmailManager._build_client` for the new provider.
3. Register the provider's environment variable in `token_store`.
4. Add token path resolution logic.

### Database Migration

The storage layer uses `MailboxStore` and `AccountStore` abstract interfaces. JSON file persistence can be replaced with any database by implementing these contracts without changing the service or core layers.
