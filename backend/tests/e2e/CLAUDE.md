# General E2E Test Rules

This is the `CLAUDE.md` for the **end-to-end test** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the E2E test layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

## 1. Scope

E2E tests validate the full backend flow against real external APIs and real authentication. **Nothing is mocked or faked** — every component runs exactly as it would in production.
Interactive endpoints (OAuth login, provider connect) are excluded from the automated suite. In E2E must not be tests that needs interactive flows for the user like choosing and email or something similar.

## 2. Test Boundary Model

| Component | Behavior in E2E |
|---|---|
| Framework app | Real app created via application factory |
| Authentication | Session injected via direct DB insert (no interactive login) |
| Session validation | Real dependency — cookie verified against DB |
| External providers | Real API calls |
| Database | Real persistence |
| DB cleanup | Module/session transaction rollback at teardown |

## 3. Prerequisites

The suite is skipped automatically when prerequisites are missing.

Required:
- Environment variables for database and provider credentials
- Credential files must exist at the configured paths
- Internet access

## 4. Flow Design

- The flow is split into individual endpoint-level tests so failures are pinpointed quickly.
- If one step fails, subsequent dependent steps are skipped to avoid cascade noise.
- Each test checks its own prerequisites and skips if a dependency failed, while independent
  tests always run.


## 5. Project-Specific Guide

This file covers the general, transferable rules for the end-to-end test layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`e2e_guide.md`](e2e_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
