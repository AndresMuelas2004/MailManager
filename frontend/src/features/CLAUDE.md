# General Feature Slice Layer Rules

This is the `CLAUDE.md` for the **feature layer** of the frontend — the vertical-slice directory where the majority of application code lives. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the feature layer from day one.

**Precedence.** In case of conflict between this file and any document further down the repository, these rules take precedence.

**Immutable.** This file must never be edited. All changes to feature-layer rules go through a new version of this file.

## 1. Purpose

Each direct subdirectory of `features/` is a **vertical slice** of the application: one self-contained domain, with its own pages, hooks, and components. Features are the place where UI, local state, and server state are assembled into user-facing behavior.

```
features/
├── <domain-a>/
├── <domain-b>/
└── ...
```

Every feature is self-contained. Features **never** depend on each other.

## 2. Feature Structure

Every feature directory has **exactly three** subdirectories — no more, no less:

```
features/<name>/
├── pages/        # Route-level components — one file per route
├── hooks/        # Feature-specific hooks (fetching, mutation, local state)
└── components/   # Feature-specific presentational components
```

Any other layout is a violation. If a file seems not to fit, it belongs in a different layer:
- Shared by multiple features → `components/` or `lib/`.
- HTTP contract → `api/`.

## 3. Page Rules (`pages/`)

### 3.1 One file per route
- Exactly one route in the router maps to each file in `pages/`. A page file that has no route is dead code.

### 3.2 Orchestrate, don't render
- A page instantiates the feature's hooks, and passes the resulting data and callbacks as props to components. Pages contain minimal JSX — the structural skeleton and any top-level layout concerns only.

### 3.3 No direct HTTP
- Pages never import from `api/endpoints/`. All data access flows through the feature's hooks.

## 4. Hook Rules (`hooks/`)

### 4.1 TanStack Query first
- Reads go through `useQuery` with a stable `queryKey`.
- Writes go through `useMutation`. On success, invalidate the relevant `queryKey` via `queryClient.invalidateQueries(...)` so dependent queries refetch automatically.
- Query keys follow a consistent shape: `[<resource>, <scope>, ...<filters>]`. Filters that may be `undefined` use `filter ?? null` to keep the key stable.

### 4.2 Side-effect ownership
- All `fetch`-adjacent side effects, including schema-derived calls to `api/endpoints/`, live in hooks. Never in components, never in pages directly.

### 4.3 Error translation
- Every hook that exposes errors to the UI converts them through `toUiError()` from `../../api/client/errors`. Consumers receive a `UiError`, never a raw `Error` or `ApiError`.

### 4.4 Public contract
- A list hook returns an object with `{ data, loading, error, refresh, ... }` or an equivalently flat shape. The keys are derived, not raw TanStack Query objects — callers should not need to understand TanStack Query internals to consume the hook.
- A mutation hook returns callable functions (plus `loading` / `error`) rather than raw `useMutation` return values.

### 4.5 Derived flags
- When a feature needs a separate "background syncing" indicator alongside the first-load spinner, derive `syncing` as something like `mutation.isPending || (query.isFetching && !query.isLoading)` so the indicator stays on during the post-invalidation refetch.

## 5. Component Rules (`components/`)

### 5.1 Presentational
- Components receive data via props and emit events via callbacks. They do not import from `api/` and they do not call hooks that fetch data.

### 5.2 Local UI state only
- `useState` is allowed for UI concerns (toggles, selection, input drafts). Anything representing server truth stays in a hook.

### 5.3 One file per component
- `PascalCase.tsx` with a matching default export. Props typed explicitly.

## 6. Cross-Feature Rule (Hard Boundary)

A file under `features/<a>/` may **not** import from `features/<b>/` under any circumstance. If two features need the same thing:

- Shared JSX → promote to `components/common/` or `components/ui/`.
- Shared logic → promote to `lib/` (or, if HTTP-bound, to a new endpoint in `api/`).
- Shared type → promote to `lib/types.ts`.

Violations of this rule are the most common cause of coupling rot. Reject them without exception.

## 7. Must / Must Not

### Must
- Keep `pages/`, `hooks/`, and `components/` inside every feature directory.
- Route every remote call through a hook in `hooks/`.
- Translate errors with `toUiError` at the hook boundary.

### Must Not
- Import from another feature.
- Call `fetch()` or `useQuery`/`useMutation` from components. Those live in hooks.
- Define routing logic inside the feature. Pages are exported; the router decides where they mount.

## 8. Import Boundaries

| From `features/<x>/`            | May import from                                                  | May not import from                         |
|---------------------------------|------------------------------------------------------------------|---------------------------------------------|
| `pages/`                        | own `hooks/`, own `components/`, `components/`, `lib/`           | `api/client/http` (go through endpoints)    |
| `hooks/`                        | `api/endpoints/`, `api/client/errors`, `api/types/`, `lib/`      | `components/ui/`, `components/common/`      |
| `components/`                   | `components/common/`, `components/ui/`, `lib/`                   | `api/`                                      |
| any of the three                | `features/<y>/` — **never**                                      |                                             |

See `../api/CLAUDE.md` for the API contract and `../components/CLAUDE.md` for the shared UI tiers.

## 9. Adding a New Feature — Checklist

- [ ] Read `../api/CLAUDE.md`, `../components/CLAUDE.md`, `../lib/CLAUDE.md`, and `../test/CLAUDE.md` before writing code.
- [ ] Create `features/<name>/{pages,hooks,components}/`.
- [ ] Add the Zod schemas + inferred types in `../api/types/dto.ts` (see the API-layer checklist).
- [ ] Add the endpoint file in `../api/endpoints/` (thin wrappers around `request()`).
- [ ] Implement hooks with `useQuery` / `useMutation`; invalidate query keys in every mutation's `onSuccess`.
- [ ] Build the page to orchestrate hooks and pass data to components; build the components as presentational.
- [ ] Register the route in `../app/routes/router.tsx` (see `../app/CLAUDE.md`). Lazy-load unless the page is on the boot path.
- [ ] Add unit tests for pure helpers and integration tests for the page. See `../test/CLAUDE.md`.
