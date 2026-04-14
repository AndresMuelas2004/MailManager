# Frontend Guide — Project-Specific (maintained by Claude)

This file contains details specific to MailManager's frontend. Update it when the project changes (new features, new routes, architectural shifts). Do not modify `CLAUDE.md`.

## Feature Modules

| Feature | Directory | Purpose |
|---------|-----------|---------|
| `auth` | `features/auth/` | Google OIDC login, session check, logout |
| `mailboxes` | `features/mailboxes/` | Create mailbox + gateway redirect to the active mailbox |
| `accounts` | `features/accounts/` | Connect, list, and delete email accounts within a mailbox |
| `emails` | `features/emails/` | Unified and per-account views: listing, cache-then-sync, bulk actions, content viewer |
| `drafts` | `features/drafts/` | Draft listing (unified + per-account), sync, bulk delete; shares the compose overlay |

## Router & Layout Tree

```
<Providers>                                  (app/providers/Providers.tsx)
  AuthProvider
    <RouterProvider>                         (app/routes/router.tsx)
      RootLayout                             (app/layout/RootLayout.tsx)
        DraftComposerGlobalProvider          (app/providers/DraftComposerGlobalProvider.tsx)
          <Suspense fallback={Spinner}>
            /login  → LoginPage
            /       → RequireAuth            (app/routes/RequireAuth.tsx)
              index → MailboxGatewayPage
              create-mailbox → CreateMailboxPage
              m/:mailboxId → MailboxLayout   (app/layout/MailboxLayout.tsx)
                accounts → ConnectedAccountsPage
                inbox|sent|spam|trash → UnifiedInboxPage box=...
                drafts → DraftsPage
                account/:accountId
                  index → redirect to inbox
                  inbox|sent|spam|trash → AccountInboxPage box=...
                  drafts → AccountDraftsPage
```

Key points:
- `DraftComposerGlobalProvider` is **global** (all descendants of the router). It internally derives the active `mailboxId` via `matchPath("/m/:mailboxId/*", useLocation().pathname)` — no prop drilling, no per-layout instantiation.
- All feature pages (`UnifiedInboxPage`, `AccountInboxPage`, `AccountDraftsPage`, `DraftsPage`, `ConnectedAccountsPage`) are loaded with `React.lazy()` and wrapped in the `<Suspense>` inside `RootLayout`. Boot-path pages (`LoginPage`, `MailboxGatewayPage`, `CreateMailboxPage`, `RequireAuth`, `MailboxLayout`, `RootLayout`) are eager.

## Route Map

| Path | Page component |
|------|----------------|
| `/login` | `LoginPage` |
| `/` | `MailboxGatewayPage` (redirects to `/create-mailbox` or `/m/:id/accounts`) |
| `/create-mailbox` | `CreateMailboxPage` |
| `/m/:mailboxId/accounts` | `ConnectedAccountsPage` |
| `/m/:mailboxId/inbox` | `UnifiedInboxPage box="ALL_MAIL"` |
| `/m/:mailboxId/sent` | `UnifiedInboxPage box="SENT"` |
| `/m/:mailboxId/spam` | `UnifiedInboxPage box="SPAM"` |
| `/m/:mailboxId/trash` | `UnifiedInboxPage box="TRASH"` |
| `/m/:mailboxId/drafts` | `DraftsPage` (unified) |
| `/m/:mailboxId/account/:accountId` | redirects to `…/inbox` |
| `/m/:mailboxId/account/:accountId/inbox\|sent\|spam\|trash` | `AccountInboxPage box=...` |
| `/m/:mailboxId/account/:accountId/drafts` | `AccountDraftsPage` |

The per-account tabs (`AccountTabs` in `features/emails/components/`) use `NavLink` against this URL map; there is no local tab state.

## Backend API Mapping

| Endpoint file | Backend router | Resource |
|---------------|---------------|----------|
| `auth.ts` | `/auth` | Authentication (`loginWithGoogle`, `getMe`, `logout`, `deleteMe`) |
| `mailboxes.ts` | `/mailboxes` | Mailbox CRUD |
| `accounts.ts` | `/mailboxes/{id}/accounts` | Account CRUD + `connectAccount` |
| `emails.ts` | `/mailboxes/{id}/emails` | Listing, sync, send, trash, spam, read status, content |
| `drafts.ts` | `/mailboxes/{id}/...drafts...` | Draft CRUD, sync, send |

Note: `deleteMe()` (auth) is distinct from `deleteAccount()` (accounts). The former removes the whole user; the latter disconnects a single email account.

## Auth Flow (cookie-based session)

1. Backend sets an HttpOnly session cookie during `POST /auth/google`.
2. Every request from the frontend uses `credentials: "include"` (configured once in `api/client/http.ts` — `request<T>()`).
3. On mount, `AuthProvider` (`app/providers/AuthProvider.tsx`) calls `GET /auth/me` to hydrate the session. `{ user, loading, error, login, logout }` is exposed via `AuthContext` and consumed via `useAuth()`.
4. `RequireAuth` (`app/routes/RequireAuth.tsx`) shows a spinner while loading and redirects to `/login` when the user is null.
5. `lib/hooks/useCurrentUser.ts` wraps `getMe` and `deleteMe` for any layout/page that needs to operate on the current user (e.g. the sidebar's "Eliminar cuenta"). It lives in `lib/` because it is application-level, not feature-scoped.

Google Identity Services is loaded via `<script>` in `index.html` (no npm package). Types live in `src/types/google-accounts.d.ts`. `useGoogleLogin` renders the official button and requires `VITE_GOOGLE_CLIENT_ID` (must match the backend `GOOGLE_CLIENT_ID`).

## Shared Utilities (`lib/`)

### Types (`lib/types.ts`)
- `EmailBox = "ALL_MAIL" | "SENT" | "SPAM" | "TRASH"` — central discriminant for listing and bulk actions.
- `ComposerMode = "new_email" | "new_draft" | "edit_draft"` — drives `ComposeOverlay`.

### Provider registry (`lib/providers.ts`)
`PROVIDER_META: Record<Provider, ProviderMeta>` centralizes everything about a mail provider that the UI needs (`label`, `friendlyName`, `dotClass`, `headerBgClass`, `headerTextClass`, `accentTextClass`). Consumers: `ComposeOverlay`, `ProviderSelect`, `AccountCard`, `UnifiedInboxPage`, `AccountInboxPage`, `AccountDraftsPage`, `useConnectedAccounts`, `lib/formatters.ts`. Helper `isGenericLabel(label, provider)` lives here — used to decide whether to show a custom display label alongside the email. Adding a new provider (see "Adding a new email provider" below) only touches this file on the frontend.

### Formatters (`lib/formatters.ts`)
- `formatDate(iso)` — locale-aware, returns a time (`HH:mm`) if the date is today, otherwise `DD mes`.
- `formatShortDate(iso)` — always `DD mes`.
- `buildAccountMap(accounts)` — `Map<account_id, account>`.
- `resolveAccount(accountId, accountsById)` — returns `{ providerName, accountEmail }` using `PROVIDER_META` for the friendly name.

### Hooks (`lib/hooks/`)
- `useAsync<T>()` — `{ data, loading, error, run(fn), reset, setData, setError }`. Wraps the universal try/setLoading/toUiError pattern. Handles stale-response guarding with a monotonic token.
- `useSelection<T>(keyOf, topN?)` — generic selection state. Replaces the previous per-feature `useEmailSelection`/`useDraftSelection`. `keyOf` is caller-provided; `topN` defaults to 50.
- `useCacheThenSync<T>({ fetchData, sync, deps })` — encapsulates the universal "show cache, then sync, then refetch" pattern. Returns `{ data, loading, syncing, error, refresh, syncAndRefresh }`. Adopt this when adding any new list view that has a provider-backed cache.
- `useMailboxList(currentMailboxId)` — lists mailboxes once on mount; exposes `currentMailboxName` and `handleCreate`.
- `useCurrentUser()` — wraps `getMe` / `deleteMe` for the sidebar's "Eliminar cuenta" and any future user-level action.

## Cache-then-Sync Pattern

`useEmailList` and `useDraftsList` (and any future list hook) follow this shape:

1. On mount, `Promise.all([fetchData(), fetchAccounts()])` → immediately render the cached view and drop `loading` to `false`.
2. Kick off the provider sync in the background (`setSyncing(true)` → `syncXxx(...)` → `setSyncing(false)`). Failures are swallowed — the cache is still displayed.
3. After the sync resolves, refetch the data and reconcile the view.

`syncing` is exposed **separately** from `loading`. Tables render a small spinning icon while `syncing === true` so the user can see the background refresh without the page blanking out. Always prefer this contract over a simple `loading` flag when the endpoint involves a provider round-trip.

## Email Bulk Actions

The unified and per-account views render `EmailTable` with a context-aware toolbar. Whenever `selection.size > 0`, the toolbar turns into `BulkActionsBar`.

### Selection
- `useSelection<EmailMetadataOut>(emailKey)` in `features/emails/hooks/useBulkBar.tsx`.
- `emailKey(e) = "${account_id}|${provider_message_id}"`.
- "Select top 50" is the only "select all" supported (`toggleTopN`, `TOP_N = 50`).

### Bulk mutations (`hooks/useEmailBulkActions.ts`)
Wraps `moveToTrash`, `updateReadStatus`, `markAsSpam`, `restoreFromSpam`, `trashAction`. Each action runs `endpoint → clearSelection → refresh` on success, storing a `UiError` on failure.

### Actions per box (`features/emails/boxes.ts`)
`EMAIL_BOX_CONFIG: Record<EmailBox, { title, subtitle, allowedBulkActions }>` is the single source of truth. `BulkActionsBar` only renders the buttons listed in `allowedBulkActions` for the current `box`. Adding a new action = extend `BulkAction` union, add the button branch, and update `allowedBulkActions` in `boxes.ts`.

| Box       | allowedBulkActions |
|-----------|--------------------|
| ALL_MAIL  | `toggle_read`, `move_to_trash`, `mark_spam` |
| SENT      | `toggle_read`, `move_to_trash` |
| SPAM      | `toggle_read`, `move_to_trash`, `restore_from_spam` |
| TRASH     | `toggle_read`, `restore_from_trash`, `delete_permanently` |

### Read/unread toggle logic
Decided on the frontend from the selected emails: if `unreadCount ≥ readCount` the action is "mark as read"; otherwise "mark as unread". Ties resolve to "mark as read". The backend is not responsible for inferring the intent.

## Email Content Viewer

Clicking any row of `EmailTable` (outside the selection checkbox) opens a modal with the full email.

- `useEmailViewer(mailboxId, refresh)` (in `features/emails/hooks/`) owns the opened email and `{ openedEmail, open, close, handleRead }`. `handleRead` calls `updateReadStatus(...)` then `refresh()`.
- `ViewerMount` (`features/emails/components/`) is a thin switch that renders `EmailViewer` only when an email is open.
- `Modal` (`components/common/Modal.tsx`) is the generic dialog primitive (portal, Esc, backdrop, X button, body-scroll lock).
- `useEmailContent` (`features/emails/hooks/useEmailContent.ts`) fetches `GET /mailboxes/{id}/emails/{provider_message_id}/content` and cancels in-flight requests.
- `EmailViewer` (`features/emails/components/EmailViewer.tsx`) renders the iframe-sandboxed email body. HTML bodies are wrapped with a base doctype + `<base target="_blank">` + minimal CSS, then rendered via `srcDoc` with `sandbox="allow-popups allow-popups-to-escape-sandbox"` and `referrerPolicy="strict-origin-when-cross-origin"`. The backend already sanitizes the HTML (premailer + bleach); the sandbox keeps scripts/forms/same-origin disabled while allowing `target="_blank"` to work. Plain-text bodies go through `<pre>` in the same iframe.
- Auto mark-as-read: when `EmailViewer` mounts, if `email.is_read === false` it calls `onRead(email)` exactly once (guarded via `useRef`).

## Drafts

### Compose overlay (`components/ui/ComposeOverlay.tsx`)
Domain-agnostic overlay driven by the `mode: ComposerMode` prop:
- `"new_email"` → "Enviar" button (`POST /emails/send`). Closing with X after any non-empty field fires a best-effort draft `POST` so nothing is lost.
- `"new_draft"` → "Guardar" button (`POST /drafts` on first save; subsequent saves `PATCH`). Closing with X with non-empty content also persists.
- `"edit_draft"` → "Guardar" (`PATCH`) and "Enviar borrador" (`POST .../send` after `PATCH` if dirty). Closing with X only `PATCH`es when the snapshot is dirty.

CC/BCC hidden by default behind "Añadir CC/BCC". `Origen` selector is disabled in `edit_draft`. The overlay receives a `ComposeAccount = Pick<AccountOut, "account_id"|"provider"|"email_address"|"display_label">` array; the provider dot uses `getProviderMeta(provider).dotClass`.

### Composer state (`app/providers/draftComposer/`)
Split into three composable hooks to keep each concern small:

- `useComposerForm()` — all field state (`to/cc/bcc/subject/body/accountId`), dirty-check against an initial snapshot, `buildDraftPayload()`, `hasAnyContent()`, `seedFromDraft(draft)`, `parseRecipients()`.
- `useDraftPersistence()` — provider calls (`persistDraft`, `sendEmailNow`, `sendDraftNow`, `saveDraftNow`), `sending`/`saving`/`error` state, `providerDraftId` ref.
- `useDraftComposer(mailboxId: string | null)` — orchestrates the two above. Exposes `openForNewEmail`, `openForNewDraft({ accountId? })`, `openForEditDraft(draft)`, `closeWithX`, `handleSendEmail`, `handleSaveDraft`, `handleSendDraft`, `setRefreshCallback(fn)`. When `mailboxId` is null (e.g. on `/login`), open-handlers are no-ops.

### Global provider (`app/providers/DraftComposerGlobalProvider.tsx` + `DraftComposerContext.ts`)
Mounted at the router root (`RootLayout`). Internally reads the active mailbox id from the URL (`matchPath("/m/:mailboxId/*", ...)`) and threads it into `useDraftComposer`. Consumers read the open/close API and `setRefreshCallback` via `useDraftComposerContext()`:
- `DraftsPage` registers its `refresh()` while mounted (unified view).
- `AccountDraftsPage` registers `refresh()` only while the user is on the account-drafts route.

### Drafts list (`features/drafts/hooks/useDraftsList.ts`)
`{ drafts, accounts, loading, syncing, error, refresh, syncAndRefresh }`. `refresh()` is a pure `GET`; `syncAndRefresh()` runs `POST /drafts/sync` then `GET`. Initial load does cache-then-sync. Accepts an optional `accountId` — when provided, only drafts for that account are fetched (used by `AccountDraftsPage`).

### Selection and bulk delete
- Selection uses the generic `useSelection<DraftOut>(draftKey)` with `draftKey(d) = "${account_id}|${provider_draft_id}"`.
- `useDraftBulkDelete` — runs `DELETE` in parallel via `Promise.allSettled`, confirms via `window.confirm`, surfaces partial failures in a `UiError`, then triggers `refresh()` + `clearSelection()`.
- `DraftBulkActionsBar` replaces the toolbar when there is a selection.

### Toolbar
When nothing is selected, `DraftsTable`'s toolbar shows:
- **Sincronizar** → calls `onSync` (triggers `POST /drafts/sync` + `GET`). Spinning icon while in flight.
- **+ Nuevo borrador** → calls `onNewDraft` (opens the overlay via context).
- Counter with the current number of drafts.

Rows are clickable when `onRowClick` is provided; checkbox `stopPropagation()` so selecting never opens the overlay.

## Sidebar

`components/ui/Sidebar.tsx` is presentational. The concrete list of mailbox-scoped tabs (`inbox/sent/spam/drafts/trash`) is defined in `app/layout/mailboxNavItems.ts` and passed to `Sidebar` as the `navItems` prop from `MailboxLayout`. Adding a section never requires touching the shared component.

## Adding a New Email Provider (frontend side)

1. Extend `Provider` union in `lib/providers.ts`.
2. Add an entry to `PROVIDER_META` with the new label, friendly name, and Tailwind classes.
3. Nothing else in the frontend should need to change. `ProviderSelect`, `AccountCard`, `ComposeOverlay`, `resolveAccount`, `isGenericLabel`, and all feature pages read from the registry.

Backend changes are out of scope for this guide — see `repository_guide.md` §Extensibility.

## Extension Checklist — Adding a New Feature

- [ ] Create `features/<name>/{components,hooks,pages}/`.
- [ ] Add DTOs to `api/types/dto.ts` matching the backend schemas.
- [ ] Create `api/endpoints/<name>.ts` using `request<T>()`.
- [ ] Build hooks using `useAsync` / `useCacheThenSync` where applicable.
- [ ] Build the page + feature-specific components.
- [ ] Add the route to `app/routes/router.tsx` (use `lazy()` unless it is on the boot path).
- [ ] Update this guide with the new feature, route, and API mapping.

## Design Reference

Screen mockups live in the Pencil design file at `Ignore/PENCIL/Pantallas.pen`. Screens: Login, Create Mailbox, Connected Accounts, Compose Email, Unified Inbox, Spam Inbox, Trash Inbox, Sent Inbox, Drafts Inbox.

## Document Maintenance

Update this file when: features are added or removed, routes change, API endpoint files are created, or architectural decisions specific to this project are made. Do not modify `CLAUDE.md`.
