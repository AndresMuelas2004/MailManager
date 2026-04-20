import { screen, waitFor } from '@testing-library/react';
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
});
