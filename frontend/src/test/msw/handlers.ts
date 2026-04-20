import { http, HttpResponse } from 'msw';

const API_BASE = 'http://localhost:8000';

/**
 * Default happy-path handlers for every backend endpoint exercised in
 * integration tests. Individual specs override specific routes with
 * `server.use(...)` to simulate errors, empty states or edge cases.
 *
 * Handlers here must stay in sync with the backend's API contract —
 * when a new endpoint is added, add a happy-path handler for it.
 */
export const handlers = [
  // Auth
  http.post(`${API_BASE}/auth/google`, () =>
    HttpResponse.json({
      user: { user_id: 'u_test', email: 'tester@example.com', name: 'Tester', avatar_url: null },
      message: 'Logged in',
    }),
  ),
  http.get(`${API_BASE}/auth/me`, () =>
    HttpResponse.json({
      user_id: 'u_test',
      email: 'tester@example.com',
      name: 'Tester',
      avatar_url: null,
    }),
  ),
  http.post(`${API_BASE}/auth/logout`, () => HttpResponse.json({ message: 'Logged out' })),
  http.delete(`${API_BASE}/auth/me`, () => HttpResponse.json({ message: 'Deleted' })),

  // Mailboxes
  http.get(`${API_BASE}/mailboxes`, () => HttpResponse.json([])),
  http.post(`${API_BASE}/mailboxes`, () =>
    HttpResponse.json({
      mailbox_id: 'mb_test',
      display_name: 'Test mailbox',
      owner_user_id: 'u_test',
      created_at: new Date().toISOString(),
    }),
  ),

  // Accounts
  http.get(`${API_BASE}/mailboxes/:mailboxId/accounts`, () => HttpResponse.json([])),

  // Emails
  http.get(`${API_BASE}/mailboxes/:mailboxId/emails`, () => HttpResponse.json([])),
  http.post(`${API_BASE}/mailboxes/:mailboxId/emails/sync-metadata`, () =>
    HttpResponse.json({ total_synced: 0, accounts: [] }),
  ),
  http.post(`${API_BASE}/mailboxes/:mailboxId/emails/move-to-trash`, () =>
    HttpResponse.json({ affected: 0 }),
  ),
  http.post(`${API_BASE}/mailboxes/:mailboxId/emails/spam`, () =>
    HttpResponse.json({ moved_count: 0, accounts: [] }),
  ),
  http.post(`${API_BASE}/mailboxes/:mailboxId/emails/restore-from-spam`, () =>
    HttpResponse.json({ moved_count: 0, accounts: [] }),
  ),
  http.patch(`${API_BASE}/mailboxes/:mailboxId/emails/read-status`, () =>
    HttpResponse.json({ updated_count: 0, accounts: [] }),
  ),

  // Drafts
  http.get(`${API_BASE}/mailboxes/:mailboxId/drafts`, () => HttpResponse.json([])),
  http.post(`${API_BASE}/mailboxes/:mailboxId/drafts/sync`, () =>
    HttpResponse.json({ total_synced: 0, accounts: [] }),
  ),
];
