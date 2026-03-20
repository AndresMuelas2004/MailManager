# General Core Layer Rules

This is the `CLAUDE.md` for the **core business logic** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the core layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.
**Immutable.** This file must never be edited. All project-specific changes go in the `*_guide.md` file referenced at the end of this document.
## 1. Layer Isolation

The `core/` package is a framework-agnostic layer — it has **no imports from `api/`**, `database/`, or `auth/`. Services in the API layer translate `CoreError` subclasses into `ApiError` subclasses via a translation function.

## 2. Error Hierarchy Pattern

All core errors derive from a single base class. Each class provides:

- `code` — stable string identifier
- `default_message` — class-level default
- `message` — instance-level override (falls back to `default_message`)
- `detail` — optional dict with structured context

Subclass errors by functional domain (e.g. email errors, payment errors) while keeping a flat or shallow hierarchy within each domain.

## 3. Capture Technique

Every core module follows these rules when catching exceptions.

### Rules

1. **Validate early, fail with domain errors.** Check config, tokens, and auth state at the top of each method before any external call. Raise the corresponding domain error immediately.

2. **Catch provider-specific exceptions first.** Each `try` block lists the concrete exception types the provider SDK can throw, ordered from most specific to most general.

3. **Generic fallback last.** A final `except Exception as exc` with message `"<Provider> unexpected <operation> error ({type}): {exc}"` ensures no exception escapes untyped. Internal layers may include `type(exc).__name__` in error messages since these are always translated before reaching the client.

4. **Preserve the cause chain.** Always `raise ... from exc` so the original traceback remains available for debugging.

5. **Never double-wrap typed errors.** This rule applies when code inside a `try` block can raise a `CoreError` subclass — either via an explicit `raise` or through a helper that raises one. Add a targeted `except CoreError: raise` (or the specific subclass) **before** the generic `except Exception` handler. **If nothing inside the `try` can produce a `CoreError`, the guard is unnecessary.** Example:
   ```python
   try:
       self._internal_helper(...)     # Can raise a CoreError subclass
       result = provider_sdk.call()
   except CoreError:                  # Guard: re-raise before generic catch
       raise
   except ProviderError as exc:
       raise DomainSpecificError(...) from exc
   except Exception as exc:
       raise DomainSpecificError(...) from exc
   ```

6. **Reclassify when the functional meaning changes.** An external API failure during token refresh becomes a refresh error, not a generic external API error, because the operation that failed is authentication refresh.

7. **Best-effort parsing with soft fallback.** When processing response data (headers, dates, error bodies), tolerate malformed values with a fallback instead of aborting the entire operation.

## 4. Public Facade Rules

- All external code imports from the package root or domain sub-package facade.
- The `__init__.py` re-exports all public symbols.
- External consumers never import from internal submodules directly.

## 5. Design Principles

- Keep external-integration behavior encapsulated inside dedicated modules (e.g. provider clients, adapters).
- Keep API-layer concerns out of core code — no imports from `api/`.
- Keep secrets wrapped at boundaries and unwrapped only when required.
- Keep error messages explicit and operation-specific.
- Use shared helpers for common operations to avoid duplication across implementations.

## 6. Project-Specific Guide

This file covers the general, transferable rules for the core business logic layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`core_guide.md`](core_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
