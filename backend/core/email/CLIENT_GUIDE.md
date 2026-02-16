# Email Client Implementation Guide

This document describes the architecture, flows, and conventions shared by every `EmailClient` implementation in MailManager. Use it as a reference when reading existing clients (Gmail, Outlook) and as a step-by-step template when adding new providers.

---

## 1. Abstract Contract (`email_client.py`)

Every provider client extends `EmailClient` and implements five abstract methods:

| Method | Purpose | Returns |
|---|---|---|
| `authenticate(app_credentials)` | Interactive OAuth flow (opens browser). | `dict[str, Any]` — wrapped tokens (always). |
| `authenticate_silent(app_credentials, user_tokens)` | Non-interactive token refresh. | `dict[str, Any] \| None` — wrapped tokens if refreshed, `None` if still valid. |
| `fetch_unread_emails()` | Retrieve unread messages from the provider. | `List[EmailMessage]` |
| `send_email(subject, body, recipients)` | Send a plain-text email. | `None` |
| `get_account_label()` | Return the unique label for this account. | `str` |

`EmailMessage` is a provider-agnostic dataclass defined in the same module.

---

## 2. Constructor Pattern

```python
def __init__(self, account_label: str = "<provider>") -> None:
    self._account_label = account_label
    self._<api_client_state> = None  # e.g. self.service (Gmail) or self._access_token (Outlook)
```

- The constructor receives **only** `account_label`.
- Provider credentials (client_id, client_secret, etc.) come from `app_credentials` at authentication time, **not** from the constructor.
- Internal API client state starts as `None` and is initialized during authentication.

---

## 3. Common Private Helpers

All clients implement these four helpers with identical signatures and logic:

### `_unwrap_app_credentials(app_credentials) -> dict`
Shallow-copies the dict and unwraps any `SecretStr` value for `client_secret`.

### `_unwrap_user_tokens(user_tokens) -> dict`
Shallow-copies the dict and unwraps `SecretStr` values for `access_token` and `refresh_token`.

### `_wrap_account_tokens(token_data) -> dict`
Shallow-copies the dict and wraps `access_token` and `refresh_token` as `SecretStr`.

### `_parse_expiry(value) -> datetime | None`
Converts a value (ISO string, Unix timestamp, or `datetime`) into a naive UTC `datetime`. Returns `None` for unparseable or missing values. Handles `"Z"` suffix, timezone-aware datetimes, and numeric timestamps.

These helpers keep SecretStr handling consistent and isolated from business logic.

---

## 4. Authentication Flows

### 4.1 Interactive — `authenticate(app_credentials)`

Called by `EmailManager.connect_account` through the service layer when a user connects an account for the first time.

**Flow:**
1. `_unwrap_app_credentials(app_credentials)` — get raw credentials.
2. Validate required fields (client_id, client_secret, provider-specific fields).
3. Start OAuth flow (browser-based consent).
4. Exchange authorization code for tokens.
5. Initialize internal API client state.
6. Build a `token_record` dict with `access_token`, `refresh_token`, `expiry`, `scopes`.
7. Return `_wrap_account_tokens(token_record)`.

**Provider specifics:**
- **Gmail**: Uses `InstalledAppFlow.from_client_config` + `run_local_server`. The Google library handles PKCE and the callback server.
- **Outlook**: Manual PKCE flow with a local `ThreadingHTTPServer` to capture the callback, then a POST to the Microsoft token endpoint.

### 4.2 Silent — `authenticate_silent(app_credentials, user_tokens)`

Called automatically before every fetch/send operation via `EmailManager.authenticate_all_silent`.

**Flow:**
1. `_unwrap_app_credentials(app_credentials)` and `_unwrap_user_tokens(user_tokens)`.
2. Validate `access_token` is present (`EmailMissingTokenError` if not).
3. Parse expiry with `_parse_expiry`.
4. **If not expired**: set internal client state, return `None` (no persistence needed).
5. **If expired without refresh_token**: raise `EmailMissingRefreshTokenError`.
6. **If expired with refresh_token**: call the provider's token refresh endpoint.
7. Update internal client state with the new access token.
8. Build `token_record` and return `_wrap_account_tokens(token_record)`.

**Key difference — refresh token rotation:**
- **Gmail**: The refresh token stays the same after refresh.
- **Outlook**: Microsoft may return a **new** refresh token on every refresh. Always persist the newest one.

The service layer persists returned tokens via `save_account_tokens` whenever `authenticate_silent` returns a non-`None` result.

---

## 5. Email Operations

### 5.1 `fetch_unread_emails(max_total=200, page_size=50)`

**Flow:**
1. Check internal client state is initialized (`EmailNotAuthenticatedError` if not).
2. Query the provider API for unread messages with pagination.
3. Enforce `max_total` limit across pages.
4. Normalize each raw message into an `EmailMessage`:
   - `message_id` — provider's unique ID.
   - `thread_id` — conversation/thread grouping (optional).
   - `subject`, `sender`, `recipients`, `body` — extracted/normalized from provider format.
   - `sent_at` — parsed to `datetime` with timezone.
   - `is_unread` — always `True` (we're fetching unread).
   - `provider` — `"gmail"`, `"outlook"`, etc.

**Provider specifics:**
- **Gmail**: Fetches message IDs first, then each message in `raw` format. Parses RFC822 headers manually.
- **Outlook**: Uses Microsoft Graph `GET /me/messages?$filter=isRead eq false` with `$select` and `@odata.nextLink` pagination. Fields come pre-parsed in JSON.

### 5.2 `send_email(subject, body, recipients)`

**Flow:**
1. Check internal client state (`EmailNotAuthenticatedError`).
2. Validate recipients list is not empty (`EmailRecipientsMissingError`).
3. Build provider-specific payload and send.

**Provider specifics:**
- **Gmail**: Constructs a MIME message, base64url-encodes it, sends via `users().messages().send`.
- **Outlook**: Builds a JSON payload with `message.body.contentType = "Text"`, sends via `POST /me/sendMail`.

---

## 6. Error Handling

All clients use errors from `core/email/errors.py`. The service layer catches `CoreError` subclasses and translates them to `ApiError` subclasses via `translate_core_error()`.

| Situation | Error to raise |
|---|---|
| No app credentials | `EmailMissingAppCredentialsError` |
| No access token stored | `EmailMissingTokenError` |
| Token expired, no refresh token | `EmailMissingRefreshTokenError` |
| Token refresh HTTP failure | `EmailRefreshFailedError` |
| Client not authenticated before API call | `EmailNotAuthenticatedError` |
| No recipients for send | `EmailRecipientsMissingError` |
| External API call fails (network, timeout, invalid response) | `EmailExternalAPIError` |

**Error Handling Pattern:**
- All external API calls (Google API, Microsoft Graph, HTTP requests) must be wrapped in `try/except Exception` blocks.
- Raise `EmailExternalAPIError` with a descriptive message including the **specific operation** and **client name** (e.g., `"Gmail failed to fetch message list: {exc}"`).
- The service layer catches `CoreError` subclasses and translates them to `ApiError` subclasses via `translate_core_error()`.
- `EmailExternalAPIError` is mapped to `ExternalAPIError` (HTTP 502 Bad Gateway), signaling a third-party API failure.

---

## 7. Adding a New Provider — Checklist

### Core layer
- [ ] Create `backend/core/email/<provider>_client.py` implementing all 5 abstract methods.
- [ ] Add the four common helpers (`_unwrap_app_credentials`, `_unwrap_user_tokens`, `_wrap_account_tokens`, `_parse_expiry`).
- [ ] Add any provider-specific helpers (API request wrappers, scope resolution, etc.).
- [ ] Define a `<PROVIDER>_SCOPES` constant if the provider uses OAuth scopes.
- [ ] Import and add a branch for the new provider in `EmailManager._build_client`.

### Database layer (`backend/api/database/token_store.py`)
- [ ] Add the new env var name to `_ENV_CREDENTIALS` dict.
- [ ] Update the `provider` CHECK constraint in `schema.sql` to include the new provider.

### No changes needed in
- `services_helpers.py` — already provider-aware via the `provider` parameter.
- `accounts_service.py` / `emails_service.py` — already pass `provider` to all load/save functions.
- `api/errors/` — reuse existing error classes.

### Documentation
- [ ] Update `CLAUDE.md`: project overview, env vars section, and any relevant notes.
- [ ] Update this guide if the new provider introduces patterns not yet covered.

---

## 8. Reference Comparison

| Aspect | Gmail | Outlook |
|---|---|---|
| API client | `googleapiclient` service object (`self.service`) | Raw `urllib.request` with bearer token (`self._access_token`) |
| OAuth library | `google-auth-oauthlib` (`InstalledAppFlow`) | Manual PKCE + local HTTP server |
| Token refresh | `google.oauth2.credentials.Credentials.refresh()` | POST to Microsoft token endpoint |
| Refresh token rotation | No (same token reused) | Yes (may change on every refresh) |
| Unread query | `users().messages().list(q="is:unread")` + per-message `get(format="raw")` | `GET /me/messages?$filter=isRead eq false` (JSON response) |
| Send mechanism | MIME → base64url → `users().messages().send` | JSON payload → `POST /me/sendMail` |
| Credentials env var | `MIA_GMAIL_CREDENTIALS_PATH` | `MIA_OUTLOOK_CREDENTIALS_PATH` |
| Credentials JSON format | Nested under `"installed"` or `"web"` key | Flat dict |
| Token filename | `gmail_token_{label}.json` | `outlook_token_{label}.json` |
