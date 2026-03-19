> **Permanent rule (do not remove unless the user explicitly asks):**
> This document should only contain information that Claude cannot deduce from reading the code,
> or that would be complex / context-expensive to deduce. Information easily derived from the code
> does not need to be here.

# Auth Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Design Decisions

### Claim validation stays in the service layer

`verify_google_token` only verifies cryptographic validity and provider issuance. Business-logic checks (missing `sub`, missing `email`) are done in the service layer (`auth_service.google_login`), which raises `Unauthorized`. This separation keeps the auth layer reusable and free of API concerns.

### Settings are loaded per call

`get_auth_settings()` is called on each service invocation (not cached globally), so env var changes take effect immediately without restart.

## Behavioral Contracts — Traps to Avoid

### TransportError must be caught before GoogleAuthError

In `google_auth/google.py`, `TransportError` is a subclass of `GoogleAuthError`. It **must** be caught first — otherwise it gets swallowed by the `GoogleAuthError` handler and misclassified as a provider rejection instead of a network error.

### Never-double-wrap rule for future providers

The current `google.py` calls only `id_token.verify_oauth2_token(...)` — a Google library function that cannot raise `AuthError` subclasses, so no guard is needed. If a future provider module calls an internal helper that raises `AuthTokenError` subclasses from inside a `try` block, that module **must** add the re-raise guard:

```python
except AuthTokenError:    # Guard: re-raise before generic catch
    raise
```

## Extension

### New identity provider checklist (project-specific additions)

Beyond `CLAUDE.md` § 9:

- Create `auth/<provider>_auth/<provider>.py` with `verify_<provider>_token(...)`.
- If the provider requires new env vars, add them to `settings.py` and `AuthSettings`.
- Re-export the verification function from `auth/__init__.py`.
- The existing `AuthTokenError` subclasses (`AuthTokenNetworkError`, `AuthTokenInvalidError`, `AuthTokenProviderError`) are provider-agnostic. Only create new subclasses if a provider introduces a failure mode that needs a different HTTP response.
- Update this guide (capture technique ordering) with the new provider's exception ordering.
