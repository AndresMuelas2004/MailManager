# General Frontend Testing Layer Rules

This is the `CLAUDE.md` for the **frontend testing convention**. It serves as the general architectural reference for the testing layer, describing which test types exist, what they cover, what they mock, where they live, and in what proportion they should be written. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the frontend testing convention from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.
**Immutable.** This file must never be edited. All project-specific changes go in the `*_guide.md` file referenced at the end of this document.

## 1. Testing Shape — the Testing Trophy

The frontend does **not** follow the backend's classic test pyramid (wide unit base, thin E2E tip). It follows the **Testing Trophy** (Kent C. Dodds), which reflects where real bugs live in a React application:

```
         ╱ E2E ╲              ← few, critical flows only
       ╱─────────╲
     ╱ INTEGRATION ╲           ← the majority — sweet spot
   ╱───────────────╲
  ╱      UNIT        ╲         ← moderate, pure logic only
 ╱─────────────────╲
╱  STATIC (TS + ESLint) ╲      ← base, already free
─────────────────────────
```

**Rationale.** In frontend, bugs rarely hide inside a single pure function. They hide at the seams between pages, hooks, components, and the API layer. Integration tests that exercise a full feature slice with HTTP intercepted at the network boundary catch those bugs without the brittleness and cost of E2E. Unit tests cover pure logic cheaply; integration tests cover real behavior; E2E tests cover the few golden paths that must survive an end-to-end deploy.

## 2. Test Categories

Three categories, each with a distinct scope, tooling, and location strategy.

### 2.1 Unit tests

- **Scope.** Isolated, pure logic. No DOM rendering beyond `renderHook`, no HTTP, no router, no context.
- **What they test.** Pure functions, pure hooks (hooks with no side effects), error translators, reducers, formatters, constants/maps.
- **What they mock.** Nothing. If a unit test needs a mock to run, the code under test belongs in the integration layer instead.
- **What they verify (really).** Input → output purity. Branch coverage of decision logic. Nothing else.
- **Tools.** Vitest as the runner. `@testing-library/react` only for `renderHook` on pure hooks.
- **Expected volume.** Moderate. Small-to-medium apps typically land in the range of 30–80 unit tests.

### 2.2 Integration tests (component tests)

- **Scope.** Render a full page or feature slice inside the same providers used in production (router, query client, auth context). Simulate the user with `user-event`. Intercept HTTP at the network boundary — nothing else is mocked.
- **What they test.** That a page, when the user clicks X or submits Y, calls the right endpoint, reflects loading/error/success states correctly, and navigates as expected.
- **What they mock.** Only HTTP responses, via MSW (Mock Service Worker). Browser APIs that jsdom cannot implement (`IntersectionObserver`, `matchMedia`) are polyfilled in the shared setup file — not mocked per test.
- **What they verify (really).** Full internal integration: hooks, components, API client (`request<T>()`), endpoint functions, error translation, schema validation, and cache behavior all execute unmocked. Only the network response is synthesized. This is what makes integration tests the sweet spot of the Trophy.
- **Tools.** Vitest + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` + MSW.
- **Expected volume.** The largest group. Small-to-medium apps typically land in the range of 50–200 integration tests — roughly one per page plus one per meaningful user interaction within that page.

### 2.3 E2E tests

- **Scope.** The compiled application running in a real browser against a real backend (or a deterministic staging backend with pre-seeded test accounts). Authentication goes through the real login flow with a test user.
- **What they test.** Golden-path user journeys that cross system boundaries: login → navigate → perform a multi-step action → verify outcome in a different view. Flows that only an end-to-end stack can guarantee.
- **What they mock.** Nothing at the browser level. The backend may be configured with test accounts or a test database, but the application under test is the real production build.
- **What they verify (really).** That the deployed app, the network, the backend, and the database all cooperate to deliver the user outcome. They catch build, routing, cookie, and environment bugs that integration tests cannot see.
- **Tools.** Playwright (Chromium by default). Multi-browser matrices only for flows where cross-browser differences truly matter.
- **Expected volume.** Small. Typically 5–15 specs for the entire application. Cover the 3–7 golden paths; resist the urge to duplicate integration tests here. If a bug can be caught at the integration layer, it belongs there — E2E time and flakiness are expensive.

## 3. Locations — Co-located vs Separated

| Test type   | Location strategy                              | Example path                                       |
|-------------|------------------------------------------------|----------------------------------------------------|
| Unit        | **Co-located** with the source file            | `src/lib/formatters.test.ts`                       |
| Integration | **Co-located** with the page/component         | `src/features/emails/pages/InboxPage.test.tsx`     |
| E2E         | **Separate** top-level directory               | `e2e/specs/login.spec.ts`                          |
| Shared test helpers (not tests)   | **Central directory**            | `src/test/setup.ts`, `src/test/msw/handlers.ts`    |

### Rules

1. **Co-location for Vitest tests.** Unit and integration tests live next to the file they test. Moving, renaming, or deleting source code moves its tests automatically — refactors stay safe.
2. **E2E is always separated.** Playwright has its own runner, its own `tsconfig`, and does not import from `src/` directly. All E2E specs live under `e2e/` at the frontend root, with their own `playwright.config.ts`.
3. **Shared test infrastructure lives in `src/test/`.** MSW handlers, Vitest setup files, test factories, custom render helpers. Production code in `src/` must never import from `src/test/`.
4. **File naming.** Vitest specs use `*.test.ts` or `*.test.tsx`. Playwright specs use `*.spec.ts`. The extension choice is enforced by each runner's glob — do not mix.

## 4. The MSW Boundary

Mock Service Worker intercepts requests at the `fetch` layer, not at the endpoint-function layer. This boundary is non-negotiable and is the reason integration tests are trustworthy:

- The real `request<T>()` runs.
- The real endpoint functions run.
- The real error translation (`toUiError`, schema validation) runs.
- The real data-fetching/cache layer (e.g. React Query) runs.
- Only the HTTP response is synthesized.

### Rules

1. **Handlers live in `src/test/msw/`.** One file per backend resource, mirroring `src/api/endpoints/`.
2. **Never mock endpoint functions directly.** Do not `vi.mock("../../api/endpoints/<resource>")`. Mocking at the endpoint level bypasses the entire API client layer — one of the most common sources of real bugs — and defeats the purpose of integration tests.
3. **Never mock `fetch` manually.** Use MSW. Hand-rolled `fetch` mocks drift, leak between tests, and do not exercise the request/response contract.
4. **Default to success; override for failure.** The shared MSW server returns happy-path responses for every handler. Individual tests install `server.use(...)` inline to simulate errors, timeouts, or edge cases.
5. **Reset between tests.** The shared setup calls `server.resetHandlers()` in `afterEach` so one test's overrides never leak into another.

## 5. Must / Must Not — per test type

### Unit tests
- **Must** take plain inputs, return plain outputs, and assert on them. Fast (< 10 ms each).
- **Must not** render the full DOM, call `fetch`, import feature pages, or touch router/context.

### Integration tests
- **Must** render the component under test inside the same providers used in production, simulate interactions via `user-event`, and use MSW for HTTP.
- **Must not** mock endpoint functions, mock application hooks, or assert on internal implementation details (state variable names, private helpers). Assert on what the user sees.

### E2E tests
- **Must** authenticate via the real login flow with a pre-seeded test user, exercise a journey that crosses at least two pages, and assert on visible outcomes in the DOM.
- **Must not** duplicate coverage that integration tests already provide. E2E time is expensive; keep the suite small and high-value.

## 6. State Required Before Each Test

| Type        | Reset between tests                                                                                     |
|-------------|---------------------------------------------------------------------------------------------------------|
| Unit        | Nothing — stateless by design.                                                                          |
| Integration | MSW handlers reset to defaults; query cache cleared; router reset. Automated in `src/test/setup.ts`.    |
| E2E         | Test user's state reset via seeded fixtures or a test-only reset endpoint. Never share state across specs. |

## 7. CI and Commands

### Rules

1. **Three distinct commands.**
   - `npm test` — Vitest, all unit + integration, watch mode during dev.
   - `npm run test:unit` — Vitest with a glob that excludes integration specs (CI gate for fast feedback).
   - `npm run e2e` — Playwright against a real backend.
2. **`npm test` runs on every commit and every PR.** `npm run e2e` runs on CI for merges into the main branch, not on every push. E2E flakiness must never block small PRs.
3. **Static checks run first.** `tsc --noEmit` and `eslint` execute before any test in CI. A type or lint error fails the pipeline before any test runs.

## 8. Adding Tests for a New Feature — Checklist

When adding a new feature, write tests in this order — do not start the next layer until the previous one is green:

- [ ] A unit test for every new pure function or isolated hook in `lib/` or `features/<x>/hooks/`.
- [ ] An integration test for the new page and for every meaningful user interaction (click, form submit, error case, optimistic update).
- [ ] If the feature crosses pages and matters for the user's journey, add a single E2E spec for the golden path. Do not add E2E for every permutation.

## 9. Anti-patterns (Do Not Do)

1. **Testing implementation details.** Do not assert on state variable names, internal function names, or the shape of props passed between components the user does not see. Assert on what the user observes.
2. **Over-mocking.** Mocking application hooks, components, or endpoint functions inside an integration test reduces it to a unit test with extra noise. Keep the mock boundary at MSW.
3. **Snapshot-only tests.** A `toMatchSnapshot` is never an integration test on its own. Use snapshots sparingly and only for stable structural output (e.g. a small presentational component's markup).
4. **Shared mutable state across tests.** Every test is independent. If two tests share a fixture, that fixture is built fresh per test — never mutated in place.
5. **Coverage as a goal.** Coverage is a diagnostic, not a target. A line covered by a meaningless assertion is worse than an uncovered line, because it hides a gap behind a green bar.

## 10. Project-Specific Guide

This file covers the general, transferable rules for the frontend testing convention. For project-specific details — concrete tool versions, test-account fixtures, CI pipeline wiring, critical flow list for E2E — consult the project's testing guide file (e.g. `testing_guide.md`). The guide complements these rules but never contradicts them. In case of conflict, this file has absolute precedence.
