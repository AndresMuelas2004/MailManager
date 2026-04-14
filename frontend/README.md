# Frontend (`frontend`)

This is the React + TypeScript frontend for MailManager. It consumes the FastAPI backend and provides mailbox and inbox UI flows.

For architectural rules read [`CLAUDE.md`](./CLAUDE.md). For project-specific conventions, route map, provider tree, shared utilities and feature contracts read [`frontend_guide.md`](./frontend_guide.md).

## Stack

- React 19
- TypeScript (strict)
- Vite
- React Router v7
- Tailwind CSS v4
- ESLint

## Scripts

```bash
npm run dev      # start Vite dev server
npm run build    # type-check and production build
npm run lint     # run ESLint
npm run preview  # preview the production build
```

## Setup

```bash
cd frontend
npm install
npm run dev
```

Default dev URL: `http://localhost:5173`.

## Backend API Configuration

The frontend HTTP client uses:

- `VITE_API_BASE_URL` when provided
- fallback: `http://localhost:8000`

Example (`.env.local`):

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=<must match backend's GOOGLE_CLIENT_ID>
```

## Project Structure

```text
src/
|-- api/
|   |-- client/        # request wrapper + API error normalization
|   |-- endpoints/     # one file per backend resource
|   `-- types/         # DTOs mirroring backend schemas
|-- app/
|   |-- layout/        # RootLayout, MailboxLayout, mailboxNavItems
|   |-- providers/     # AuthProvider, DraftComposerGlobalProvider, draftComposer/
|   `-- routes/        # router.tsx, RequireAuth
|-- components/
|   |-- common/        # domain-agnostic primitives (Spinner, Modal, Checkbox, ConfirmPopover)
|   `-- ui/            # domain-aware shared widgets (Sidebar, ComposeOverlay, SettingsDropdown, …)
|-- features/
|   |-- auth/
|   |-- mailboxes/
|   |-- accounts/
|   |-- emails/
|   `-- drafts/
|-- lib/
|   |-- formatters.ts  # formatDate, resolveAccount, buildAccountMap
|   |-- providers.ts   # PROVIDER_META, getProviderMeta, isGenericLabel
|   |-- types.ts       # EmailBox, ComposerMode
|   `-- hooks/         # useAsync, useSelection, useCacheThenSync, useMailboxList, useCurrentUser
|-- styles/
`-- main.tsx
```

All page components live under `features/<name>/pages/`. There is no top-level `src/pages/` directory.

## Routing

Routes are defined in `src/app/routes/router.tsx`. Full map, layout tree and which routes are lazy-loaded are documented in [`frontend_guide.md`](./frontend_guide.md#route-map).

## HTTP Layer

`src/api/client/http.ts` centralizes API requests:

- Base URL resolution (`VITE_API_BASE_URL` fallback to `http://localhost:8000`).
- JSON request/response handling.
- `credentials: "include"` on every request (cookie-based session).
- Conversion of non-ok responses to `ApiError`; network failures become `ApiError` with code `"network_error"`.
- `toUiError()` for hook consumers.

## Development Notes

- Run backend (`backend/main.py`) before testing frontend flows.
- CORS in backend allows `http://localhost:5173`.
- Keep DTO changes synchronized with backend schemas.
