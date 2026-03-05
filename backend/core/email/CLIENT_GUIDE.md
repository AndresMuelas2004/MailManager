# Email Client Implementation Guide

This guide documents the current contract and implementation patterns for provider clients in `backend/core/email`.
Use it when maintaining Gmail/Outlook clients or adding a new provider.

## Scope

This guide covers:

- `EmailClient` abstract interface
- `EmailManager` orchestration behavior
- Shared helpers for token and expiry handling
- Authentication flows (interactive and silent)
- Error conventions
- New provider checklist

## 1. Core Contract (`email_client.py`)

Every provider client must implement the `EmailClient` abstract methods:

| Method | Purpose | Return |
|---|---|---|
| `authenticate(app_credentials)` | Interactive account connection flow. | `dict[str, Any] \| None` |
| `authenticate_silent(app_credentials, user_tokens)` | Non-interactive auth and refresh path. | `dict[str, Any] \| None` |
| `fetch_email_metadata(sync_cursor, max_total)` | Fetch email metadata from provider. | `tuple[list[EmailMetadata], str]` |
| `send_email(subject, body, recipients)` | Send plain-text email. | `None` |
| `get_account_label()` | Stable account identifier in manager. | `str` |

`EmailMetadata` is the normalized provider-agnostic metadata dataclass used by the service layer for persistence.

## 2. Account Label Convention

The service layer builds labels as:

```text
{mailbox_id}__{account_id}
```

Requirements:

- Labels must be unique across clients registered in `EmailManager`.
- Duplicate labels raise `EmailDuplicateAccountLabelError`.

## 3. Shared Helpers (`helpers.py`)

Provider clients should use shared helpers instead of re-implementing token logic:

- `parse_expiry(value)`
- `unwrap_app_credentials(app_credentials)`
- `unwrap_user_tokens(user_tokens)`
- `wrap_account_tokens(token_data)`

These helpers standardize:

- `SecretStr` unwrapping/wrapping for sensitive fields
- Expiry parsing from datetime, timestamps, and ISO strings

## 4. EmailManager Responsibilities

`EmailManager` orchestrates all registered clients.

Main methods:

- `add_account_record(record)`
- `authenticate_all_silent(auth_payloads)`
- `connect_account(account_label, app_credentials)`
- `fetch_all_email_metadata(sync_cursors)`
- `send_email_from_account(account_label, ...)`
- `get_last_errors()`

Behavioral notes:

- Manager stores per-account errors in `_last_errors`.
- Silent auth can refresh tokens and return updated payloads per account label.
- `fetch_all_email_metadata()` accepts an optional `sync_cursors` dict keyed by account label. Each client receives its cursor (or `None` for bootstrap). Per-client errors are collected in `_last_errors` without aborting other clients.
- Missing target account label raises `EmailAccountNotFoundError`.

## 5. Authentication Flows

### 5.1 Interactive flow (`authenticate`)

Used by `POST /mailboxes/{mailbox_id}/accounts/{account_id}/connect`.

Expected flow:

1. Validate app credentials.
2. Execute provider interactive OAuth flow.
3. Obtain access token (and refresh token when provided).
4. Build token record with `access_token`, `refresh_token`, `expiry`, `scopes`.
5. Return wrapped tokens via `wrap_account_tokens(...)`.

Provider specifics:

- Gmail: `InstalledAppFlow.run_local_server(...)`.
- Outlook: manual PKCE flow with local callback HTTP server.

### 5.2 Silent flow (`authenticate_silent`)

Used before fetch/send operations.

Expected flow:

1. Validate app credentials and stored user tokens.
2. Parse token expiry.
3. If token is still valid, initialize client state and return `None`.
4. If expired and refresh token exists, refresh access token.
5. Return wrapped updated tokens only when refreshed.

Provider-specific token refresh behavior:

- Gmail refresh token is commonly stable.
- Outlook may rotate refresh tokens. Always persist returned refresh token.

## 6. Email Operations

### 6.1 `fetch_email_metadata`

Signature:

```python
def fetch_email_metadata(
    self, sync_cursor: str | None = None, max_total: int = 500,
) -> tuple[list[EmailMetadata], str]:
```

Requirements:

- Fail fast if client is not authenticated (`EmailNotAuthenticatedError`).
- Return `(metadata_list, new_sync_cursor)`.
- If `sync_cursor` is `None` → bootstrap (Camino 1): fetch up to `max_total` messages.
- If `sync_cursor` is not `None` → attempt incremental (Camino 2), fall back to bootstrap on failure or if not yet implemented.
- `account_id` field on `EmailMetadata` is left empty (`""`) — stamped by the service layer before persistence.

#### `EmailMetadata` dataclass

```python
@dataclass
class EmailMetadata:
    provider_message_id: str
    thread_id: str
    from_email: str
    from_name: str
    subject: str
    received_at: datetime
    is_read: bool
    box: str          # "ALL_MAIL" | "SPAM" | "TRASH"
    account_id: str = ""
```

#### Box mapping (label → box)

```
labelIds contains "SPAM"  → box = "SPAM"
labelIds contains "TRASH" → box = "TRASH"
otherwise                 → box = "ALL_MAIL"
```

#### Gmail batch fetch pattern

1. **List message IDs** — paginated `messages.list()` with `includeSpamTrash=True`, no `q` filter, up to `max_total`.
2. **Batch-fetch metadata** — chunks of 100 IDs via `service.new_batch_http_request()` with `format="metadata"`, `metadataHeaders=["From", "Subject"]`.
3. **Parse each response** — extract `From` header via `email.utils.parseaddr()`, `Subject` header, `internalDate` (millis → UTC datetime), `labelIds` for `is_read` and `box`.
4. **Get current historyId** — `users().getProfile(userId="me")["historyId"]` as `new_sync_cursor`.

#### Sync cursor (Gmail)

- Bootstrap: `sync_cursor=None` → Camino 1 → returns `historyId` as new cursor.
- Incremental: `sync_cursor` present → validates via `users.history.list` probe. Currently falls back to bootstrap (Camino 2 not yet implemented).

#### Outlook

`fetch_email_metadata()` raises `EmailExternalAPIError("Outlook metadata sync not yet implemented.")`. Full implementation is planned for a future iteration.

### 6.2 `send_email`

Requirements:

- Fail if not authenticated.
- Validate non-empty `recipients` (`EmailRecipientsMissingError`).
- Raise typed core errors for provider/network failures.

## 7. Error Conventions

Use typed errors from `core/email/errors.py`.
Do not raise raw provider exceptions beyond the core boundary.

Typical mappings:

| Scenario | Core Error |
|---|---|
| Missing app credentials | `EmailMissingAppCredentialsError` |
| Missing access token | `EmailMissingTokenError` |
| Expired token without refresh token | `EmailMissingRefreshTokenError` |
| Refresh request failure | `EmailRefreshFailedError` |
| Unauthenticated operation | `EmailNotAuthenticatedError` |
| Missing recipients | `EmailRecipientsMissingError` |
| External API failure | `EmailExternalAPIError` |
| Unknown provider in manager | `EmailProviderConfigError` |
| Invalid account record fields | `EmailAccountRecordError` |
| Invalid or unparseable expiry value | `EmailInvalidExpiryError` |
| App credentials data is structurally invalid | `EmailInvalidCredentialsDataError` |
| Token data is structurally invalid | `EmailInvalidTokenDataError` |
| Duplicate account label in manager | `EmailDuplicateAccountLabelError` |
| Account label not registered in manager | `EmailAccountNotFoundError` |

The API service layer translates these into `ApiError` subclasses.

External consumers (services, test fixtures) should import through the package facade: `from core.email import CoreError, EmailManager, ...`

### Capture technique

Every provider client follows these rules when catching exceptions:

1. **Validate early, fail with domain errors.** Check config, tokens, and auth state at the top of each method before any external call. Raise the corresponding `EmailMissing*` or `EmailNotAuthenticatedError` immediately.
2. **Catch provider-specific exceptions first.** Each `try` block lists the concrete exception types the provider SDK can throw (e.g. `HttpError`, `TransportError`, `RefreshError` for Gmail; `HTTPError`, `URLError` for Outlook) before any generic handler.
3. **Generic fallback last.** A final `except Exception as exc` with message `"<Provider> unexpected <operation> error ({type}): {exc}"` ensures no exception escapes untyped.
4. **Preserve the cause chain.** Always `raise ... from exc` so the original traceback remains available for debugging.
5. **Never double-wrap typed errors.** This rule applies when code inside the `try` block can raise a `CoreError` subclass — either via an explicit `raise` statement (e.g. `raise EmailExternalAPIError(...)`) or through a helper function that raises one (e.g. `_token_request()` raises `EmailRefreshFailedError`). In that case, add a targeted `except CoreError: raise` (or the specific subclass) **before** the generic `except Exception` handler to re-raise it directly. Without this guard, the generic fallback would catch the already-typed error and wrap it inside a new one. When the guard is not a plain re-raise but converts to a different error type, it becomes a reclassification (see rule 6). **If nothing inside the `try` can produce a `CoreError`, the guard is unnecessary** — only external library calls remain, and those will never raise core exceptions. Example:
   ```python
   try:
       self._token_request(...)       # Can raise EmailRefreshFailedError (a CoreError)
       result = provider_sdk.call()
   except CoreError:                  # Guard: re-raise before generic catch
       raise
   except HttpError as exc:
       raise EmailExternalAPIError(...) from exc
   except Exception as exc:
       raise EmailExternalAPIError(...) from exc
   ```
6. **Reclassify when the functional meaning changes.** An external API failure during token refresh becomes `EmailRefreshFailedError`, not `EmailExternalAPIError`, because the operation that failed is authentication refresh.
7. **Best-effort parsing with soft fallback.** When processing response data (headers, dates, error bodies), tolerate malformed values with a fallback instead of aborting the entire operation.

## 8. Gmail and Outlook Reference

| Aspect | Gmail | Outlook |
|---|---|---|
| API integration | `googleapiclient` service object | `urllib` requests to Microsoft Graph |
| Interactive OAuth | `google-auth-oauthlib` local server flow | PKCE + local callback server |
| Silent refresh | Google `Credentials.refresh()` | Token endpoint POST (`refresh_token`) |
| Send operation | Gmail `users.messages.send` | Graph `POST /me/sendMail` |
| Metadata fetch | Gmail `messages.list` + `BatchHttpRequest` (`format="metadata"`) | Not yet implemented (stub raises `EmailExternalAPIError`) |
| Sync cursor | `historyId` from `users().getProfile()` | N/A |

## 9. Adding a New Provider Checklist

Core layer:

- [ ] Implement `EmailClient` in `backend/core/email/<provider>_client.py`.
- [ ] Reuse helper functions from `helpers.py`.
- [ ] Add provider branch in `EmailManager._build_client`.
- [ ] Raise typed `CoreError` subclasses for all failure paths.
- [ ] Export any new public symbols in `core/email/__init__.py`.

Database and config:

- [ ] Add provider env var mapping in `database/settings.py` and ensure `database/security/app_credentials.py` can load the new provider.
- [ ] Update provider CHECK constraint in `database/schema.sql`.

Services/tests/docs:

- [ ] Update `_CORE_TO_API_MAP` in `api/services/services_helpers.py` if the new provider introduces new error types.
- [ ] Ensure service flows call provider through existing helper APIs.
- [ ] Add unit tests for helper, auth, fetch, and send behavior.
- [ ] Add integration and E2E coverage.
- [ ] Update `README.md` and API/database docs.

## 10. Implementation Rules

- Keep provider-specific behavior inside provider client modules.
- Keep API-layer concerns out of core code.
- Keep secrets wrapped at boundaries and unwrapped only when required.
- Keep error messages explicit and operation-specific.
