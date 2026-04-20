# General Application Shell Layer Rules

This is the `CLAUDE.md` for the **application shell** — the layer that boots the frontend, composes the global providers, and maps URLs to feature pages. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the application shell from day one.

**Precedence.** In case of conflict between this file and any document further down the repository, these rules take precedence.

**Immutable.** This file must never be edited. All changes to shell-layer rules go through a new version of this file.

## 1. Purpose

The shell is the "skeleton" of the application. It **boots** the app, **wraps** it in global providers, and **routes** URLs to feature pages. It owns no business logic and no visual domain concerns beyond the structural layouts every route shares.

## 2. Structure

```
app/
├── layout/      # Layout components that render an <Outlet />
├── providers/   # React context providers composed into one shell
└── routes/      # Router configuration — one router.tsx
```

## 3. Router Rules (`routes/`)

### 3.1 Single source of truth
- All routes are declared in **one** `router.tsx` using the framework's router factory. No feature declares its own routes.

### 3.2 Point at feature pages
- Each route's element references a page component exported by a feature (`features/<x>/pages/...`). The shell never defines page components itself.

### 3.3 Lazy loading
- Non-boot-path pages use `React.lazy()` (or the framework's equivalent lazy loader) to split the bundle. Boot-path pages — those reached before the router has resolved a feature route — may be eager.

### 3.4 Route paths
- Flat and descriptive. Use resource-style paths (`/resources`, `/resources/:id`). Avoid deep nesting beyond two levels.

### 3.5 No routing logic in features
- Features export page components only. They never import the router, never build paths, and never call navigation helpers that bypass the router.

## 4. Provider Rules (`providers/`)

### 4.1 Composition in one file
- All global context providers are composed inside `Providers.tsx` (or an equivalent single entry point). Individual providers are defined in sibling files and only consumed by `Providers.tsx`.

### 4.2 Cross-cutting only
- A context lives here only if it is genuinely cross-cutting: authenticated identity, data-fetching cache, theme, locale. Feature-scoped state does not belong in a global context.

### 4.3 Singleton instances
- Long-lived instances (for example, a data-fetching client) are created once with `useState(() => createClient())` inside the provider to avoid re-instantiation on re-render.

### 4.4 Devtools
- Optional developer overlays (devtools panels, mock-switchers) mount only under `import.meta.env.DEV` (or the equivalent dev-mode guard).

## 5. Layout Rules (`layout/`)

### 5.1 Render an `<Outlet />`
- Layouts are React components that declare the shell structure (chrome, navigation, suspense boundaries) and delegate their content region to the router's `<Outlet />`.

### 5.2 No domain logic
- A layout does not fetch data, does not know about specific features, and does not orchestrate hooks that depend on the domain. If a layout needs contextual information (e.g. the current resource id), it reads it from the router (URL params) or from a global context.

## 6. Entry Point

The `main.tsx` (or equivalent) file mounts `<Providers />` into the root DOM node and does nothing else. No fetching, no routing, no conditional logic.

## 7. Must / Must Not

### Must
- Keep routing, layout, and providers strictly structural.
- Lazy-load every non-boot page.
- Compose all providers in a single entry.

### Must Not
- Import feature hooks directly from the shell (pages do that inside the feature, not here).
- Declare routes outside `routes/`.
- Hold domain state in a global context. Domain state belongs in `features/` or in the data-fetching cache.

## 8. Import Boundaries

| From `app/`    | May import from                                                    | May not import from                                           |
|----------------|--------------------------------------------------------------------|---------------------------------------------------------------|
| `layout/`      | `components/`, `lib/`                                              | `api/`, `features/*/hooks` or `features/*/components`         |
| `providers/`   | `api/client/errors`, `lib/`, pinned third-party providers          | `features/`, `components/ui/`                                 |
| `routes/`      | `features/*/pages`, `layout/`                                      | `features/*/hooks`, `features/*/components`                   |

See `../features/CLAUDE.md` for the pages the router points at and `../api/CLAUDE.md` for the error types providers may import.

## 9. Adding Something to the Shell — Checklist

- [ ] If it is a new route: add it in `routes/router.tsx`, referencing a page from `features/<x>/pages/`. Prefer `React.lazy()`.
- [ ] If it is a new global provider: add its file under `providers/` and compose it inside `Providers.tsx`. Justify why it is cross-cutting.
- [ ] If it is a new layout: place it under `layout/`, render an `<Outlet />`, avoid domain logic.
- [ ] Verify no forbidden import crossed a boundary (see the table above).
