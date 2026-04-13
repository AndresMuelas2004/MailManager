# Common Mistakes — Corrections for Claude

This file tracks recurring mistakes Claude makes in this project. The developer updates it manually based on patterns observed across conversations. Claude must check this file before any implementation and treat every entry as a hard rule.

## Mistakes

### 1. E2E tests — don't split simple follow-up assertions into separate tests

When an E2E test performs a destructive action (delete, disconnect, etc.), the verification that the resource is actually gone (e.g., GET returns 404) must be part of the **same test function**, not a separate test. The E2E suite is sequential and flow-dependent — creating a standalone test just to check a 404 after a delete adds noise without value. The assertion is part of the same logical operation, not a separate "behavior."

**Where this applies:** E2E tests only. Unit tests follow "one behavior per case" and should stay granular. Integration tests depend on context — simple follow-up assertions can stay in the same test, but distinct contracts (different endpoint, different error translation) deserve their own test.

**Why:** The E2E CLAUDE.md says tests are "split into individual endpoint-level tests." A follow-up 404 check is not a separate endpoint test — it is verifying the side effect of the endpoint already being tested.

### 2. Plans must propose E2E test updates when applicable

When a plan adds new endpoint behavior or modifies existing endpoint behavior, the plan **must** include a clear, explicit step proposing the required E2E test changes. This does not mean every plan needs E2E changes — only those that affect endpoint behavior visible at the E2E level (new endpoints, changed responses, new provider operations, etc.).

The E2E step in the plan must describe **what** will change in the E2E suite and **why**, with enough detail for the user to evaluate it during plan review. The user always reviews plans before accepting, so vague references like "update E2E tests" are not acceptable — specify which tests are added or modified and what they verify.

**Where this applies:** Plan mode only. This is about plan completeness, not about test writing style.

**Why:** Claude has a recurring tendency to propose unit and integration test updates but silently omit E2E tests, even though root CLAUDE.md § 8 explicitly requires all three layers. The omission is not caused by any rule — it is a behavioral bias toward avoiding the more complex E2E flow. This entry exists to counteract that bias.

### 3. Starting PostgreSQL — use pg_ctl, never Docker or Start-Service

When tests fail because PostgreSQL is not running, start it with `pg_ctl.exe` directly:

```
powershell -Command "& 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe' start -D 'C:\Program Files\PostgreSQL\16\data' -l 'C:\Program Files\PostgreSQL\16\data\log\startup.log'"
```

Then verify with:

```
powershell -Command "& 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe' status -D 'C:\Program Files\PostgreSQL\16\data'"
```

**Never** use `docker-compose up -d db`, `Start-Service 'postgresql-x64-16'`, or any Docker-based approach. PostgreSQL always runs locally on this machine.

**Where this applies:** Any situation where Claude needs to start or check the database — before running integration tests, e2e tests, or any DB-dependent operation.

**Why:** `Start-Service` interacts with the Windows Service Control Manager, which can get stuck in an inconsistent state after an abnormal shutdown and refuse to start. `pg_ctl` bypasses the SCM and starts the PostgreSQL process directly, which is reliable. Docker is not used in this project for running tests.
