# General API Layer Rules

This is the `general_api_rules.md` for the **HTTP API** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the API layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

## 1. Package Structure

The API layer is organized into four sub-packages:

```
api/
├── app.py              # Application factory, lifespan, CORS, router registration
├── errors/             # API error hierarchy + framework exception handlers
├── routers/            # Thin HTTP surface — one service call per endpoint
├── schemas/            # Pydantic request/response models
└── services/           # Orchestration, validation, error mapping
```

## 2. Layer Boundaries

- **Routers** — thin HTTP surface. Zero business logic. Each endpoint declares Pydantic schemas and contains a single service call.
- **Services** — orchestration, validation, and error mapping. The only layer that raises `ApiError` subclasses. Services call into lower layers — never the reverse.
- **Errors** — defines the `ApiError` hierarchy and the framework exception handlers that translate them to HTTP responses.
- **Schemas** — Pydantic `BaseModel` subclasses defining the API contract.

Hard rule: routers never contain business logic, services never expose HTTP details (except receiving `Response` for cookie management).

## 3. Router Rules

Every router follows the same pattern:

1. **One service call per endpoint.** The route function calls a single service function and returns its result.
2. **Auth dependency** on all protected endpoints — returns the authenticated identity.
3. **No business logic.** No conditionals, no error handling, no data transformation.
4. **Pydantic schemas** declare the request/response contract.

## 4. Service Rules

- The **only layer** that raises `ApiError` subclasses.
- **Ownership check** — for any action scoped to a resource, verify the authenticated user owns it before proceeding.
- **Builder helpers** — build provider/manager objects exclusively via dedicated builder functions. Never instantiate provider clients directly.
- **Database calls** — wrap all database calls in explicit `try`/`except` blocks using a translation helper that catches `DatabaseError` and unexpected exceptions, consistent with the pattern used for core and auth errors.
- **Cookie management** — services that manage session cookies receive the framework `Response` object from the router. Cookie setting/clearing happens in the service layer, not in routers.

## 5. Error Hierarchy

All API errors derive from a single base class with a stable `code` string. A status map translates error types to HTTP status codes.

### Base class contract

Every `ApiError` subclass provides:
- `code` — stable string identifier (e.g. `"resource_not_found"`)
- `message` — human-readable description
- `detail` — optional dict with structured context

### HTTP status mapping

A `_STATUS_MAP` dict maps each error class to its HTTP status code. The base `ApiError` defaults to 500.

### Response envelope

All error responses use a standard envelope:

```json
{
  "error": {
    "code": "error_code",
    "message": "Human-readable message.",
    "detail": {}
  }
}
```

## 6. Error Message Uniqueness

Every `ApiError` raised directly in the service layer (i.e. not escalated from a lower layer, which already carries its own descriptive message) **must** have a `message` that:

1. **Describes what happened and where** — the message must be concrete enough to identify the failing operation and its context without inspecting a stack trace.
2. **Is globally unique across all raise sites** — no two raise statements in the entire service layer may share the same message string. This guarantees that a single error message is sufficient to pinpoint exactly where the error originated.

Bad: `raise ResourceNotFoundError("Not found")` — generic, duplicated across multiple sites.
Good: `raise ResourceNotFoundError("Order not found while processing refund for the given transaction")` — specific to the operation and site.

## 7. ApiError Subclass Granularity

Every `ApiError` subclass must represent the **semantic meaning** of the error from the context where it is raised. Reading the error type alone should give a strong hint about what went wrong and in which area of the service layer.

### Rules

1. **One concept per class** — do not reuse a generic class (e.g. `OperationError`) across unrelated operations. If two errors describe fundamentally different failures, they deserve different classes.
2. **As many classes as needed** — create as many `ApiError` subclasses as necessary to maintain a tight relationship between the error type and the raising context. Under-specifying error types hides information; prefer more classes over fewer.
3. **Self-documenting names** — the class name should read as a short description of the failure domain (e.g. `ResourceOwnershipError`, `SessionExpiredError`, `DataSyncError`).
4. **Register every new class** — add it to `_STATUS_MAP` with the appropriate HTTP status code and document it in the project-specific API guide.

## 8. Error Handling — Capture Technique

This is the central pattern for error handling in the service layer. Every `try` block in services follows the same ordered structure.

### The pattern

```python
try:
    result = lower_layer_call(...)
except LayerError as exc:                   # 1. Typed layer error → translate
    raise translate_layer_error(exc, fallback=SpecificApiError) from exc
except Exception as exc:                    # 2. Unexpected error → log + generic ApiError
    logger.warning("Unexpected error (%s): %s", type(exc).__name__, exc)
    raise SpecificApiError("Failed to ...") from exc
```

### Rules

1. **Catch the layer base class** (`CoreError`, `AuthError`, `DatabaseError`) — the translation function uses `isinstance` to find the most specific mapping.
2. **Always `from exc`** — preserve the cause chain.
3. **Fallback matches the context** — use the `ApiError` subclass that best describes the failed operation.
4. **Never expose internal details in API messages** — the `except Exception` fallback must use a generic message (no `type(exc).__name__`, no `str(exc)`). Log the full details server-side with `logger.warning()` instead. This prevents leaking internal state (class names, library errors, paths) to external clients. Internal layers (`core/`, `database/`, `auth/`) may include details in their errors because those are always translated before reaching the client.
5. **Never let lower-layer exceptions escape** — every `try` block has an `except Exception` fallback.

### Translation functions and maps

Translation functions convert lower-layer errors to `ApiError` subclasses. Each uses an `isinstance`-based mapping list evaluated most specific first. The final entry is always `(LayerErrorBase, ApiError)` as a catch-all.

### Database error pattern

Database calls use the same explicit `try`/`except` pattern as core and auth:

```python
try:
    record = store.get(resource_id)
except DatabaseError as exc:
    raise translate_database_error(exc) from exc
except Exception as exc:
    logger.warning("Unexpected <operation> error (%s): %s", type(exc).__name__, exc)
    raise ApiError("Failed to <operation>.") from exc
```

`translate_database_error` maps `DatabaseError` subclasses to `ApiError` subclasses via the mapping. The `except Exception` fallback catches truly unexpected non-DB errors.

## 9. Global Exception Handlers

Two framework exception handlers form the final safety net:

1. **Typed handler** — catches any `ApiError`, looks up the HTTP status from `_STATUS_MAP` (default 500), and returns the error envelope.
2. **Generic handler** — catches any `Exception` not already handled, logs the full traceback, and returns a generic 500 error envelope. This should never fire if all service functions follow the capture technique.

## 10. Application Factory

The `create_app()` factory:

1. Loads environment variables (OS/Docker env vars take precedence over `.env` files).
2. Creates the framework instance with a lifespan context manager.
3. Adds CORS middleware.
4. Registers error handlers.
5. Includes all routers in order.

### Lifespan

- **Startup**: runs optional auto-migrations, then warms the connection pool.
- **Shutdown**: closes the connection pool.

## 11. Schema Rules

- All schemas are Pydantic `BaseModel` subclasses.
- Request schemas define validation constraints (min length, allowed values, etc.).
- Response schemas define the API contract for clients.
- Error schemas define the standard error envelope.

## 12. Router Helper Rules

- Shared `Depends` callables live in a dedicated helper module.
- The session/auth dependency validates the session and returns the authenticated identity.
- All protected routes use the auth dependency.
- Override the auth dependency in integration tests to return a fixed test identity.

## 13. Adding a New Endpoint Checklist

- [ ] **Schema** — add request/response models in the schemas package.
- [ ] **Service** — add the service function. Follow service conventions: ownership check, database error wrapping, translation of layer errors, `except Exception` fallback.
- [ ] **Router** — add the route. Single service call, auth dependency unless unauthenticated.
- [ ] **Register** — include the router in the factory if it's a new router module.
- [ ] **Error mapping** — if new `ApiError` subclasses are needed, add them and register their HTTP status.
- [ ] **Unit tests** — test the service function in isolation.
- [ ] **Integration tests** — test the endpoint via the framework test client.
- [ ] **Docs** — update the project-specific API guide if patterns change.

## 14. Project-Specific Guide

This file covers the general, transferable rules for the HTTP API layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`api_guide.md`](api_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `general_api_rules.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
