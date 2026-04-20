# General Shared UI Layer Rules

This is the `CLAUDE.md` for the **shared UI layer** — the two-tier library of React components that are reused across features and the application shell. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the shared UI layer from day one.

**Precedence.** In case of conflict between this file and any document further down the repository, these rules take precedence.

**Immutable.** This file must never be edited. All changes to shared-UI rules go through a new version of this file.

## 1. Purpose

Components used by more than one feature, or by the application shell, live here. Components used by a single feature live inside that feature's own `components/` directory — not here.

## 2. Two Tiers

The shared UI is split in two strict tiers by whether the component understands the application domain.

```
components/
├── common/   # Domain-agnostic primitives (Button, Modal, Input, Spinner)
└── ui/       # Domain-aware widgets that receive data by props
```

### 2.1 `common/` — primitives
- Know nothing about the application. Could live in any React project unchanged.
- Accept only generic props (`label`, `onClick`, `children`, `className`, etc.).
- May import from `lib/` only.
- Examples of what belongs here: buttons, modals, inputs, spinners, badges.

### 2.2 `ui/` — domain-aware widgets
- Are aware of the application's domain vocabulary (e.g. they know there is a concept of "account" or "resource") because multiple features share the same visual pattern.
- Receive every piece of domain data through **props** from the page that renders them. They never fetch data, never open contexts, never call endpoints.
- May import from `components/common/` and `lib/`. Must not import from `features/`, `api/`, or `app/`.

## 3. Component Rules (apply to both tiers)

### 3.1 One file per component
- File name matches the component name in `PascalCase.tsx`. The default export is that component.

### 3.2 Props over internal state
- Data flows in through props. Internal `useState` is limited to UI concerns (open/closed, hover, input draft, selected index). Any state that represents domain data is lifted out.

### 3.3 Explicit typed props
- Every component declares a `Props` type (or `<ComponentName>Props` when exported). No `any`; prefer `unknown` and narrow at the boundary.

### 3.4 Composition over configuration
- Prefer composing small components over a single component with many conditional props. A widget with ten `if`s is a signal to split.

### 3.5 No side effects on the global app
- Components may hold local state and call callbacks from props; they may not mutate global state, read cookies, or perform navigation directly. Navigation helpers (from the router) come through the page or the shell.

### 3.6 Styling
- Tailwind utility classes only. See the frontend-root `CLAUDE.md` for the styling policy.

### 3.7 Safe rendering of untrusted content
- Any string coming from the backend, the URL, or user input is rendered as **text** by default — React escapes it automatically via JSX interpolation. Do not circumvent that default.
- `dangerouslySetInnerHTML` is prohibited unless the input has been passed through a dedicated sanitisation pipeline, and that pipeline is identified at the call site. "The backend already sanitised it" is not sufficient justification — the trust boundary ends at the layer that finally renders HTML.
- URLs injected into `href`, `src`, `formAction`, or any equivalent attribute must be validated against an allowed-protocol list (typically `http`, `https`, `mailto`). Never interpolate an unchecked URL into a link that could resolve to `javascript:…` or `data:text/html,…`.

## 4. Must / Must Not

### Must
- Keep `common/` free of any import path that starts with `../features/`, `../api/`, or `../app/`.
- Keep `ui/` free of any import from `../features/` or `../api/endpoints/`.

### Must Not
- Issue HTTP calls. Data always arrives as props.
- Hold state that represents truth about the application (the server state). Server state lives in the feature hooks; UI here only reads it via props.
- Cross the tier boundary upward: `common/` must not import from `ui/`.
- Pass unsanitised content to `dangerouslySetInnerHTML` (see §3.7).
- Render a URL from user or backend input into `href`/`src` without validating its protocol (see §3.7).

## 5. Import Boundaries

| Directory              | May import from                            | May not import from                     |
|------------------------|--------------------------------------------|-----------------------------------------|
| `components/common/`   | `lib/`                                     | `ui/`, `features/`, `api/`, `app/`      |
| `components/ui/`       | `components/common/`, `lib/`               | `features/`, `api/endpoints/`, `app/`   |

See `../lib/CLAUDE.md` for the utility layer this tier depends on.

## 6. Placement Decision — Where Does a New Component Go?

- Used inside one feature only → `features/<feature>/components/`. Not here.
- Used across two or more features or by the shell, with zero domain knowledge → `components/common/`.
- Used across two or more features or by the shell, with domain knowledge in its API → `components/ui/`.
- Borderline case (e.g. a button that only exists to compose a domain-specific widget) → default to the feature; promote to `common/`/`ui/` only on the second consumer.

## 7. Adding a New Shared Component — Checklist

- [ ] Decide the tier (`common/` vs `ui/`) from the criteria above.
- [ ] Place the file as `PascalCase.tsx` with the matching default export.
- [ ] Define `Props` explicitly; forbid `any`.
- [ ] Ensure no forbidden imports (see the boundaries table).
- [ ] Add a co-located test `PascalCase.test.tsx` when the component has interactive behavior. See `../test/CLAUDE.md`.
