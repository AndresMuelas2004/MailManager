# General Auth Layer Rules

This is the `CLAUDE.md` for the **authentication** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the auth layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

## 1. Layer Isolation

The `auth/` package is a framework-agnostic layer — it has **no imports from `api/`**. Services in the API layer translate `AuthError` subclasses into `ApiError` subclasses via a translation function (same pattern used for core and database errors).

## 2. Package Structure

```
auth/
├── __init__.py              # Public facade (re-exports everything below)
├── errors/                  # Auth-specific error hierarchy
│   ├── __init__.py          #   Re-exports all exceptions
│   └── errors.py            #   AuthError base + subclasses
├── settings.py              # Centralized env var reading and validation
└── <provider>_auth/         # One directory per identity provider
    ├── __init__.py
    └── <provider>.py         #   verify_<provider>_token — pure token verification
```

## 3. Public Facade

All external code imports from the package root (`from auth import ...`). The `__init__.py` re-exports:

- Error classes (full hierarchy)
- Settings dataclass and its loader function
- Provider verification functions

External consumers **never import from internal submodules** — only from the facade.

## 4. Settings Rules

- `settings.py` is the **only module** that reads `os.environ`.
- Settings are returned as a frozen dataclass.
- Missing or invalid required env vars raise `AuthSettingsError`.
- Settings are loaded per service call (not cached globally), so env var changes take effect without restart.

## 5. Token Verification Contract

Each identity provider module exposes a single verification function:

```python
def verify_<provider>_token(raw_token: str, ...) -> dict:
    """
    Verify a token and return the decoded claims.
    Raises AuthTokenError subclasses on any verification failure.
    """
```

The function must:

1. Accept the raw token string and any provider-specific config.
2. Return a `dict` of decoded claims on success.
3. Raise only `AuthTokenError` subclasses on failure — never raw provider exceptions.
4. Follow the capture technique described in § 7.

Claim validation (business logic like checking `sub`, `email`) stays in the service layer, not in the auth layer. The auth layer only verifies cryptographic validity.

## 6. Error Hierarchy

All errors follow the same base-class pattern: each class has a `code`, `default_message`, `message`, and `detail` dict.

```
AuthError                           # Base for all auth errors
├── AuthSettingsError               # Missing/invalid auth env vars
└── AuthTokenError                  # Base for token verification failures
    ├── AuthTokenNetworkError       # Transport/network failure during verification
    ├── AuthTokenInvalidError       # Malformed or bad-format token
    └── AuthTokenProviderError      # Provider rejected the token
```

### Semantic notes

- Error names are **provider-agnostic** — reusable across identity providers.
- `AuthTokenNetworkError` maps to a 502-equivalent, not 401. A transport failure is not an invalid token — the token may be valid, but the verification endpoint is unreachable. This lets clients differentiate "your token is bad" from "the verification service is down."

## 7. Capture Technique

Every provider verification function follows these rules when catching exceptions.

### Rules

1. **Catch provider-specific exceptions first.** List the concrete exception types the provider library can throw, ordered from most specific to most general.
2. **Map to the correct `AuthTokenError` subclass.** Each provider exception maps to the subclass that best describes the *functional* failure: network errors → `AuthTokenNetworkError`, provider rejections → `AuthTokenProviderError`, format errors → `AuthTokenInvalidError`.
3. **Catch built-in `ValueError` explicitly.** Some verification libraries raise `ValueError` for malformed tokens. Catch it before the generic handler and map to `AuthTokenInvalidError`.
4. **Generic fallback last.** A final `except Exception as exc` with a message including `type(exc).__name__` ensures no exception escapes untyped. Maps to `AuthTokenInvalidError` as the safest default. Internal layers may include `type(exc).__name__` in error messages since these are always translated before reaching the client.
5. **Preserve the cause chain.** Always `raise ... from exc`.
6. **Never double-wrap typed errors.** This rule applies when code inside a `try` block can raise an `AuthError` subclass — either via an explicit `raise` or through a helper that raises one. Add a targeted `except AuthTokenError: raise` **before** the generic `except Exception` handler. **If nothing inside the `try` can produce an `AuthError`, the guard is unnecessary.**

### Pattern

```python
try:
    return provider_sdk.verify(token, ...)
except ProviderNetworkError as exc:       # 1. Most specific provider error
    raise AuthTokenNetworkError(...) from exc
except ProviderBaseError as exc:          # 2. Provider rejection
    raise AuthTokenProviderError(...) from exc
except ValueError as exc:                # 3. Malformed token
    raise AuthTokenInvalidError(...) from exc
except Exception as exc:                 # 4. Generic fallback
    raise AuthTokenInvalidError(
        f"Unexpected verification error ({type(exc).__name__}): {exc}"
    ) from exc
```

## 8. Service-Side Translation

The service layer catches `AuthError` and translates via a mapping function:

```python
try:
    claims = verify_<provider>_token(raw_token, ...)
except AuthError as exc:
    raise translate_auth_error(exc) from exc
except Exception as exc:
    logger.warning("Unexpected error (%s): %s", type(exc).__name__, exc)
    raise Unauthorized("Token verification failed.") from exc
```

No context manager exists for auth translation — there are typically only a few catch sites.

## 9. Adding a New Identity Provider Checklist

### Auth layer

- [ ] Create `auth/<provider>_auth/<provider>.py` with `verify_<provider>_token(...)`.
- [ ] Follow the capture technique — map provider exceptions to `AuthTokenError` subclasses.
- [ ] Add the never-double-wrap guard only if internal helpers raise `AuthError` subclasses.
- [ ] If new env vars are needed, add them to `settings.py` and the settings dataclass.
- [ ] Re-export the verification function from `auth/__init__.py`.

### Service layer

- [ ] Add a service function (e.g. `<provider>_login`) in the auth service.
- [ ] Catch `AuthError` and translate via the translation function.
- [ ] Add claim validation (business logic) in the service, not in the auth layer.

### Error hierarchy

- The existing `AuthTokenError` subclasses are provider-agnostic and should cover most scenarios. Only create new subclasses if a provider introduces a failure mode requiring a different HTTP response or client-side handling.

### Router / schema

- [ ] Add a new endpoint (e.g. `POST /auth/<provider>`) — one endpoint per provider.
- [ ] Add request/response schemas.

### Tests and docs

- [ ] Unit tests for the verification function.
- [ ] Unit tests for the service function.
- [ ] Integration tests for the new endpoint.
- [ ] Update docs with the new provider's exception ordering.

## 10. Design Principles

- Keep provider-specific verification logic inside provider modules.
- Keep API-layer concerns out of auth code — no imports from `api/`.
- Keep settings centralized — the only module that reads env vars.
- Keep error names provider-agnostic — reuse across providers.
- Keep claim validation (business logic) in the service layer, not in the auth layer.

## 11. Project-Specific Guide

This file covers the general, transferable rules for the authentication layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`auth_guide.md`](auth_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
