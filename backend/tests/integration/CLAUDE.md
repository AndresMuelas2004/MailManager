# General Integration Test Rules

This is the `CLAUDE.md` for the **integration test** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the integration test layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

## 1. Scope

Integration tests verify the full internal backend flow:

```
router → router helpers → service → database → core
```

These tests execute real framework endpoints and real database operations, while replacing external provider boundaries with fakes.

## 2. Test Boundary Model

| Component | Real or Fake | Notes |
|---|---|---|
| Framework app | Real | Exercised via test client |
| Routers and services | Real | Production modules |
| Database | Real | Per-test transaction rollback isolation |
| Core orchestration | Real | Built and used in tests |
| External provider calls | Fake | Replaced with fake clients |
| App credentials loading | Fake | Monkeypatched |
| Token loading/saving | Fake | Monkeypatched |
| Session authentication | Fake | Auth dependency overridden |

## 3. Database Isolation

- Each test runs inside a database transaction that is **rolled back** after the test completes.
- A shared connection is monkeypatched into all repository modules.
- Schema is created once per test session (e.g. via migration tool).
- A deterministic test user is seeded per test for ownership checks.

## 4. Auth Override Pattern

- The session/auth dependency is overridden to return a fixed test user ID for all protected endpoints.
- Tests that verify real session validation temporarily remove the override and restore it in a `finally` block.

## 5. Error Strategy Coverage

Integration tests separate two major error surfaces:

1. **Direct API-layer errors** — service raises `ApiError` directly (missing resources, validation failures, auth/session errors).
2. **Translated errors** — lower-layer errors translated to API errors (core errors, database errors, auth errors).

## 6. Fixture Design Patterns

- **Schema fixture** (session scope, autouse) — runs migrations once.
- **Isolation fixture** (per test, autouse) — manages transaction rollback.
- **Seed fixture** (per test, autouse) — inserts deterministic test data.
- **Auth override fixture** (session scope, autouse) — overrides auth dependency.
- **Client fixture** — patches builder helpers and provides a test client.
- **Setup helpers** — callable fixtures that create prerequisite resources via API calls.
- **Failing client fixture** (indirect parametrize) — injects fake failures for error translation tests.

## 7. Maintenance Rules

- Keep fake behavior deterministic.
- Keep each test focused on one API contract or one translation path.
- Avoid provider-specific assumptions in integration tests.
- Add E2E coverage when a change depends on real provider behavior.

## 8. What Integration Tests Do NOT Cover

- Real OAuth browser flows
- Real provider HTTP traffic
- Real token refresh against live endpoints
- Frontend behavior

Those are covered by E2E tests.

## 9. Project-Specific Guide

This file covers the general, transferable rules for the integration test layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`integration_guide.md`](integration_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
