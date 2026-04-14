# Frontend Guide — Project-Specific (maintained by Claude)

This file contains details specific to MailManager's frontend. Update it when the project changes (new features, new routes, architectural shifts). Do not modify `CLAUDE.md`.

## Feature Modules

| Feature | Directory | Status | Purpose |
|---------|-----------|--------|---------|
| `auth` | `features/auth/` | Implemented | Google OIDC login, session check, logout |
| `mailboxes` | `features/mailboxes/` | Scaffolded | Create, list, and delete mailboxes |
| `accounts` | `features/accounts/` | Scaffolded | Connect, list, edit, and delete email accounts within a mailbox |
| `emails` | `features/emails/` | Scaffolded | Unified inbox, sent, spam, trash — listing, sync, read status, move, content view |
| `drafts` | `features/drafts/` | Scaffolded | Draft listing, sync, create, update, send, delete |
| `users` | `features/users/` | Scaffolded | User profile and account deletion |

## Route Structure

Routes defined in `app/routes/router.tsx`:

| Path | Feature | Page | Status |
|------|---------|------|--------|
| `/login` | auth | `LoginPage` | Implemented |
| `/` | mailboxes | `MailboxesPage` (list/create) | Planned |
| `/m/:mailboxId/inbox` | emails | `InboxPage` (box=ALL_MAIL) |
| `/m/:mailboxId/sent` | emails | `SentPage` (box=SENT) |
| `/m/:mailboxId/spam` | emails | `SpamPage` (box=SPAM) |
| `/m/:mailboxId/trash` | emails | `TrashPage` (box=TRASH) |
| `/m/:mailboxId/drafts` | drafts | `DraftsPage` |
| `/m/:mailboxId/compose` | emails | `ComposePage` |
| `/m/:mailboxId/accounts` | accounts | `AccountsPage` |

## Backend API Mapping

Each `api/endpoints/` file maps to a backend router:

| Endpoint file | Backend router | Resource |
|---------------|---------------|----------|
| `auth.ts` | `/auth` | Authentication (login, me, logout, delete) |
| `mailboxes.ts` | `/mailboxes` | Mailbox CRUD |
| `accounts.ts` | `/mailboxes/{id}/accounts` | Account CRUD + connect |
| `emails.ts` | `/mailboxes/{id}/emails` | Email listing, sync, send, trash, spam, read status, content |
| `drafts.ts` | `/mailboxes/{id}/...drafts...` | Draft CRUD, sync, send |

## Auth Infrastructure

### AuthProvider (`app/providers/AuthProvider.tsx`)
Context provider that wraps the entire app. On mount, calls `GET /auth/me` to check for an existing session cookie. Provides `{ user, loading, error, login, logout }` to the tree.

### AuthContext (`app/providers/AuthContext.ts`)
Defines the `AuthState` type, creates the React context, and exports the `useAuth()` convenience hook. Separated from `AuthProvider.tsx` to satisfy React Refresh (component-only exports per file).

### RequireAuth (`app/routes/RequireAuth.tsx`)
Route guard layout component. Shows a spinner while `AuthProvider` checks the session. Redirects to `/login` if no user. Renders `<Outlet />` for authenticated users. All protected routes are nested under this component.

### Google Identity Services Integration
- GIS script loaded via `<script>` tag in `index.html` (no npm package).
- TypeScript declarations in `src/types/google-accounts.d.ts`.
- `useGoogleLogin` hook (`features/auth/hooks/useGoogleLogin.ts`) initializes GIS and renders the official Google button via `renderButton()`.
- Requires `VITE_GOOGLE_CLIENT_ID` env var (must match backend's `GOOGLE_CLIENT_ID`).

## Design Reference

Screen mockups are maintained in the Pencil design file at `Ignore/PENCIL/Pantallas.pen`. Screens include: Login, Create Mailbox, Connected Accounts, Compose Email, Unified Inbox, Spam Inbox, Trash Inbox, Sent Inbox, Drafts Inbox.

## Extension Checklist — Adding a New Feature

- [ ] Create the feature directory: `features/<name>/components/`, `features/<name>/hooks/`, `features/<name>/pages/`.
- [ ] Add DTOs to `api/types/dto.ts` matching the backend schemas.
- [ ] Create the endpoint file in `api/endpoints/<name>.ts`.
- [ ] Build the page component in `features/<name>/pages/`.
- [ ] Build hooks in `features/<name>/hooks/` for data fetching and mutations.
- [ ] Build feature-specific components in `features/<name>/components/`.
- [ ] Add the route to `app/routes/router.tsx`.
- [ ] Update this guide with the new feature, route, and API mapping.

## Document Maintenance

Update this file when: features are added or removed, routes change, API endpoint files are created, or architectural decisions specific to this project are made. Do not modify `CLAUDE.md`.
