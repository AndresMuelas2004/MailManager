# General Utility Layer Rules

This is the `CLAUDE.md` for the **utility layer** of the frontend. It hosts the pure, reusable building blocks that every higher layer is allowed to consume. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the utility layer from day one.

**Precedence.** In case of conflict between this file and any document further down the repository, these rules take precedence.

**Immutable.** This file must never be edited. All changes to utility-layer rules go through a new version of this file.

## 1. Purpose

The utility layer holds **pure, cross-feature, framework-light** helpers. Anything that two or more features would otherwise duplicate lives here. Anything tied to a single feature stays inside that feature.

## 2. Structure

```
lib/
├── types.ts         # Cross-feature domain-agnostic types
├── formatters.ts    # Pure formatting functions (dates, numbers, strings)
├── <registry>.ts    # Optional config registries (enum maps, presets)
└── hooks/           # Generic React hooks with no domain knowledge
```

The list is open-ended, but every file must satisfy the rules below. Adding a new sub-file or sub-directory inside `lib/` is encouraged when a genuinely reusable helper emerges.

## 3. Rules

### 3.1 Purity
- Functions must be deterministic and free of side effects whenever possible. Input in, output out.
- Impure helpers (those that read `Date.now()`, the DOM, or external state) are allowed only when necessary, documented with a one-line comment, and free of business semantics.

### 3.2 Scope
- Every export must be meaningful in at least **two** places in the codebase. If only one feature uses it, move it into that feature.
- No dependencies on the domain of the application. `lib/` must not know about users, sessions, resources, pages, or any concept that belongs in a feature or in `api/`.

### 3.3 Hooks in `lib/hooks/`
- Must be generic: their type parameters and behavior apply to many shapes of data, not to a specific entity.
- Must not call endpoints. Data fetching belongs in feature hooks, not here.
- Naming: `useXxx.ts` exporting `useXxx` as default (or named — see naming conventions in the frontend root `CLAUDE.md`).

## 4. Must / Must Not

### Must
- Stay dependency-free from the rest of `src/`. Only React, pinned third-party packages (TypeScript-safe), and other files inside `lib/`.
- Provide explicit TypeScript types for every public export.

### Must Not
- Import from `api/`, `features/`, `components/`, `app/` or `test/`. Any such import is an architectural violation.
- Perform JSX rendering (besides the generic hooks that return state/callbacks).
- Hold application-wide mutable state. Generic hooks may hold *local* state scoped to the caller.

## 5. Import Boundaries

| Allowed imports                                                                             | Forbidden imports                                                  |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| React (for hooks), pinned third-party deps, other files inside `lib/`                       | Any other directory under `src/` (`api`, `features`, `components`, `app`, `test`) |

## 6. Adding Something to `lib/` — Checklist

- [ ] Confirm the helper is genuinely reusable in two or more sites. If not, put it in the owning feature.
- [ ] Strip any dependency on the application domain. Make the API generic.
- [ ] Write a unit test co-located with the file (`*.test.ts`). See `src/test/CLAUDE.md`.
- [ ] Export only what other layers need — keep internal helpers module-private.
- [ ] Do not introduce imports from other `src/` directories.
