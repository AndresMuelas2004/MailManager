# General Frontend Layer Rules

This is the top-level `CLAUDE.md` for the **frontend** of the application. It describes the architecture, the tech stack, and the rules that govern every directory under `frontend/`. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the frontend layer from day one.

**Precedence.** In case of conflict between this file and any document further down the repository (sub-layer `CLAUDE.md` files included), the most specific layer rule wins **unless** this file states a stricter constraint, in which case this file takes precedence.

**Immutable.** This file must never be edited. All changes to frontend rules go through a new version of this file.

## 1. Tech Stack

- **React** with **TypeScript** in strict mode (`strict: true`, `noUnusedLocals`, `noUnusedParameters`).
- **Vite** as the build tool and dev server.
- **React Router** for client-side routing.
- **TanStack Query** for server-state and data fetching. This is the only acceptable cache layer.
- **Zod** for runtime validation of every API response and request shape.
- **Tailwind CSS** for styling — utility classes only.
- **Vitest** + **Testing Library** + **MSW** for unit and integration tests.
- **Playwright** for end-to-end tests.
- **Prettier** + **ESLint** + **lint-staged** + pre-commit hooks for formatting and linting.

No Redux, MobX, Zustand or similar global-state library unless a concrete need justifies it. Server state belongs in TanStack Query; UI state belongs in `useState`.

## 2. Package Structure

```
frontend/
├── src/
│   ├── app/            # Application shell: layout, providers, router
│   ├── api/            # HTTP client + endpoints + Zod-validated DTOs
│   ├── features/       # Vertical slices — one domain per subdirectory
│   ├── components/     # Shared UI: common (primitives) + ui (domain-aware)
│   ├── lib/            # Pure utilities, types, generic hooks
│   ├── test/           # Testing infrastructure (MSW, render helpers, setup)
│   ├── styles/         # Global CSS (Tailwind import + minimal resets)
│   └── main.tsx        # Entry point — mounts <Providers /> into root
├── e2e/                # Playwright end-to-end specs (own tsconfig)
└── <configs>           # vite.config.ts, vitest.config.ts, playwright.config.ts, etc.
```

Each subdirectory of `src/` and `e2e/` has its own `CLAUDE.md` with the rules specific to that layer. This file is the summary; those are the authority for their own scope.

## 3. Layer Boundaries (Dependency Graph)

Imports flow in one direction only. Arrows read as "may import from":

```
            app/
             │
             ▼
          features/
         ╱   │   ╲
        ▼    ▼    ▼
 components/  api/  lib/
       │      │
       ▼      ▼
      lib/   zod
```

Explicit rules:
- **`features/<a>/` never imports from `features/<b>/`.** Shared pieces go to `components/`, `lib/`, or `api/`.
- **`api/` never imports from `features/`, `components/`, or `app/`.** It is a near-leaf layer.
- **`lib/` never imports from any other `src/` directory.** It is the leaf.
- **`components/common/` never imports from `components/ui/` or any higher layer.**
- **`components/ui/` never imports from `features/` or `api/endpoints/`.**
- **`app/` never imports feature hooks directly** (pages do that inside the feature).
- **`src/` never imports from `src/test/` or `e2e/`.** Test helpers are scoped to tests.

Refer to each layer's `CLAUDE.md` for the detailed boundaries.

## 4. Styling

Tailwind utility classes only. No CSS modules, no styled-components, no inline `style` objects unless a truly dynamic pixel value requires it. The only CSS file is `styles/globals.css` (Tailwind import + minimal resets). Responsive design uses Tailwind prefixes (`sm:`, `md:`, `lg:`). Dark mode, when present, uses Tailwind's `dark:` prefix.

## 5. State Management

| Kind of state                 | Lives in                                        |
|-------------------------------|-------------------------------------------------|
| Server state (remote data)    | **TanStack Query cache** (`useQuery`/`useMutation`) |
| UI state (local to a component)| `useState` inside the component                 |
| Cross-cutting app state       | React `Context` composed in `app/providers/`    |

Never store server state in `useState` and never turn a TanStack Query cache into a global variable. If UI state must be shared between components, lift it only as far as necessary; reach for `Context` only when deeply nested components need it.

## 6. Error Handling

A single pipeline governs every error surfaced to the user:

```
fetch or schema parse → ApiError / ValidationError (in api/client/errors.ts)
                        │
                        ▼
hook catches → toUiError(err) → UiError { message, code? }
                        │
                        ▼
component renders error.message
```

Rules:
- Every response body from the backend is validated at the API boundary by a Zod schema. Drift between frontend and backend surfaces as `ValidationError`, not as a silent render bug.
- Hooks catch; components display. Components never call `toUiError`, never read raw `Error.message`, never branch on `instanceof ApiError`.
- Network failures distinguish themselves (code `network_error`) so the UI can show a specific message when appropriate.

Full hierarchy and conventions live in `src/api/CLAUDE.md`.

## 7. Naming Conventions

- **Components**: `PascalCase.tsx` — the default export matches the filename.
- **Hooks**: `camelCase.ts` starting with `use` (e.g. `useResourceList.ts`).
- **Endpoint files**: `camelCase.ts` matching the backend resource.
- **Type files**: `camelCase.ts` (e.g. `dto.ts`).
- **Props types**: `Props` for internal types, `<ComponentName>Props` when exported.
- **Constants**: `UPPER_SNAKE_CASE` for true constants.
- **Directories**: lowercase, no separators (`components`, `endpoints`, `providers`).

## 8. Testing

The frontend follows the **Testing Trophy**: static checks (TypeScript + ESLint) as the base, a moderate unit tier, a large integration tier (the sweet spot — MSW intercepts HTTP at the `fetch` boundary while every other layer runs unmocked), and a small E2E tier for golden paths.

- Unit + integration tests: co-located `*.test.ts(x)` next to the file they cover. See `src/test/CLAUDE.md`.
- E2E tests: `e2e/specs/*.spec.ts`, separate runner and config. See `e2e/CLAUDE.md`.

## 9. Formatting, Linting, Commits

- Prettier enforces a single formatting style. Pre-commit hook runs `prettier --write` + `eslint --fix` on staged files via lint-staged.
- TypeScript strict mode, ESLint with React Hooks and React Refresh plugins, and Prettier integration are non-negotiable.
- CI gates on `tsc --noEmit`, `eslint`, `prettier --check`, and the Vitest suite. E2E runs on merges to the main branch.

## 10. Reading Order Before Adding Functionality

When touching the frontend, **read the layer-level `CLAUDE.md` of every directory the change lives in or crosses** before writing code. In practice:

- New or changed API contract → `src/api/CLAUDE.md`.
- New or changed page / hook / feature-local component → `src/features/CLAUDE.md`.
- New shared primitive or widget → `src/components/CLAUDE.md`.
- New global provider, layout, or route → `src/app/CLAUDE.md`.
- New pure helper, type, or generic hook → `src/lib/CLAUDE.md`.
- New tests → `src/test/CLAUDE.md` (and `e2e/CLAUDE.md` if end-to-end).

Skipping this step is the most common source of architectural drift.

## 11. Adding a New Feature — End-to-End Checklist

- [ ] **Read** the layer `CLAUDE.md` files for every affected directory (see §10).
- [ ] **DTOs**: add Zod schemas + inferred types in `src/api/types/dto.ts`.
- [ ] **Endpoints**: thin wrappers around `request()` in `src/api/endpoints/`.
- [ ] **Feature slice**: create `src/features/<name>/{pages,hooks,components}/`.
- [ ] **Hooks**: `useQuery` for reads, `useMutation` with `onSuccess` invalidation for writes; translate errors via `toUiError`.
- [ ] **Pages**: one per route, orchestrate hooks, pass data as props.
- [ ] **Components**: presentational, props-typed, no API calls.
- [ ] **Shared UI promotion**: if a piece is used by ≥2 features, move it to `components/`.
- [ ] **Routing**: register in `src/app/routes/router.tsx`, `React.lazy()` unless boot path.
- [ ] **MSW handlers**: add happy-path handlers for new endpoints in `src/test/msw/handlers.ts`.
- [ ] **Tests**: unit for pure helpers, integration for the page, E2E if the journey is critical.
- [ ] **No forbidden imports**: verify the dependency graph in §3 is respected.

## 12. Anti-Patterns (Do Not Do)

1. Calling `fetch()` outside `src/api/client/http.ts`.
2. Importing from another feature.
3. Hand-writing TypeScript types for DTOs instead of inferring them from a Zod schema.
4. Storing server state in `useState`.
5. Mocking endpoint functions or application hooks inside an integration test — always mock at the MSW (network) boundary.
6. Rendering raw `error.message` from an `Error` or `ApiError` — always go through `UiError`.
7. Declaring routes outside `src/app/routes/router.tsx`.
8. Writing CSS outside Tailwind.
9. Adding a global state management library without a concrete need that TanStack Query plus `Context` cannot cover.
10. Commenting on *what* code does rather than *why* a non-obvious decision was made.
