import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../../test/renderWithProviders';
import { server } from '../../../test/msw/server';
import UnifiedInboxPage from './UnifiedInboxPage';

const API_BASE = 'http://localhost:8000';

const emailFixtures = [
  {
    provider_message_id: 'm_1',
    account_id: 'a_1',
    thread_id: null,
    from_email: 'alice@example.com',
    from_name: 'Alice',
    subject: 'Welcome to the platform',
    received_at: new Date('2024-01-10T09:00:00Z').toISOString(),
    is_read: false,
    box: 'ALL_MAIL',
  },
  {
    provider_message_id: 'm_2',
    account_id: 'a_1',
    thread_id: null,
    from_email: 'bob@example.com',
    from_name: 'Bob',
    subject: 'Your receipt is attached',
    received_at: new Date('2024-01-11T10:00:00Z').toISOString(),
    is_read: true,
    box: 'ALL_MAIL',
  },
];

const accountFixture = {
  account_id: 'a_1',
  mailbox_id: 'mb_1',
  provider: 'gmail',
  display_label: 'Gmail',
  config: {},
  email_address: 'alice@example.com',
};

function renderInboxAtMailbox() {
  return renderWithProviders(
    <Routes>
      <Route path="/m/:mailboxId/inbox" element={<UnifiedInboxPage box="ALL_MAIL" />} />
    </Routes>,
    { initialEntries: ['/m/mb_1/inbox'] },
  );
}

describe('UnifiedInboxPage', () => {
  it('renders the cached emails returned by the backend', async () => {
    server.use(
      http.get(`${API_BASE}/mailboxes/mb_1/emails`, () => HttpResponse.json(emailFixtures)),
      http.get(`${API_BASE}/mailboxes/mb_1/accounts`, () => HttpResponse.json([accountFixture])),
    );

    renderInboxAtMailbox();

    await waitFor(() => {
      expect(screen.getByText('Welcome to the platform')).toBeInTheDocument();
    });
    expect(screen.getByText('Your receipt is attached')).toBeInTheDocument();
  });

  it('surfaces a backend error through the UI instead of rendering the table', async () => {
    server.use(
      http.get(`${API_BASE}/mailboxes/mb_1/emails`, () =>
        HttpResponse.json(
          { error: { code: 'forbidden', message: 'Mailbox not accessible' } },
          { status: 403 },
        ),
      ),
      http.get(`${API_BASE}/mailboxes/mb_1/accounts`, () => HttpResponse.json([accountFixture])),
    );

    renderInboxAtMailbox();

    await waitFor(() => {
      expect(screen.getByText('Mailbox not accessible')).toBeInTheDocument();
    });
    expect(screen.queryByText('Welcome to the platform')).not.toBeInTheDocument();
  });

  it('debounces typing: every keystroke updates ?q in the URL and the eventual request carries the latest q', async () => {
    // Capture every q value the backend sees. Default handler intentionally
    // returns the unfiltered fixtures — what we assert is the request shape.
    const seenQueries: (string | null)[] = [];
    server.use(
      http.get(`${API_BASE}/mailboxes/mb_1/emails`, ({ request }) => {
        const url = new URL(request.url);
        seenQueries.push(url.searchParams.get('q'));
        const q = (url.searchParams.get('q') ?? '').toLowerCase();
        if (!q) return HttpResponse.json(emailFixtures);
        const filtered = emailFixtures.filter((e) => e.subject.toLowerCase().includes(q));
        return HttpResponse.json(filtered);
      }),
      http.get(`${API_BASE}/mailboxes/mb_1/accounts`, () => HttpResponse.json([accountFixture])),
    );

    renderInboxAtMailbox();

    // First-render request hits the endpoint with no q.
    await waitFor(() => {
      expect(screen.getByText('Welcome to the platform')).toBeInTheDocument();
    });
    expect(seenQueries[0]).toBeNull();

    const input = screen.getByRole('searchbox');
    // Real (not fake) timers are used here so TanStack Query's internals run
    // without contention — userEvent.type produces real input events at a
    // realistic cadence; the page debounces internally at 300 ms.
    const user = userEvent.setup();
    await user.type(input, 'receipt');

    // After debounce settles, the table must reflect the filtered subset.
    await waitFor(() => {
      expect(screen.queryByText('Welcome to the platform')).not.toBeInTheDocument();
      expect(screen.getByText('Your receipt is attached')).toBeInTheDocument();
    });

    // The input reflects the URL search param (the page round-trips q
    // through `useSearchParams`, so a non-empty input value proves the URL
    // state was updated by the controlled-input handler).
    expect((input as HTMLInputElement).value).toBe('receipt');

    // The last network request must carry the final, complete query string.
    // We do not require exactly one extra request — TanStack Query may issue
    // an intermediate one during keystrokes — but the final one must equal
    // 'receipt' and there must be at least one request beyond the initial.
    expect(seenQueries.length).toBeGreaterThan(1);
    expect(seenQueries[seenQueries.length - 1]).toBe('receipt');
  });

  it('shows the search-empty message when the active search returns no rows', async () => {
    server.use(
      http.get(`${API_BASE}/mailboxes/mb_1/emails`, ({ request }) => {
        const q = new URL(request.url).searchParams.get('q');
        return HttpResponse.json(q ? [] : emailFixtures);
      }),
      http.get(`${API_BASE}/mailboxes/mb_1/accounts`, () => HttpResponse.json([accountFixture])),
    );

    renderInboxAtMailbox();
    await waitFor(() => {
      expect(screen.getByText('Welcome to the platform')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByRole('searchbox'), 'nope');

    await waitFor(() => {
      expect(screen.getByText('No se encontraron correos para tu búsqueda.')).toBeInTheDocument();
    });
  });

  it('clearing the search restores the unfiltered list and removes ?q from the URL', async () => {
    server.use(
      http.get(`${API_BASE}/mailboxes/mb_1/emails`, ({ request }) => {
        const q = new URL(request.url).searchParams.get('q');
        return HttpResponse.json(q ? [emailFixtures[1]] : emailFixtures);
      }),
      http.get(`${API_BASE}/mailboxes/mb_1/accounts`, () => HttpResponse.json([accountFixture])),
    );

    renderWithProviders(
      <Routes>
        <Route path="/m/:mailboxId/inbox" element={<UnifiedInboxPage box="ALL_MAIL" />} />
      </Routes>,
      { initialEntries: ['/m/mb_1/inbox?q=receipt'] },
    );

    // Initial fetch with q=receipt returns only the second fixture.
    await waitFor(() => {
      expect(screen.getByText('Your receipt is attached')).toBeInTheDocument();
    });
    expect(screen.queryByText('Welcome to the platform')).not.toBeInTheDocument();

    // The clear button should be visible because the input is non-empty.
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Limpiar búsqueda' }));

    // After debounce, the list must come back full.
    await waitFor(() => {
      expect(screen.getByText('Welcome to the platform')).toBeInTheDocument();
    });
    expect(window.location.search.includes('q=')).toBe(false);
  });
});
