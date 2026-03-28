# Common Mistakes — Corrections for Claude

This file tracks recurring mistakes Claude makes in this project. The developer updates it manually based on patterns observed across conversations. Claude must check this file before any implementation and treat every entry as a hard rule.

## Mistakes

### 1. E2E tests — don't split simple follow-up assertions into separate tests

When an E2E test performs a destructive action (delete, disconnect, etc.), the verification that the resource is actually gone (e.g., GET returns 404) must be part of the **same test function**, not a separate test. The E2E suite is sequential and flow-dependent — creating a standalone test just to check a 404 after a delete adds noise without value. The assertion is part of the same logical operation, not a separate "behavior."

**Where this applies:** E2E tests only. Unit tests follow "one behavior per case" and should stay granular. Integration tests depend on context — simple follow-up assertions can stay in the same test, but distinct contracts (different endpoint, different error translation) deserve their own test.

**Why:** The E2E CLAUDE.md says tests are "split into individual endpoint-level tests." A follow-up 404 check is not a separate endpoint test — it is verifying the side effect of the endpoint already being tested.
