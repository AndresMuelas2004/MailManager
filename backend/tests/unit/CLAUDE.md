# General Unit Test Rules

This is the `CLAUDE.md` for the **unit test** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the unit test layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

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
- **Prefer pure function testing where possible.** Functions without side effects are the easiest to test and require no mocking.

## 3. Mocking Strategy

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

## 4. Shared Test Utilities

Maintain reusable fakes and builders in a shared test utilities module:

- **Fake clients** — deterministic implementations of abstract interfaces for testing orchestration logic.
- **Builder functions** — create test data objects with sensible defaults and overridable fields.
- **Fake database primitives** — record SQL executions, return pre-configured results.
- **Patch helpers** — convenience functions to replace module-level dependencies.

Shared utilities are used by both unit and integration tests.

## 5. Naming Conventions

- File naming: `test_<module>.py`
- Test function naming: `test_<behavior>_<scenario>`
- Group related cases in classes when it improves readability.
- Keep fixtures in `conftest.py` focused and composable.

## 6. What Unit Tests Cover

- Service logic and orchestration
- Error translation and mapping
- Settings/configuration validation
- Helper and utility functions
- Provider client guard clauses and internal logic
- Error hierarchy contracts (codes, default messages)

## 7. What Unit Tests Do NOT Cover

- Real OAuth/browser flows
- Real provider API calls
- Real database persistence
- API router/service wiring (covered by integration tests)
- End-to-end flows (covered by E2E tests)

## 8. Project-Specific Guide

This file covers the general, transferable rules for the unit test layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`unit_guide.md`](unit_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
