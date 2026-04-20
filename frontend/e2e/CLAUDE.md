# General End-to-End (E2E) Layer Rules

This is the `CLAUDE.md` for the **end-to-end testing layer** of the frontend. It governs browser-level tests that exercise the compiled application against a real backend. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the E2E layer from day one.

**Precedence.** In case of conflict between this file and any document further down the repository, these rules take precedence.

**Immutable.** This file must never be edited. All changes to E2E-layer rules go through a new version of this file.

## 1. Purpose

This layer owns **browser-level, end-to-end tests**. It validates that the compiled application, the network, the backend, and the database cooperate to deliver user-visible outcomes. It complements — but does not duplicate — the unit and integration tiers documented in `../src/test/CLAUDE.md`.

## 2. Structure

```
e2e/
├── specs/                 # Test files — one file per user journey or flow
├── fixtures/              # Shared test data, auth helpers, setup utilities
├── .auth/                 # Saved authenticated browser state (git-ignored)
├── .artifacts/            # Test output: traces, screenshots, videos (git-ignored)
└── playwright.config.ts   # Runner configuration
```

## 3. Scope

### 3.1 What E2E tests do
- Exercise user journeys that cross at least two pages and depend on the full stack (compiled frontend, real network, real backend).
- Authenticate through the **real** login flow with a seeded test user — never through stubs.
- Assert on what the user sees in the DOM, not on internal implementation details.

### 3.2 What E2E tests do not do
- Duplicate coverage that an integration test already provides. If a bug can be caught with MSW at the integration tier, it belongs there.
- Mock network traffic at the browser level. The app under test is the real build.
- Pretend to be fast. E2E is the slow, high-value tier.

## 4. Spec Rules (`specs/`)

### 4.1 One journey per file
- Each spec file covers one golden path (e.g. "log in and reach the main view", "create and submit a form"). Files stay focused so a failure points clearly at the broken journey.

### 4.2 File naming
- Playwright specs use `*.spec.ts`. The extension is enforced by the runner's glob — do not mix `.test.ts`.

### 4.3 Assertions
- Assert on visible DOM (`expect(locator).toBeVisible()`, `toHaveText()`, `toHaveURL()`) and on side effects observable by a real user.
- Do not assert on computed state, internal variables, or framework internals.

### 4.4 Timing
- Prefer Playwright's auto-waiting locators. Avoid arbitrary `page.waitForTimeout(ms)`. When a test needs a specific condition, use an explicit `expect(...).toPass()` or `page.waitForURL(...)`.

## 5. Fixtures and Authenticated State (`fixtures/`, `.auth/`)

### 5.1 Seeded test users
- Real authenticated journeys use pre-seeded test identities provisioned by the backend. Identities and their credentials are the responsibility of the backend's E2E layer; the frontend E2E layer **consumes** them.

### 5.2 Storage state reuse
- After authenticating once in a global setup, the resulting browser storage state is written to `.auth/<name>.json` and reused by subsequent specs via `test.use({ storageState: ... })`. This keeps the suite fast and deterministic.

### 5.3 Git hygiene
- `.auth/` and `.artifacts/` are git-ignored at the frontend root. They contain session material and run output respectively.

## 6. Reset Contract

### 6.1 Per-spec isolation
- No mutable state may leak between specs. Two strategies are acceptable:
  - The seeded test identity is reset via a test-only endpoint invoked in `beforeEach`.
  - Each spec operates within its own scoped resource (e.g. a freshly created record with a unique id) and cleans up in `afterEach`.

### 6.2 No retry as cover
- `retries` in the Playwright config is a diagnostic tool, not a substitute for fixing a flaky test. If a spec needs retries to pass, triage the root cause.

## 7. Must / Must Not

### Must
- Run against a real, running backend (local or deterministic staging).
- Authenticate through the production login flow.
- Produce artifacts (traces, screenshots, video) on failure for debugging.

### Must Not
- Mock HTTP, cookies, or storage at the browser level.
- Share state across specs.
- Reproduce coverage achievable at the integration tier.
- Import code from `src/` — the suite has its own `tsconfig` and exercises the application through the running browser only.

## 8. Import Boundaries

| Allowed imports                                                           | Forbidden imports            |
|---------------------------------------------------------------------------|------------------------------|
| `@playwright/test`, files inside `e2e/` (fixtures, helpers), env config   | Any path starting with `src/` |

## 9. Commands and CI

- `npm run e2e` — runs the Playwright suite against the configured base URL.
- `npm run e2e:ui` — interactive runner for local debugging.
- CI invokes `npm run e2e` on merges into the main branch, not on every push. E2E flakiness must never gate a small PR.

## 10. Relationship to Other Testing Tiers

The global philosophy (Testing Trophy, MSW boundary, co-location of Vitest tests) is documented in `../src/test/CLAUDE.md`. This file governs only the E2E specifics. When a change affects both tiers — for instance, adding a new critical journey — read both files before writing tests.
