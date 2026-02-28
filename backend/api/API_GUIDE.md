# API Layer Guide

This guide documents the `backend/api/` package — the HTTP surface, service orchestration, error handling, and schema contracts for MailManager.
Use it when adding endpoints, modifying service logic, or debugging error translation.

## Scope

This guide covers:

- Package structure and directory layout
- Layer boundaries (routers vs services vs errors vs schemas)
- Application setup (`app.py` factory, lifespan, CORS)
- Router rules and endpoint catalogue
- Service conventions and shared helpers
- Error hierarchy with HTTP status mapping
- Error handling — capture technique and translation patterns
- Schema contracts
- Adding a new endpoint checklist

## 1. Package Structure

```
api/
├── app.py                          # Application factory, lifespan, CORS, router registration
│
├── errors/                         # API error hierarchy + FastAPI exception handlers
│   ├── __init__.py
│   ├── exceptions.py               #   ApiError base + all subclasses
│   └── handlers.py                 #   register_error_handlers(), _STATUS_MAP
│
├── routers/                        # Thin HTTP surface — one service call per endpoint
│   ├── routers_helpers.py          #   require_session (shared Depends callable)
│   ├── health_routers.py           #   GET /health
│   ├── auth_routers.py             #   POST /auth/google, GET /auth/me, POST /auth/logout, DELETE /auth/me
│   ├── mailboxes_routers.py        #   CRUD for /mailboxes
│   ├── accounts_routers.py         #   CRUD + /connect for /mailboxes/{id}/accounts
│   └── emails_routers.py           #   GET /unread, POST /send for /mailboxes/{id}/emails
│
├── schemas/                        # Pydantic request/response models
│   ├── auth.py                     #   GoogleLoginRequest, UserOut, AuthResponse
│   ├── mailbox.py                  #   MailboxCreate, MailboxOut
│   ├── account.py                  #   AccountCreate, AccountUpdate, AccountOut, AccountConnectResponse
│   ├── email.py                    #   EmailOut, EmailSendRequest
│   └── error.py                    #   ErrorDetail, ErrorResponse
│
└── services/                       # Orchestration, validation, error mapping
    ├── services_helpers.py         #   Translation maps, context managers, shared utilities
    ├── auth_service.py             #   Google OIDC login, session management
    ├── mailboxes_service.py        #   Mailbox CRUD
    ├── accounts_service.py         #   Account CRUD + interactive connect
    └── emails_service.py           #   Fetch unread, send email
```

## 2. Layer Boundaries

- **Routers** (`routers/`) — thin HTTP surface. Zero business logic. Each endpoint declares Pydantic schemas and contains a single service call.
- **Services** (`services/`) — orchestration, validation, and error mapping. The only layer that raises `ApiError` subclasses. Services call into `core/`, `database/`, and `auth/` — never the reverse.
- **Errors** (`errors/`) — defines the `ApiError` hierarchy and the FastAPI exception handlers that translate them to HTTP responses.
- **Schemas** (`schemas/`) — Pydantic `BaseModel` subclasses defining the API contract.

Hard rule: routers never contain business logic, services never expose HTTP details (except receiving `Response` for cookie management).

## 3. Application Setup (`app.py`)

`create_app()` is the application factory:

1. Loads `backend/.env` via `python-dotenv` (`override=False` — OS/Docker env vars take precedence).
2. Creates the `FastAPI` instance with a lifespan context manager.
3. Adds CORS middleware from `CORS_ALLOWED_ORIGINS` (default `http://localhost:5173`).
4. Registers error handlers via `register_error_handlers(app)`.
5. Includes all routers in order: health, auth, mailboxes, accounts, emails.

### Lifespan

- **Startup**: runs optional auto-migrations (`run_startup_migrations_if_enabled`), then warms the connection pool (`warmup_connection`).
- **Shutdown**: closes the connection pool (`close_pool`).

## 4. Router Rules

Every router follows the same pattern:

1. **One service call per endpoint.** The route function calls a single service function and returns its result.
2. **`Depends(require_session)`** on all protected endpoints — returns `user_id`.
3. **No business logic.** No conditionals, no error handling, no data transformation.
4. **Pydantic schemas** declare the request/response contract.

### Endpoints that skip `require_session`

| Endpoint | Reason |
|---|---|
| `GET /health` | Unauthenticated health check |
| `POST /auth/google` | Creates the session — cannot require a prior one |
| `POST /auth/logout` | Must work even with expired sessions |

### Endpoint catalogue

| Method | Path | Auth | Service function | Response |
|---|---|---|---|---|
| `GET` | `/health` | No | — | `{"status": "ok"}` |
| `POST` | `/auth/google` | No | `auth_service.google_login` | `AuthResponse` |
| `GET` | `/auth/me` | Yes | `auth_service.get_current_user` | `UserOut` |
| `POST` | `/auth/logout` | No | `auth_service.logout` | `{"status": "logged_out"}` |
| `DELETE` | `/auth/me` | Yes | `auth_service.delete_account` | `{"status": "account_deleted"}` |
| `POST` | `/mailboxes` | Yes | `mailboxes_service.create_mailbox` | `MailboxOut` |
| `GET` | `/mailboxes` | Yes | `mailboxes_service.list_mailboxes` | `list[MailboxOut]` |
| `GET` | `/mailboxes/{mailbox_id}` | Yes | `mailboxes_service.get_mailbox` | `MailboxOut` |
| `DELETE` | `/mailboxes/{mailbox_id}` | Yes | `mailboxes_service.delete_mailbox` | `{"status": "deleted"}` |
| `GET` | `/mailboxes/{mid}/accounts` | Yes | `accounts_service.list_accounts` | `list[AccountOut]` |
| `POST` | `/mailboxes/{mid}/accounts` | Yes | `accounts_service.create_account` | `AccountOut` |
| `GET` | `/mailboxes/{mid}/accounts/{aid}` | Yes | `accounts_service.get_account` | `AccountOut` |
| `PATCH` | `/mailboxes/{mid}/accounts/{aid}` | Yes | `accounts_service.update_account` | `AccountOut` |
| `DELETE` | `/mailboxes/{mid}/accounts/{aid}` | Yes | `accounts_service.delete_account` | `{"status": "deleted"}` |
| `POST` | `/mailboxes/{mid}/accounts/{aid}/connect` | Yes | `accounts_service.connect_account` | `AccountConnectResponse` |
| `GET` | `/mailboxes/{mid}/emails/unread` | Yes | `emails_service.get_unread` | `list[EmailOut]` |
| `POST` | `/mailboxes/{mid}/emails/send` | Yes | `emails_service.send_email` | `{"status": "sent"}` |

### Extensibility — new identity providers

Currently the only identity endpoint is `POST /auth/google`, which is hardcoded to Google OIDC. When a new identity provider is added (e.g. GitHub OAuth, Microsoft Entra ID), the approach is **one endpoint per provider** — not a single generic endpoint with a `provider` parameter:

- Add `POST /auth/<provider>` in `auth_routers.py` (thin route, single service call).
- Add `<provider>_login` in `auth_service.py` (catch `AuthError`, translate via `translate_auth_error`).
- Add request/response schemas in `api/schemas/auth.py`.

The existing `AuthTokenError` subclasses are provider-agnostic and reusable. See `AUTH_GUIDE.md` § 9 for the full checklist covering the auth layer, service layer, router, tests, and docs.

## 5. Service Conventions

### Ownership check

For any action scoped to a mailbox, call `ensure_mailbox_access(mailbox_id, user_id)` first. It validates the mailbox exists and the authenticated user owns it, raising `MailboxNotFound` (404) or `Forbidden` (403).

### Building provider clients

Build via `build_manager_for_accounts(accounts)` — never instantiate `EmailClient` subclasses directly. This helper creates an `EmailManager` and registers all account records, translating `CoreError` and unexpected exceptions to `AccountMisconfigured`.

### Database calls

Wrap all database calls in `catch_database_errors(*, fallback, context)` — a context manager that catches `DatabaseError` (translated via `_DB_TO_API_MAP`) and unexpected exceptions (wrapped in `fallback`).

### Secret wrapping

Load credentials with `load_wrapped_app_credentials(provider)` / `load_wrapped_account_tokens(mailbox_id, account_id, provider)` (uses `pydantic.SecretStr`). Unwrap with `unwrap_secret()` before persisting.

### Cookie management

Services that manage session cookies receive the `fastapi.Response` object from the router. Cookie setting/clearing happens in the service layer, not in routers.

## 6. Error Hierarchy

All API errors are defined in `api/errors/exceptions.py`. Every subclass has a stable `code` string and maps to an HTTP status via `_STATUS_MAP` in `handlers.py`.

```
ApiError                            # code="api_error"                    → 500
├── MailboxNotFound                 # code="mailbox_not_found"            → 404
├── AccountNotFound                 # code="account_not_found"            → 404
├── UserNotFound                    # code="user_not_found"               → 404
├── AccountMisconfigured            # code="account_misconfigured"        → 400
├── RecipientsMissing               # code="recipients_missing"           → 400
├── Unauthorized                    # code="unauthorized"                 → 401
├── AccountConnectAuthError         # code="account_connect_auth_error"   → 401
├── Forbidden                       # code="forbidden"                    → 403
├── AccountNotConnected             # code="account_not_connected"        → 409
├── AppCredentialsInvalid           # code="app_credentials_invalid"      → 500
├── AppCredentialsMissing           # code="app_credentials_missing"      → 500
├── EnvVarError                     # code="env_var_error"                → 500
├── CredentialFileError             # code="credential_file_error"        → 500
├── DatabaseConnectionError         # code="database_connection_error"    → 503
├── DatabaseQueryError              # code="database_query_error"         → 503
├── DatabaseMigrationError          # code="database_migration_error"     → 500
├── TokenDecryptionError            # code="token_decryption_error"       → 500
├── TokenIntegrityError             # code="token_integrity_error"        → 500
├── EmailFetchError                 # code="email_fetch_error"            → 502
├── EmailSendError                  # code="email_send_error"             → 502
└── ExternalAPIError                # code="external_api_error"           → 502
```

All responses use the `ErrorResponse` envelope:

```json
{
  "error": {
    "code": "account_not_found",
    "message": "Account 'abc' not found.",
    "detail": {}
  }
}
```

## 7. Error Handling — Capture Technique

This is the central pattern for error handling in the service layer. Every `try` block in services follows the same ordered structure.

### The pattern

```python
try:
    result = lower_layer_call(...)
except LayerError as exc:                   # 1. Typed layer error → translate
    raise translate_layer_error(exc, fallback=SpecificApiError) from exc
except Exception as exc:                    # 2. Unexpected error → specific ApiError
    raise SpecificApiError(
        f"Failed to ... ({type(exc).__name__}): {exc}"
    ) from exc
```

### Rules

1. **Catch the layer base class** (`CoreError`, `AuthError`, `DatabaseError`) — the translation function uses `isinstance` to find the most specific mapping.
2. **Always `from exc`** — preserve the cause chain.
3. **Fallback matches the context** — email fetch failures use `EmailFetchError`, connect failures use `AccountConnectAuthError`, account registration uses `AccountMisconfigured`, etc.
4. **Include `type(exc).__name__`** in unexpected-error messages for debuggability.
5. **Never let lower-layer exceptions escape** — every `try` block has an `except Exception` fallback.

### Translation functions and maps

Three parallel translation functions convert lower-layer errors to `ApiError` subclasses:

| Function | Map | Source layer |
|---|---|---|
| `translate_core_error(exc, fallback, context)` | `_CORE_TO_API_MAP` | `core/email/` |
| `translate_database_error(exc, fallback, context)` | `_DB_TO_API_MAP` | `database/` |
| `translate_auth_error(exc, fallback, context)` | `_AUTH_TO_API_MAP` | `auth/` |

Each map is a list of `(LayerErrorType, ApiErrorType)` tuples evaluated with `isinstance`, most specific first. The final entry is always `(LayerErrorBase, ApiError)` as a catch-all.

#### `_CORE_TO_API_MAP`

| Core exception | API exception | HTTP |
|---|---|---|
| `EmailAccountNotFoundError` | `AccountNotFound` | 404 |
| `EmailMissingTokenError` | `AccountNotConnected` | 409 |
| `EmailMissingRefreshTokenError` | `AccountNotConnected` | 409 |
| `EmailRefreshFailedError` | `AccountNotConnected` | 409 |
| `EmailNotAuthenticatedError` | `AccountNotConnected` | 409 |
| `EmailAuthError` | `AccountNotConnected` | 409 |
| `EmailInvalidExpiryError` | `AccountMisconfigured` | 400 |
| `EmailInvalidCredentialsDataError` | `AppCredentialsInvalid` | 500 |
| `EmailInvalidTokenDataError` | `AccountMisconfigured` | 400 |
| `EmailAccountRecordError` | `AccountMisconfigured` | 400 |
| `EmailProviderConfigError` | `AccountMisconfigured` | 400 |
| `EmailMissingAppCredentialsError` | `AppCredentialsMissing` | 500 |
| `EmailDuplicateAccountLabelError` | `AccountMisconfigured` | 400 |
| `EmailConfigError` | `AccountMisconfigured` | 400 |
| `EmailRecipientsMissingError` | `RecipientsMissing` | 400 |
| `EmailExternalAPIError` | `ExternalAPIError` | 502 |
| `CoreError` | `ApiError` | 500 |

#### `_DB_TO_API_MAP`

| Database exception | API exception | HTTP |
|---|---|---|
| `ConnectionPoolError` | `DatabaseConnectionError` | 503 |
| `QueryError` | `DatabaseQueryError` | 503 |
| `MigrationError` | `DatabaseMigrationError` | 500 |
| `SettingsError` | `EnvVarError` | 500 |
| `TokenDecryptError` | `TokenDecryptionError` | 500 |
| `TokenValidationError` | `TokenIntegrityError` | 500 |
| `CredentialReadError` | `CredentialFileError` | 500 |
| `UnknownProviderError` | `AccountMisconfigured` | 400 |
| `DatabaseError` | `ApiError` | 500 |

#### `_AUTH_TO_API_MAP`

| Auth exception | API exception | HTTP |
|---|---|---|
| `AuthSettingsError` | `EnvVarError` | 500 |
| `AuthTokenNetworkError` | `ExternalAPIError` | 502 |
| `AuthTokenInvalidError` | `Unauthorized` | 401 |
| `AuthTokenProviderError` | `Unauthorized` | 401 |
| `AuthTokenError` | `Unauthorized` | 401 |
| `AuthError` | `ApiError` | 500 |

### Context manager (`catch_database_errors`)

Database calls use a context manager instead of explicit `try`/`except`:

```python
with catch_database_errors(fallback=DatabaseQueryError, context={"mailbox_id": mid}):
    record = account_store.get(mailbox_id, account_id)
```

The context manager catches `DatabaseError` (translated via `_DB_TO_API_MAP`) and unexpected exceptions (wrapped in `fallback`). The default fallback is `ApiError`.

### Special patterns

- **`translate_connect_error`** — for the interactive `/connect` flow. Maps `EmailAuthError` to `AccountConnectAuthError` (401) instead of `AccountNotConnected` (409), because a connect-time auth failure means the user's credentials are wrong, not that they need to call `/connect` again.
- **`raise_on_silent_auth_errors`** — inspects the per-account error dict from `manager.authenticate_all_silent()`. Non-auth `CoreError`s are translated and raised immediately. Auth errors are accumulated and raised as a single `AccountNotConnected` (409).
- **Post-fetch error inspection** — after `fetch_all_unread_emails()`, the service checks `manager.get_last_errors()` for per-client failures and raises either `AccountNotConnected` (auth errors) or `EmailFetchError` (other errors).

### Global handlers (`handlers.py`)

Two FastAPI exception handlers form the final safety net:

1. **`handle_api_error`** — catches any `ApiError`, looks up the HTTP status from `_STATUS_MAP` (default 500), and returns the `ErrorResponse` envelope.
2. **`handle_unexpected_error`** — catches any `Exception` not already handled, logs the full traceback, and returns a generic 500 `ErrorResponse`. This should never fire if all service functions follow the capture technique.

## 8. Schema Contracts

### `auth.py`

| Schema | Fields | Used by |
|---|---|---|
| `GoogleLoginRequest` | `id_token: str` (min 1) | `POST /auth/google` request |
| `UserOut` | `user_id`, `email`, `name?`, `avatar_url?` | User response model |
| `AuthResponse` | `user: UserOut`, `message: str` | `POST /auth/google` response |

### `mailbox.py`

| Schema | Fields | Used by |
|---|---|---|
| `MailboxCreate` | `display_name: str` (1–120 chars) | `POST /mailboxes` request |
| `MailboxOut` | `mailbox_id`, `display_name?`, `owner_user_id`, `created_at` | Mailbox response model |

### `account.py`

| Schema | Fields | Used by |
|---|---|---|
| `AccountCreate` | `provider`, `display_label`, `config?` | `POST .../accounts` request |
| `AccountUpdate` | `display_label?`, `config?` | `PATCH .../accounts/{id}` request |
| `AccountOut` | `account_id`, `mailbox_id`, `provider`, `display_label`, `config` | Account response model |
| `AccountConnectResponse` | `connected`, `provider`, `account_id`, `account_label`, `message` | `POST .../connect` response |

### `email.py`

| Schema | Fields | Used by |
|---|---|---|
| `EmailOut` | `message_id`, `subject`, `sender`, `recipients`, `body`, `sent_at`, `is_unread`, `provider`, `thread_id?`, `raw_rfc822_b64url?` | Email response model |
| `EmailSendRequest` | `account_id`, `subject`, `body`, `recipients` (min 1) | `POST .../emails/send` request |

### `error.py`

| Schema | Fields | Used by |
|---|---|---|
| `ErrorDetail` | `code`, `message`, `detail` | Error envelope inner object |
| `ErrorResponse` | `error: ErrorDetail` | All error responses |

## 9. Router Helpers

### `require_session`

```python
def require_session(session_id: str | None = Cookie(default=None)) -> str:
```

A FastAPI `Depends` callable used by all protected endpoints. Reads the `session_id` cookie, delegates validation to `auth_service.validate_session()`, and returns `user_id`. Raises `Unauthorized` (401) on absent, invalid, or expired sessions.

Overridden in integration tests via `app.dependency_overrides[require_session]` to return a fixed test user_id.

## 10. Adding a New Endpoint Checklist

- [ ] **Schema** — add request/response models in `api/schemas/`.
- [ ] **Service** — add the service function in the appropriate `api/services/` module. Follow service conventions (§ 5): ownership check, `catch_database_errors`, translation of layer errors, `except Exception` fallback.
- [ ] **Router** — add the route in the appropriate `api/routers/` module. Single service call, `Depends(require_session)` unless unauthenticated.
- [ ] **Register** — include the router in `app.py` if it's a new router module.
- [ ] **Error mapping** — if new `ApiError` subclasses are needed, add them in `exceptions.py` and register their HTTP status in `_STATUS_MAP` (`handlers.py`).
- [ ] **Unit tests** — test the service function in isolation (monkeypatch lower layers).
- [ ] **Integration tests** — test the endpoint via `FastAPI TestClient`.
- [ ] **Docs** — update this guide if architectural patterns change.
