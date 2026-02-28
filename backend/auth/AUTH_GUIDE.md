# Auth Layer Guide

This guide documents the authentication layer in `backend/auth/`.
Use it when maintaining the current Google OIDC flow or adding a new identity provider.

## Scope

This guide covers:

- Package structure and public facade
- `AuthSettings` configuration
- Token verification contract
- Error hierarchy and capture technique
- Service-side error translation
- Adding a new identity provider

## 1. Architecture

The `auth/` package is a framework-agnostic layer parallel to `core/email/` and `database/` — it has **no imports from `api/`**. Services in `api/services/` translate `AuthError` subclasses into `ApiError` subclasses via `translate_auth_error` / `_AUTH_TO_API_MAP` (same pattern as `translate_core_error` for core and `translate_database_error` for database).

```
auth/
├── __init__.py                  # Public facade (re-exports everything below)
│
├── errors/                      # Auth-specific error hierarchy
│   ├── __init__.py              #   Re-exports all exceptions
│   └── errors.py                #   AuthError base + subclasses
│
├── settings.py                  # Centralized env var reading and validation (AuthSettings)
│
└── google_auth/                 # Google OIDC provider
    ├── __init__.py
    └── google.py                #   verify_google_token — pure token verification
```

### Public facade

All external code imports from the package root (`from auth import ...`). The `__init__.py` re-exports:

| Symbol | Source module | Purpose |
|---|---|---|
| `AuthError` | `errors/` | Base auth exception |
| `AuthSettingsError` | `errors/` | Invalid/missing auth env vars |
| `AuthTokenError` | `errors/` | Base for token verification failures |
| `AuthTokenNetworkError` | `errors/` | Transport/network failure during verification |
| `AuthTokenInvalidError` | `errors/` | Malformed or bad-format token |
| `AuthTokenProviderError` | `errors/` | Provider rejected the token |
| `AuthSettings` | `settings.py` | Frozen dataclass with validated auth config |
| `get_auth_settings` | `settings.py` | Read and validate auth env vars |
| `verify_google_token` | `google_auth/google.py` | Google OIDC token verification |

External consumers (services) **never import from internal submodules** — only from the `auth` facade.

### Layer boundaries

- **`settings.py`** is the only module that reads `os.environ`.
- **`google_auth/`** contains provider-specific verification logic — no framework coupling.
- **`errors/`** defines the error hierarchy — shared across all modules in the layer.
- **`__init__.py`** re-exports everything — external code never imports submodules directly.

## 2. Settings (`settings.py`)

`get_auth_settings()` reads and validates auth-related environment variables and returns a frozen `AuthSettings` dataclass.

| Env var | Type | Default | Purpose |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | `str` | *(required)* | Google OAuth client ID for OIDC verification |
| `AUTH_SESSION_LIFETIME_DAYS` | `int` | `7` | Session duration in days (minimum `1`) |
| `AUTH_COOKIE_SECURE` | `bool` | `false` | `true` for HTTPS-only session cookies |

Validation rules:

- Missing or empty `GOOGLE_CLIENT_ID` raises `AuthSettingsError`.
- Invalid integer or value below minimum for `AUTH_SESSION_LIFETIME_DAYS` raises `AuthSettingsError`.
- Unrecognized boolean string for `AUTH_COOKIE_SECURE` raises `AuthSettingsError` (accepted: `1`, `true`, `yes`, `on`, `0`, `false`, `no`, `off`).

**Settings are loaded once per service call** (not cached globally), so env var changes take effect immediately without restart.

## 3. Token Verification Contract

Each identity provider module exposes a single verification function:

```python
def verify_<provider>_token(raw_token: str, ...) -> dict:
    """
    Verify a token and return the decoded claims.
    Raises AuthTokenError subclasses on any verification failure.
    """
```

The function must:

1. Accept the raw token string and any provider-specific config (e.g. `google_client_id`).
2. Return a `dict` of decoded claims on success.
3. Raise only `AuthTokenError` subclasses on failure — never raw provider exceptions.
4. Follow the capture technique described in § 5.

### Google OIDC (`google_auth/google.py`)

`verify_google_token(raw_id_token, google_client_id)` wraps `google.oauth2.id_token.verify_oauth2_token` with a 10-second clock skew tolerance.

The service layer (`auth_service.google_login`) calls this function and performs additional claim validation:

- Missing `sub` claim → `Unauthorized` (service-level check).
- Missing `email` claim → `Unauthorized` (service-level check).

These claim checks are business logic and stay in the service layer — the auth layer only verifies that the token is cryptographically valid and issued by the expected provider.

## 4. Error Hierarchy

All errors are defined in `auth/errors/errors.py` and follow the same base-class pattern as `CoreError` and `DatabaseError`: each class has a `code`, `default_message`, `message`, and `detail` dict.

```
AuthError                           # code="auth_error"
├── AuthSettingsError               # code="auth_settings_error"
└── AuthTokenError                  # code="auth_token_error"
    ├── AuthTokenNetworkError       # code="auth_token_network_error"
    ├── AuthTokenInvalidError       # code="auth_token_invalid_error"
    └── AuthTokenProviderError      # code="auth_token_provider_error"
```

### Exception classes

| Exception | `code` | Translates to (API) | HTTP | When |
|---|---|---|---|---|
| `AuthError` | `auth_error` | `ApiError` (fallback) | 500 | Base for all auth errors |
| `AuthSettingsError` | `auth_settings_error` | `EnvVarError` | 500 | Missing/invalid auth env vars |
| `AuthTokenError` | `auth_token_error` | `Unauthorized` | 401 | Base for token verification failures |
| `AuthTokenNetworkError` | `auth_token_network_error` | `ExternalAPIError` | 502 | Network failure during verification |
| `AuthTokenInvalidError` | `auth_token_invalid_error` | `Unauthorized` | 401 | Malformed or bad-format token |
| `AuthTokenProviderError` | `auth_token_provider_error` | `Unauthorized` | 401 | Provider rejected the token (expired, wrong audience, etc.) |

Error names are **provider-agnostic**. They cover Google OIDC today and are reusable for future identity providers.

### Semantic note

`AuthTokenNetworkError` maps to `ExternalAPIError` (502), not `Unauthorized` (401). A transport failure is not an invalid token — the token may be perfectly valid, but the verification endpoint is unreachable. This distinction lets clients differentiate between "your token is bad" (retry with a new token) and "the verification service is down" (retry later).

## 5. Capture Technique

Every provider verification function follows these rules when catching exceptions.

### Rules

1. **Catch provider-specific exceptions first.** List the concrete exception types the provider library can throw, ordered from most specific to most general. For Google: `TransportError` (subclass of `GoogleAuthError`) before `GoogleAuthError`.
2. **Map to the correct `AuthTokenError` subclass.** Each provider exception maps to the `AuthTokenError` subclass that best describes the *functional* failure: network errors → `AuthTokenNetworkError`, provider rejections → `AuthTokenProviderError`, format errors → `AuthTokenInvalidError`.
3. **Catch built-in `ValueError` explicitly.** Some verification libraries (including Google's `id_token`) raise `ValueError` for malformed tokens. Catch it before the generic handler and map to `AuthTokenInvalidError`.
4. **Generic fallback last.** A final `except Exception as exc` with a message including `type(exc).__name__` ensures no exception escapes untyped. Maps to `AuthTokenInvalidError` as the safest default.
5. **Preserve the cause chain.** Always `raise ... from exc` so the original traceback remains available for debugging.
6. **Never double-wrap typed errors.** This rule applies when code inside a `try` block can raise an `AuthError` subclass — either via an explicit `raise` statement or through a helper function that raises one. In that case, add a targeted `except AuthTokenError: raise` (or the specific subclass) **before** the generic `except Exception` handler to re-raise it directly. Without this guard, the generic fallback would catch the already-typed error and wrap it inside a new one. **If nothing inside the `try` can produce an `AuthError`, the guard is unnecessary** — only external library calls remain, and those will never raise auth exceptions.

### Current application

In `google_auth/google.py`, the `try` block calls only `id_token.verify_oauth2_token(...)` — a Google library function that cannot raise `AuthError` subclasses. Therefore the never-double-wrap guard is **not present** (it would be dead code).

If a future provider module calls an internal helper that raises `AuthTokenError` subclasses from inside a `try` block, that module **must** add the guard:

```python
try:
    result = _some_internal_helper(...)       # This helper raises AuthTokenProviderError
    return provider_sdk.verify(result)
except AuthTokenError:                        # Guard: re-raise before generic catch
    raise
except ProviderSpecificError as exc:
    raise AuthTokenProviderError(...) from exc
except Exception as exc:
    raise AuthTokenInvalidError(...) from exc
```

### Google OIDC exception ordering

```python
try:
    return id_token.verify_oauth2_token(...)
except TransportError as exc:           # 1. Network (most specific — subclass of GoogleAuthError)
    raise AuthTokenNetworkError(...)
except GoogleAuthError as exc:          # 2. Provider rejection (expired, wrong audience, etc.)
    raise AuthTokenProviderError(...)
except ValueError as exc:              # 3. Malformed token (Google library convention)
    raise AuthTokenInvalidError(...)
except Exception as exc:               # 4. Generic fallback
    raise AuthTokenInvalidError(...)
```

`TransportError` is a subclass of `GoogleAuthError`, so it **must** be caught first — otherwise it would be swallowed by the `GoogleAuthError` handler and misclassified as a provider rejection instead of a network error.

## 6. Service-Side Error Translation

The service layer (`api/services/auth_service.py`) catches auth errors and translates them to API errors using `translate_auth_error()` from `services_helpers.py`.

### Translation mapping (`_AUTH_TO_API_MAP`)

```python
_AUTH_TO_API_MAP = [
    (AuthSettingsError,      EnvVarError),        # 500
    (AuthTokenNetworkError,  ExternalAPIError),    # 502
    (AuthTokenInvalidError,  Unauthorized),        # 401
    (AuthTokenProviderError, Unauthorized),        # 401
    (AuthTokenError,         Unauthorized),        # 401
    (AuthError,              ApiError),            # 500
]
```

The mapping is evaluated with `isinstance` — most specific first. The `auth_code` key is added to the API error `detail` dict for debuggability.

### Usage in `auth_service.py`

```python
# Settings errors
def _load_auth_settings() -> AuthSettings:
    try:
        return get_auth_settings()
    except AuthSettingsError as exc:
        raise translate_auth_error(exc) from exc

# Token verification errors
def google_login(raw_id_token, response):
    settings = _load_auth_settings()
    try:
        id_info = verify_google_token(raw_id_token, settings.google_client_id)
    except AuthTokenError as exc:
        logger.debug("Google token verification failed: %s", exc)
        raise translate_auth_error(exc) from exc
```

No `catch_auth_errors()` context manager exists — there are only two catch sites, not enough to justify one.

## 7. Environment Variables

| Env var | Required | Default | Read by |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | Yes | — | `settings.py` |
| `AUTH_SESSION_LIFETIME_DAYS` | No | `7` | `settings.py` |
| `AUTH_COOKIE_SECURE` | No | `false` | `settings.py` |

All are read via `os.getenv()` in `settings.py`. The backend loads `backend/.env` via `python-dotenv` (`override=False`), so OS/Docker env vars take precedence.

## 8. Testing

### Unit tests

- **`tests/unit/api/test_auth_settings.py`** — validates `get_auth_settings()` behavior: defaults, missing required vars (`AuthSettingsError`), invalid types.
- **`tests/unit/api/services/test_auth_service.py`** — monkeypatches `verify_google_token` to raise `AuthTokenInvalidError`, `AuthTokenNetworkError`, etc. Verifies the service correctly translates to `Unauthorized`, `ExternalAPIError`, etc.

### Integration tests

- **`tests/integration/test_auth_endpoints.py`** — monkeypatches `verify_google_token` at the service import level. Tests login success, invalid token (401), session validation, logout, ownership enforcement, and account deletion cascade.

### Testing pattern

Tests monkeypatch `verify_google_token` to raise `AuthTokenError` subclasses (not raw `ValueError` or provider exceptions). This tests the service translation layer in isolation from provider libraries.

## 9. Adding a New Identity Provider

When adding a new provider (e.g. Microsoft Entra ID, GitHub OAuth):

### Auth layer (`auth/`)

- [ ] Create `auth/<provider>_auth/<provider>.py` with a `verify_<provider>_token(...)` function.
- [ ] Follow the capture technique in § 5 — map provider exceptions to `AuthTokenError` subclasses.
- [ ] Add the never-double-wrap guard **only if** code inside the `try` calls internal helpers that raise `AuthError` subclasses.
- [ ] If the provider requires new env vars, add them to `settings.py` and `AuthSettings`.
- [ ] Re-export the verification function from `auth/__init__.py`.

### Service layer (`api/services/`)

- [ ] Add a service function (e.g. `<provider>_login`) in `auth_service.py`.
- [ ] Catch `AuthTokenError` and translate via `translate_auth_error`.
- [ ] Add claim validation (business logic) in the service, not in the auth layer.

### Error hierarchy

The existing `AuthTokenError` subclasses (`AuthTokenNetworkError`, `AuthTokenInvalidError`, `AuthTokenProviderError`) are **provider-agnostic** and should cover most scenarios. Only create new subclasses if a provider introduces a failure mode that doesn't fit any existing class and requires a different HTTP response or client-side handling.

### Router / schema

- [ ] Add a new endpoint (e.g. `POST /auth/<provider>`) in `auth_routers.py`.
- [ ] Add request/response schemas in `api/schemas/auth.py`.

### Tests and docs

- [ ] Add unit tests for the verification function (raise provider exceptions, verify correct `AuthTokenError` subclass).
- [ ] Add unit tests for the service function (monkeypatch verification, verify correct `ApiError` subclass).
- [ ] Add integration tests for the new endpoint.
- [ ] Update this guide (§ 3 and § 5) with the new provider's exception ordering.
- [ ] Update `CLAUDE.md` if architectural patterns change.

## 10. Design Principles

- Keep provider-specific verification logic inside provider modules (`google_auth/`, etc.).
- Keep API-layer concerns out of auth code — no imports from `api/`.
- Keep settings centralized in `settings.py` — the only module that reads env vars.
- Keep error names provider-agnostic — reuse across providers.
- Keep claim validation (business logic like checking `sub`, `email`) in the service layer, not in the auth layer. The auth layer only verifies cryptographic validity.
