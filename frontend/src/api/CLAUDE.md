# General API Client Layer Rules

This is the `CLAUDE.md` for the **API client layer** of the frontend — the single doorway between the browser application and the backend HTTP surface. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the API client layer from day one.

**Precedence.** In case of conflict between this file and any document further down the repository, these rules take precedence.

**Immutable.** This file must never be edited. All changes to API-layer rules go through a new version of this file.

## 1. Purpose

`api/` is the **only** layer permitted to invoke `fetch()` or talk to the backend in any form. Every other layer reaches the network exclusively through this layer. The contract with the backend — paths, methods, request/response shapes, error envelope — is expressed here and nowhere else.

## 2. Structure

```
api/
├── client/
│   ├── http.ts      # request<T>() — the single fetch wrapper
│   └── errors.ts    # ApiError, ValidationError, UiError, toUiError
├── endpoints/       # One file per backend resource, thin wrappers
└── types/
    └── dto.ts       # Zod schemas + inferred TypeScript types
```

## 3. HTTP Client Rules (`client/`)

### 3.1 Single `request<T>()`
- Exactly **one** function issues HTTP calls in the whole codebase. No other file in `src/` may call `fetch()` directly.
- `request<T>()` accepts: `path`, `method`, optional `body`, optional `AbortSignal`, optional `schema` (Zod validator for the response).
- Applies `credentials: "include"` on every call.
- Serialises bodies as JSON and sets `Content-Type: application/json` only when a body is provided.

### 3.2 Response handling
- On non-2xx, convert the response into an `ApiError` through the backend's standard error envelope.
- On 2xx, if a `schema` was provided, run `schema.safeParse(json)` and raise a `ValidationError` if the payload fails. On success, return the parsed value so the caller gets a type narrower than the wire contract.
- On network-level failure, raise a generic `ApiError` with code `network_error`.

### 3.3 Error hierarchy
- `ApiError` is the base class. It carries `code`, `message`, optional `status`, optional `detail`.
- `ValidationError extends ApiError` adds the Zod `issues` array and uses code `schema_mismatch`.
- `UiError` is the plain object shape (`{ message, code? }`) safe for UI consumption. `toUiError(err)` is the canonical translator that every higher layer must use.

### 3.4 Credentials and token storage
- Session tokens, access tokens, and any credential material **must never** be written to `localStorage` or `sessionStorage`. Both are readable by any script running on the page, which turns a single XSS into a full session takeover.
- When the backend supports it, authentication travels in `httpOnly` + `Secure` + `SameSite` cookies, and `request<T>()` surfaces them via `credentials: "include"` (see §3.1). The frontend never handles the raw token.
- When the backend forces a bearer token the browser has to hold, it lives in memory only (a module variable or a closure inside `client/`) and is cleared on logout. It never crosses into storage, `window`, or any other globally reachable surface.

## 4. Endpoint Rules (`endpoints/`)

### 4.1 Shape
- One file per backend resource. The file name mirrors the resource name (e.g. `users.ts`, `orders.ts`).
- Every function is a **thin wrapper** around `request<T>()`: HTTP method, path, optional body, matching schema. No retry logic, no caching, no branching, no business rules.
- Functions return `Promise<T>` where `T` is the Zod-inferred type from `types/dto.ts`.

### 4.2 Schema pass-through
- Every call to `request()` that returns data passes its response schema. "No schema" is only acceptable for responses with no body (`204 No Content`).

## 5. DTO Rules (`types/`)

### 5.1 Schema-first
- Every DTO is defined as a Zod `z.object({...})` (or `z.array(...)`) exported as `xxxSchema`.
- The TypeScript type is **inferred**: `export type X = z.infer<typeof xSchema>`. Never hand-write the `type` alongside the schema.

### 5.2 Wire-format fidelity
- Field names match the backend **exactly**, including casing convention (`snake_case` if the backend uses it). The frontend does not translate names at this boundary.
- Nullability is expressed with `.nullable()` when the backend may return `null`, and `.optional()` when the field may be omitted. Never both unless the backend genuinely produces three states.

### 5.3 Reusable envelopes
- Shared response shapes (e.g. `{ status: string }`, `{ message: string }`) are declared once at the top of `dto.ts` as `statusResponseSchema`, `messageResponseSchema`, etc., and reused across endpoints. Do not inline them.

## 6. Must / Must Not

### Must
- Route every network call through `request<T>()`.
- Validate every response body that is not `204` through a Zod schema.
- Surface errors as `ApiError` / `ValidationError`; never as raw `Error` or `Response`.
- Keep credential material out of every web-storage API (see §3.4).

### Must Not
- Call `fetch()` outside `client/http.ts`.
- Maintain in-memory caches here. Caching belongs in the data-fetching layer used by features (TanStack Query).
- Import from `features/`, `components/`, or `app/`. This layer is strictly lower than any of them.
- Hand-write types that should be inferred from a schema.
- Persist tokens, sessions, or credentials in `localStorage`, `sessionStorage`, `IndexedDB`, or any other script-readable storage.

## 7. Import Boundaries

| Allowed imports                      | Forbidden imports                                  |
|--------------------------------------|----------------------------------------------------|
| `zod`, `lib/` (rare), own files      | `features/`, `components/`, `app/`, `test/`       |

The API layer sits just above `lib/` in the dependency graph. See `../lib/CLAUDE.md` for the leaf-layer rules.

## 8. Adding a New Endpoint — Checklist

- [ ] **DTOs**: add the request/response Zod schemas to `types/dto.ts` and the inferred types alongside.
- [ ] **Endpoint**: create or extend the file in `endpoints/` for the resource; add a thin wrapper around `request()` that passes the matching schema.
- [ ] **Errors**: if the backend introduces a new error code the UI cares about, surface it via `ApiError.code`; do not add subclasses without a structural reason.
- [ ] **No retry / caching / business logic** here — push that to the calling hook in `features/`.
- [ ] **Tests**: add a default MSW handler mirroring the new endpoint in `src/test/msw/handlers.ts` so integration tests keep working. See `../test/CLAUDE.md`.
