# General Frontend Layer Rules

This is the `CLAUDE.md` for the **frontend client application** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the frontend layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.
**Immutable.** This file must never be edited. All project-specific changes go in the `*_guide.md` file referenced at the end of this document.

## 1. Tech Stack

The frontend is built on:

- **React** (UI library) with **TypeScript** in strict mode (`strict: true`, `noUnusedLocals`, `noUnusedParameters`).
- **Vite** (build tool and dev server).
- **React Router** (client-side routing via `createBrowserRouter`).
- **Tailwind CSS** (utility-first styling — the only styling approach allowed).
- **No state management library** — React state (`useState`, `useReducer`) and context (`useContext`) only.
- **No data fetching library** — raw `fetch()` wrapped in a custom HTTP client.

## 2. Package Structure

```
src/
├── api/                    # HTTP client layer
│   ├── client/             # Base HTTP client + error handling
│   ├── endpoints/          # One file per backend resource
│   └── types/              # TypeScript DTOs matching backend schemas
├── app/                    # Application shell
│   ├── layout/             # Layout components (root layout with Outlet)
│   ├── providers/          # Context providers wrapper
│   └── routes/             # Router configuration
├── components/             # Shared reusable UI components
│   ├── common/             # Generic, domain-agnostic primitives (Button, Modal, Input)
│   └── ui/                 # Domain-aware shared widgets (Sidebar, DataRow)
├── features/               # Vertical slices by domain
│   └── <feature>/
│       ├── components/     # Feature-specific components
│       ├── hooks/          # Feature-specific hooks
│       └── pages/          # Feature page components (routed)
├── lib/                    # Shared utilities (formatters, constants, helpers)
├── styles/                 # Global CSS (Tailwind import + resets only)
├── main.tsx                # Entry point (renders Providers into root)
└── vite-env.d.ts           # Vite type declarations
```

## 3. Layer Boundaries

Import rules enforce a strict dependency direction. Violations are architectural errors.

### Allowed imports (direction: consumer → dependency)

- **`features/`** → `api/endpoints/`, `api/types/`, `components/`, `lib/`
- **`components/ui/`** → `components/common/`, `lib/`
- **`components/common/`** → `lib/` only (no domain knowledge)
- **`app/routes/`** → `features/*/pages/`, `app/layout/`
- **`app/providers/`** → `app/routes/`
- **`api/endpoints/`** → `api/client/`, `api/types/`
- **`api/client/`** → no internal imports (leaf module — uses only browser `fetch`)
- **`lib/`** → no internal imports (leaf module)

### Forbidden imports

- **No feature-to-feature imports.** A feature module must never import from another feature module. Shared logic goes in `components/`, `lib/`, or `api/`.
- **No reverse imports.** `api/` must never import from `features/`, `components/`, or `app/`. `lib/` must never import from any other `src/` directory.
- **No circular imports.** If two modules need each other, extract the shared dependency into `lib/` or a parent module.

## 4. Feature Module Rules

Each feature directory is a self-contained vertical slice.

### Internal structure

Every feature has three subdirectories — no more, no less:

- **`pages/`** — route-level components. Each page corresponds to one route. Pages compose feature-specific components and invoke feature-specific hooks.
- **`hooks/`** — custom React hooks that encapsulate data fetching, mutation logic, and local state management. Hooks call endpoint functions from `api/endpoints/` and convert `ApiError` into `UiError` for the UI.
- **`components/`** — presentational and interactive components used only within this feature. They receive data via props — never call API endpoints directly.

### Rules

1. **Pages orchestrate; components render.** Pages wire hooks to components. Components are pure renderers that receive data and callbacks via props.
2. **Hooks own side effects.** All `fetch` calls, error handling, and loading states live in hooks — never in components or pages directly.
3. **No cross-feature imports.** If two features need the same component, move it to `components/common/` or `components/ui/`. If they need the same hook logic, extract the shared part into a hook in `lib/` or into a new endpoint in `api/`.
4. **One page per route.** Each file in `pages/` maps to exactly one route in the router configuration.

## 5. Component Rules

### Classification

- **`components/common/`** — generic, domain-agnostic primitives. These components know nothing about the application domain. Examples: Button, Modal, Input, Spinner, Badge. They accept only generic props (label, onClick, className, children).
- **`components/ui/`** — domain-aware shared widgets used across multiple features. They may import from `components/common/` and `lib/` but never from `features/` or `api/endpoints/`. They receive domain data via props — never fetch it themselves.
- **`features/*/components/`** — feature-specific components. Used only within the owning feature. May import from `components/common/`, `components/ui/`, and `lib/`.

### Rules

1. **One component per file.** The file name matches the component name in PascalCase (e.g., `EmailList.tsx` exports `EmailList`).
2. **Props over internal state.** Components receive data through props. Internal state is limited to UI concerns (open/closed, selected index, input value).
3. **No direct API calls in components.** Components never import from `api/`. Data fetching is the responsibility of hooks, which are called in pages or parent components.
4. **Explicit prop types.** Every component defines a `Props` type (or `<ComponentName>Props` for exported types). No `any` — use `unknown` and narrow.
5. **Composition over configuration.** Prefer composing small components over building large components with many conditional props.

## 6. API Client Rules

The `api/` directory is the frontend's interface to the backend. It mirrors the backend's HTTP surface.

### Structure

- **`api/client/http.ts`** — the single HTTP client. Wraps `fetch()` with base URL resolution, JSON serialization, and error conversion. Exports a `request<T>()` generic function.
- **`api/client/errors.ts`** — defines `ApiError` (class), `UiError` (plain type), and helper functions: `toApiError()`, `toNetworkError()`, `toUiError()`, `isApiError()`.
- **`api/endpoints/*.ts`** — one file per backend resource. Each file exports thin async functions that call `request<T>()` and return typed promises. No business logic — just HTTP method, path, and payload.
- **`api/types/dto.ts`** — TypeScript types that mirror backend response/request schemas exactly. Field names use the backend's naming convention (snake_case).

### Rules

1. **DTOs mirror backend schemas.** Every type in `dto.ts` must match the corresponding backend schema field-for-field, including nullability. When the backend schema changes, `dto.ts` changes to match.
2. **One file per resource.** Each endpoint file groups all operations for one backend resource (CRUD + actions). Do not mix resources in a single file.
3. **Endpoint functions are thin wrappers.** Each function calls `request<T>()` with the correct path, method, and body. No error handling, no retry logic, no caching — just the HTTP call.
4. **All errors flow through `ApiError`.** The HTTP client converts non-ok responses to `ApiError` instances and network failures to `ApiError` with code `"network_error"`. Consumers catch `ApiError` — never raw `fetch` errors.
5. **No direct `fetch()` calls outside `http.ts`.** All HTTP communication goes through the `request<T>()` function.

### Adding a new endpoint

- [ ] Add the response/request types to `api/types/dto.ts`.
- [ ] Create or update the endpoint file in `api/endpoints/`.
- [ ] Use `request<T>()` with the correct generic type parameter.
- [ ] Import the DTO types with `import type` to ensure they are erased at runtime.

## 7. Routing Rules

Routing is configured centrally in `app/routes/` using `createBrowserRouter`.

### Rules

1. **Single router definition.** All routes are declared in one file (`router.tsx`). No route definitions scattered across feature modules.
2. **Routes point to feature pages.** Each route's `element` (or `lazy` loader) references a page component from `features/*/pages/`.
3. **Layout nesting via `Outlet`.** The root layout (`app/layout/`) renders an `<Outlet />`. Child routes render inside this outlet.
4. **Lazy loading for feature pages.** Non-critical routes use React Router's `lazy()` to code-split feature pages. The root layout and login page may be eagerly loaded.
5. **Route paths are flat and descriptive.** Use REST-style paths (e.g., `/resources`, `/resources/:id`). Avoid deeply nested route trees beyond two levels.
6. **No routing logic in features.** Features do not define their own routes — they export page components that the router references.

## 8. State Management

This application uses React's built-in state primitives exclusively — no external state management library.

### Rules

1. **Co-locate state.** Keep state as close to where it is used as possible. Start with `useState` in the component that needs it.
2. **Lift only when necessary.** Move state to a parent component only when siblings need to share it. Move to context only when deeply nested components need it.
3. **Context for cross-cutting concerns only.** Use `React.createContext` for truly global state: authenticated user, theme, locale. Do not use context as a general-purpose store.
4. **Providers wrap the app shell.** All context providers are composed in `app/providers/Providers.tsx`. Individual providers are defined in their own files within `app/providers/`.
5. **No prop drilling beyond two levels.** If a prop must pass through more than two intermediate components that do not use it, introduce a context or restructure the component tree.
6. **Derived state over synchronized state.** Compute values from existing state instead of storing redundant copies. Use `useMemo` for expensive derivations.

## 9. Error Handling

All API errors are caught in hooks, converted to user-friendly messages, and surfaced in the UI. Errors must never crash the application silently.

### The pattern

```typescript
import { toUiError } from "../api/client/errors";
import type { UiError } from "../api/client/errors";

const [error, setError] = useState<UiError | null>(null);

async function handleAction() {
  setError(null);
  try {
    const result = await endpointFunction(...);
    // handle success
  } catch (err) {
    setError(toUiError(err));
  }
}
```

### Rules

1. **Hooks catch, components display.** Hooks call `toUiError()` on any caught error and expose the `UiError` object via their return value. Components render the error message — they never catch errors themselves.
2. **Clear errors before retrying.** Every action that can fail resets the error state to `null` before the `try` block.
3. **No raw error objects in UI.** Components never render `error.message` from a raw `Error` or `ApiError`. Always use the `UiError` type, which guarantees a user-safe `message` string.
4. **Loading and error states are co-located.** Hooks that fetch data return `{ data, error, loading }` — all three states managed together.
5. **Network errors are distinct from API errors.** The UI may show different messages for "server returned an error" (`ApiError` with a status) versus "could not reach the server" (`ApiError` with code `"network_error"`).

## 10. Styling Rules

All styling uses Tailwind CSS utility classes. No other styling approach is permitted.

### Rules

1. **Tailwind utility classes only.** No CSS modules, no styled-components, no inline `style` objects, no `<style>` blocks. The only CSS file is `styles/globals.css`, which contains the Tailwind import and minimal resets.
2. **No custom CSS classes.** Do not create custom class names in CSS files. If a utility pattern repeats across many components, extract a shared component — not a CSS class.
3. **Responsive design via Tailwind breakpoints.** Use Tailwind's responsive prefixes (`sm:`, `md:`, `lg:`) directly in JSX. No media queries in CSS files.
4. **Consistent spacing and sizing.** Use Tailwind's spacing scale (`p-4`, `gap-2`, `w-full`) — avoid arbitrary values (`p-[13px]`) unless the design requires an exact pixel value not in the scale.
5. **Dark mode via Tailwind.** If dark mode is supported, use the `dark:` prefix. Do not implement dark mode via JavaScript class toggling or CSS variables outside Tailwind's system.

## 11. Naming Conventions

### Files

- **Components**: `PascalCase.tsx` — the file name matches the default export (e.g., `EmailList.tsx` exports `EmailList`).
- **Hooks**: `camelCase.ts` starting with `use` (e.g., `useMailboxes.ts` exports `useMailboxes`).
- **Endpoint files**: `camelCase.ts` matching the resource name (e.g., `mailboxes.ts`, `auth.ts`).
- **Utility files**: `camelCase.ts` (e.g., `formatters.ts`, `constants.ts`).
- **Type files**: `camelCase.ts` (e.g., `dto.ts`).

### Code

- **Components**: `PascalCase` (e.g., `AppShell`, `LoginPage`).
- **Hooks**: `camelCase` starting with `use` (e.g., `useAuth`, `useEmails`).
- **Functions**: `camelCase` (e.g., `listMailboxes`, `toUiError`).
- **Types/Interfaces**: `PascalCase` (e.g., `MailboxOut`, `UiError`, `RequestOptions`).
- **Constants**: `UPPER_SNAKE_CASE` for true constants (e.g., `DEFAULT_BASE_URL`), `camelCase` for configured values.
- **Props types**: `Props` for internal types, `<ComponentName>Props` when exported.

### Directories

- All directory names are lowercase with no separators (e.g., `components`, `endpoints`, `providers`).
- Feature directories use lowercase plural nouns (e.g., `emails`, `accounts`, `auth`).

## 12. Project-Specific Guide

This file covers the general, transferable rules for the frontend client application layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`frontend_guide.md`](frontend_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide frontend_guide.md.
