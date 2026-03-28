# General Database Layer Rules

This is the `CLAUDE.md` for the **database persistence** layer. It serves as the general architectural reference for this layer, describing its separation of responsibilities, its error handling and escalation model, its structural rules, and its common behavior. Every aspect covered here is transferable to any application that follows this layered architecture — nothing is specific to a single project.

**Project-agnostic by design.** Nothing here references a concrete domain, entity, or feature. Every rule applies to any repository that follows this layered architecture.

**Reusable.** Copy this file into a new project to establish the database layer architecture from day one. The project-specific guide extends these rules with domain details but must never contradict them.

**Precedence.** In case of conflict between this file and a project-specific guide, these rules take precedence.
**Immutable.** This file must never be edited. All project-specific changes go in the `*_guide.md` file referenced at the end of this document.
## 1. Layer Isolation

The `database/` package is a framework-agnostic layer — it has **no imports from `api/`**, `core/`, or `auth/`. Services in the API layer translate `DatabaseError` subclasses into `ApiError` subclasses via a translation function.

## 2. Package Structure

```
  database/
  ├── __init__.py              # Public facade (re-exports everything below)
  ├── errors/                  # Database-specific error hierarchy
  │   ├── __init__.py          #   Re-exports all exceptions
  │   └── exceptions.py        #   DatabaseError base + subclasses
  ├── settings.py              # Centralized env var reading and validation
  ├── connection.py            # Connection pool management + transactional context manager
  ├── lifecycle.py             # Pool warmup and schema migration orchestration
  ├── contracts.py             # Abstract interfaces (Store contracts)
  ├── queries/                 # Raw SQL constants only — no Python logic
  ├── repositories/            # Concrete implementations of contracts
  ├── security/                # (optional) Credentials and token encryption utilities
  └── migrations/              # Schema evolution (Alembic or equivalent)

  
```

## 3. Public Facade

All external code imports from the package root (`from database import ...`). The `__init__.py` re-exports:

- Store singleton instances
- Pool management functions (close, warmup)
- Migration helpers
- Credential loading functions

External consumers **never import from internal submodules**.

## 4. Internal Data Flow

### Runtime (request handling)

  repositories/
    → queries/          (SQL constants)
    → connection.py     (pool access)
    → contracts.py      (abstract interfaces)
    → security/         (optional — token encryption)

  security/
    → settings.py       (credential paths, encryption keys)

  connection.py
    → settings.py       (pool config)

  settings.py
    → os.environ        (the only module that reads env vars)

  ### Startup (bootstrap)

  lifecycle.py
    → connection.py        (health-check / warmup)
    → settings.py          (migration config)
    → migrations/runner.py (schema evolution, when enabled)

## 5. Layer Boundary Rules

- **`settings.py`** — the only module that reads `os.environ`.
- **`connection.py`** — the only module that manages the connection pool.
- **`queries/`** — contains only SQL string constants. Zero imports, zero logic.
- **`repositories/`** — the only modules that execute SQL. They combine a query with a connection and raise specific `DatabaseError` subclasses on failure.
- **`contracts.py`** — defines abstract interfaces that decouple services from concrete implementations.
- **`__init__.py`** — re-exports everything. External code never imports submodules directly.

## 6. Error Hierarchy

The database layer uses its own `DatabaseError` hierarchy, independent of the API error hierarchy.

```
 DatabaseError                   # Base for all database errors
  ├── ConnectionPoolError         # Pool creation, warmup, connection exhaustion
  ├── QueryError                  # Any SQL execution failure (CRUD)
  ├── MigrationError              # Schema migration failures
  ├── SettingsError               # Missing/invalid env vars, malformed keys
  └── ...                         # Project-specific subclasses (see guide)
```


Each class has a `code`, `default_message`, `message`, and `detail` dict — same base-class pattern as other layers.

## 7. Capture Technique

Every `try` block in the database layer follows this ordered pattern:

```python
try:
    # ... operation ...
except specific_db_lib.SpecificError:       # 1. Specific DB library error first
    return None                             #    (graceful handling where applicable)
except DatabaseError:                        # 2. Never double-wrap
    raise
except db_lib.Error as exc:                 # 3. Domain-specific catch
      raise <ModuleError>("Failed to ...") from exc
except Exception as exc:                    # 4. Generic fallback last
      raise <ModuleError>(
          f"Unexpected error ({type(exc).__name__}): {exc}"
      ) from exc
```

### Rules

1. **Specific DB library errors first** (step 1) — only where applicable (e.g. invalid UUID → graceful `None`/`[]`).
2. **Never double-wrap `DatabaseError`** (step 2) — this guard is only needed when code inside the `try` block can raise a `DatabaseError` subclass, either explicitly or via an internal helper. The `except DatabaseError: raise` re-raises it before the generic `except Exception` can catch and wrap it. **If nothing inside the `try` can produce a `DatabaseError`, this guard is unnecessary.**
3. **Domain-specific catch** (step 3) — all DB library error subclasses map to the appropriate exception (`QueryError` for repositories, `ConnectionPoolError` for pool, `MigrationError` for migrations).
4. **Generic fallback last** (step 4) — ensures no exception escapes untyped. Message includes `type(exc).__name__` for debuggability. Internal layers may include these details since errors are always translated before reaching the client.
5. **Preserve the cause chain** — always `raise ... from exc`.

### Where each exception is raised

  - **`connection.py`** → `ConnectionPoolError` (pool creation, pool exhaustion)
  - **`lifecycle.py`** → `ConnectionPoolError` (warmup), `MigrationError` (migrations)
  - **`repositories/*.py`** → `QueryError` (SQL failures)
  - **`settings.py`** → `SettingsError` (missing/invalid env vars)
  - Project-specific modules (e.g. `security/`) raise their own `DatabaseError` subclasses as defined in the project guide.

## 8. Contract Pattern

Abstract store interfaces in `contracts.py` define the public API for each data domain:

- Each contract is an abstract class with typed method signatures.
- Concrete implementations live in `repositories/`.
- Singleton instances are created at module level and re-exported via the facade.
- Services depend on the abstract contracts, not concrete implementations.

## 9. Settings Rules

- `settings.py` is the **only module** that reads `os.environ`.
- Missing or invalid required env vars raise `SettingsError`.
- Settings are organized by concern: connection, pool tuning, migrations, encryption, credentials.

## 10. Migration Rules

- Schema changes are managed with a migration tool (Alembic or equivalent).
- Migrations are the source of truth for schema evolution — not `schema.sql` snapshots.
- Auto-migrate at startup is disabled by default; enable via env var for development.
- Production recommendation: run migrations in CI/CD before API rollout.

## 11. Security Rules

The security/ sub-package is optional. Projects that do not store encrypted tokens or credential files at the database layer may omit it entirely along with its associated error subclasses. When present,
the following rules apply:
- Sensitive data (tokens, credentials) is encrypted at rest.
- Encryption keys are loaded from env vars via `settings.py`.
- Credential files are loaded from paths specified in env vars.
- Legacy plaintext fallback is controlled by explicit env vars — never silent.
- A malformed encryption key raises `SettingsError` immediately — never silently treated as absent.

## 12. Service-Side Translation

Services translate database errors via explicit `try`/`except` blocks using `translate_database_error`:

```python
try:
    record = store.get(resource_id)
except DatabaseError as exc:
    raise translate_database_error(exc) from exc
except Exception as exc:
    logger.warning("Unexpected <operation> error (%s): %s", type(exc).__name__, exc)
    raise ApiError("Failed to <operation>.") from exc
```

`translate_database_error` maps `DatabaseError` subclasses to `ApiError` subclasses via the mapping. The `except Exception` fallback catches truly unexpected non-DB errors.

## 13. Project-Specific Guide

This file covers the general, transferable rules for the database persistence layer. For project-specific details — concrete rules, architectural decisions, and implementation details that apply these general principles to the current application — consult [`database_guide.md`](database_guide.md).

The guide complements these rules but never contradicts them. In case of conflict, this `CLAUDE.md` has absolute precedence. Code in this layer must respect both levels: first these general rules, then the project-specific guide database_guide.md.
