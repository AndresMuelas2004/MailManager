# Unit Tests Guide

> **General rules**: this test layer MUST respect every rule defined in
> [`general_unit_rules.md`](./general_unit_rules.md).
> The current document contains project-specific details that complement those rules.

**Authority rule**: the code of this layer must respect what is documented here. If there is a discrepancy between this guide and existing code, this guide is the reference — fix the code, not the guide. When new functionality is added, update this guide at the end of the task to reflect the new reality.

## Project-Specific Notes

### Coverage targets

Unit tests cover: `core/email` (clients, manager, helpers, errors), `database` (settings, token crypto, repositories, credentials, connection, lifecycle), `api/services` (auth, emails, error translation, helpers), and `auth` (settings).

### Database fakes

`tests/shared/database_fakes.py` provides `FakeCursor`, `FakeConnection`, `patch_connection`, and `patch_connection_error` — used by all database repository unit tests. Less discoverable than `tests/shared/email_fakes.py` (which provides `FakeEmailClient` and `build_metadata`).
