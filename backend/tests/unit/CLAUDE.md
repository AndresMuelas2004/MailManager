# General Unit Test Rules

  This is the `CLAUDE.md` for the **unit test** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model,
  its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

  **Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

  **Reusable.** Copy this file into a new project to establish the unit test layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

  **Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

  **Immutable.** This file must never be edited. All project-specific changes go in the `*_guide.md` file referenced at the end of this document.

  ## 1. Scope

  Unit tests validate individual modules in isolation. They do **not** require:

  - External services (databases, APIs, message queues)
  - Network access
  - Browser interaction
  - File system side effects

  ## 2. Principles

  - **Test one behavior per case.** Each test validates a single logical assertion or behavioral contract.
  - **Keep tests deterministic and fast.** No randomness, no timing dependencies, no flaky external calls.
  - **Mock only at external boundaries.** Replace external dependencies (network, database, file I/O) with fakes or mocks. Internal logic is tested directly.
  - **Prefer pure function testing where possible.** Functions without side effects are the easiest to test and require no mocking. When testing methods with side effects, verify observable behavior (what was
  called, with what arguments, what was returned) — not internal implementation details.
  - **Isolate the unit under test.** Each test targets a single function or method. Do not test cross-layer flows or multi-step orchestrations — those belong in integration and E2E tests.

  ## 3. Coverage Rules

  - **Cover every public function and method.** Every public function or method in a module must have at least one unit test. Untested public surface area is a gap.
  - **Cover both success and error paths.** For each function, test the happy path (correct inputs → expected output) **and** every distinct error path (invalid inputs, boundary conditions, exception
  handling). Reading the function's code should reveal which paths exist — all of them must be tested.
  - **One test per behavior, not per function.** A function with three error paths needs at least four tests (one success + three errors), not one test that checks everything.

  ## 4. Mocking Strategy

  Mock or fake these boundaries:

  - Network requests (HTTP clients, API SDKs)
  - Database stores and connections
  - File system operations
  - External authentication/verification calls
  - Time-dependent operations (use deterministic timestamps)

  Do **not** mock:

  - Internal helper functions (test them directly)
  - Data transformations and parsing logic
  - Error class instantiation and hierarchy

  ## 5. Shared Test Utilities

  Maintain reusable fakes and builders in a shared module accessible to all test layers:

  - **Fake clients** — deterministic implementations of abstract interfaces for testing orchestration logic.
  - **Builder functions** — create test data objects with sensible defaults and overridable fields.
  - **Fake database primitives** — record SQL executions, return pre-configured results.
  - **Patch helpers** — convenience functions to replace module-level dependencies.

  Shared utilities are used by both unit and integration tests.

  ## 6. Naming Conventions

  - File naming: `test_<module>.py`
  - Test function naming: `test_<behavior>_<scenario>`
  - Group related cases in classes when it improves readability.
  - Keep fixtures in `conftest.py` focused and composable.

  ## 7. Fixture Design Patterns

  - **Patch fixtures** — replace external boundaries (network clients, database connections) with fakes or mocks. Scope them per test to avoid cross-test contamination.
  - **Builder fixtures** — provide factory functions that create test data with sensible defaults. Accept overrides for the fields relevant to each test case.
  - **Composed fixtures** — combine patch and builder fixtures to set up common scenarios. Keep them small and focused — a fixture that sets up too much context is a sign the test is not truly a unit test.
  - **conftest.py** — keep fixtures focused and composable. Avoid monolithic fixtures that configure everything; prefer small, single-purpose fixtures that tests can combine as needed.

  ## 8. What Unit Tests Cover

  - Service logic and orchestration
  - Error translation and mapping
  - Settings/configuration validation
  - Helper and utility functions
  - Provider client guard clauses and internal logic
  - Error hierarchy contracts (codes, default messages)

  ## 9. What Unit Tests Do NOT Cover

  - Real OAuth/browser flows
  - Real provider API calls
  - Real database persistence
  - API router/service wiring (covered by integration tests)
  - End-to-end flows (covered by E2E tests)

  ## 10. Maintenance Rules

  - **Keep fakes minimal.** Fakes should implement only the behavior needed for the tests that use them. Avoid building full-featured simulators.
  - **Update fakes when interfaces change.** When a dependency's interface evolves, update the corresponding fakes immediately — stale fakes cause false positives.
  - **Don't test implementation details.** Tests should verify what a function does (inputs → outputs, calls made), not how it does it internally. Refactoring internals should not break tests.
  - **Delete obsolete tests.** When a function is removed or its contract changes fundamentally, remove or rewrite the corresponding tests — do not leave dead test code.

  ## 11. Project-Specific Guide

  This file covers the general, transferable rules for the unit test layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general
  principles to the current application — consult [`unit_guide.md`](unit_guide.md).

  The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the
  project-specific guide.