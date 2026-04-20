> **Permanent rule — read before editing this file.**
>
> This file is loaded into context on every Claude session. A line here only justifies its tokens if it cannot be reconstructed by reading the code.
>
> **Before writing or keeping a line, ask: could I rebuild this by opening the relevant file(s) for ~30 seconds?**
> - **YES → delete it.** The code is the source of truth. Catalogs of what modules / functions / tests do, paraphrases of names or bodies, exhaustive kwarg / field / config enumerations, flow tables that mirror existing file or symbol names, and step-by-step recipes for code that is itself readable all fall here. Delete them on sight.
> - **NO → keep it.** Silent traps when extending the layer, cross-file asymmetries (siblings that don't behave alike), ordering / lifecycle rules whose violation breaks everything, invariants whose silent regression would slip through review, historical decisions whose rationale isn't in the code, and fixed identifiers (UUIDs, seeded data, magic constants) that cannot be recomputed — those earn their tokens.
>
> **When updating this file, re-read every section and delete anything that has since migrated into the code.** Staleness is worse than silence.

# Auth Layer Guide

> **General rules**: this layer MUST respect every rule defined in
> [`CLAUDE.md`](./CLAUDE.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Traps

### `TransportError` must be caught **before** `GoogleAuthError`

`google.auth.exceptions.TransportError` is a **subclass** of `GoogleAuthError`. Its handler must come first. Swap the order and network failures get misclassified as provider rejections — users see 401 "invalid token" when the real problem is that Google's verification endpoint is unreachable (which should surface as 502 via `AuthTokenNetworkError`).

### Never-double-wrap guard — conditional, currently unneeded

The guard pattern described in `auth/CLAUDE.md` §7 rule 6 is only required when code inside a `try` block can raise an `AuthError` subclass. The current `google.py` does not need it: `id_token.verify_oauth2_token(...)` is a Google library call that cannot produce `AuthError`. A future provider whose `verify_*_token` helper internally calls something that raises `AuthTokenError` **must** add:

```python
except AuthTokenError:  # re-raise before the generic catch
    raise
```

Otherwise the `except Exception` below re-wraps our own typed error as `AuthTokenInvalidError`, losing the network/provider/format classification.

### Claim validation lives in the service, not in the auth layer

`verify_google_token` only verifies cryptographic validity and provider issuance. Business-logic checks (`sub` present, `email` present, etc.) belong in `auth_service.google_login`, which raises `Unauthorized`. This separation keeps the auth layer reusable across endpoints and free of API concerns.

## Extension — new identity provider

See the general checklist in `auth/CLAUDE.md` §9. Project-specific additions:

- The existing `AuthTokenError` subclasses (`AuthTokenNetworkError`, `AuthTokenInvalidError`, `AuthTokenProviderError`) are provider-agnostic. Only create a new subclass when a provider introduces a failure mode that needs a different HTTP response or client-side handling.
- When adding a new provider module, update the "TransportError must be caught first" trap above with that provider's specific subclass relationship (or confirm it doesn't apply).
