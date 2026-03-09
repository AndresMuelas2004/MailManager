# General E2E Test Rules

This is the `general_e2e_rules.md` for the **end-to-end test** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the E2E test layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.

## 1. Scope

E2E tests validate the full backend flow against real external APIs and real authentication. **Nothing is mocked or faked** — every component runs exactly as it would in production.

## 2. Test Boundary Model

| Component | Behavior in E2E |
|---|---|
| Framework app | Real app created via application factory |
| Authentication | Real interactive flow (browser-based) |
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
- Browser available for interactive OAuth authorization steps

## 4. Flow Design

- The flow is split into individual endpoint-level tests so failures are pinpointed quickly.
- If one step fails, subsequent dependent steps are skipped to avoid cascade noise.
- Interactive steps (OAuth consent) require manual browser interaction.

## 5. Running Rules

```bash
# Always use -s to allow interactive output
python -m pytest backend/tests/e2e -v -s
```

Why `-s` matters:
- OAuth URLs may be printed when browser auto-open fails.
- Output is needed for manual interaction and debugging.

## 6. Failure Triage Order

Use this order for triage:

1. Missing env var or invalid credentials file → suite skipped.
2. Authentication failure → credentials file invalid or config mismatch.
3. OAuth/connect failure → likely provider auth config issue.
4. Provider operation failure → likely API permission, token, or account issue.
5. CRUD failure → likely API/database regression.

## 7. Extension Checklist

When adding a new provider:

- [ ] Add account creation for the provider.
- [ ] Add connect step for the provider.
- [ ] Add operation steps (send, fetch, etc.) for the provider.
- [ ] Ensure flow assertions include the new provider behavior.

The E2E suite should always represent the full set of supported providers.

## 8. Project-Specific Guide

This file covers the general, transferable rules for the end-to-end test layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`e2e_guide.md`](e2e_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `general_e2e_rules.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide.
