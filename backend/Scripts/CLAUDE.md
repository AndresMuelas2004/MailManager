# backend/Scripts/

Manual execution scripts for hands-on verification of endpoint behavior against real email provider clients.

These scripts contain **no business logic** — they call existing service-layer endpoints directly, acting as lightweight CLI wrappers. Their purpose is to complement the automated test suites (unit, integration, E2E) by enabling manual exploration of edge cases and provider-specific behaviors that are easier to inspect interactively.

Subdirectories:

- `cli_utilities/` — reusable scripts for common operations (register users, connect accounts, send emails, manage trash, etc.). All parameters are passed via CLI arguments; no hardcoded credentials.
- `ejecucion_unica/` — one-off scripts for specific setup tasks (not tracked in git).
- `EXECUTION_MDs/` — personal notes with runtime parameters (not tracked in git).
