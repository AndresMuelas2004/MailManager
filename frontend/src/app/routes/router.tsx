import { lazy } from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';

import RequireAuth from './RequireAuth';
import RootLayout from '../layout/RootLayout';
import MailboxLayout from '../layout/MailboxLayout';
import LoginPage from '../../features/auth/pages/LoginPage';
import CreateMailboxPage from '../../features/mailboxes/pages/CreateMailboxPage';
import MailboxGatewayPage from '../../features/mailboxes/pages/MailboxGatewayPage';

const ConnectedAccountsPage = lazy(
  () => import('../../features/accounts/pages/ConnectedAccountsPage'),
);
const UnifiedInboxPage = lazy(() => import('../../features/emails/pages/UnifiedInboxPage'));
const AccountInboxPage = lazy(() => import('../../features/emails/pages/AccountInboxPage'));
const DraftsPage = lazy(() => import('../../features/drafts/pages/DraftsPage'));
const AccountDraftsPage = lazy(() => import('../../features/drafts/pages/AccountDraftsPage'));

const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      {
        path: '/',
        element: <RequireAuth />,
        children: [
          { index: true, element: <MailboxGatewayPage /> },
          { path: 'create-mailbox', element: <CreateMailboxPage /> },
          {
            path: 'm/:mailboxId',
            element: <MailboxLayout />,
            children: [
              { path: 'accounts', element: <ConnectedAccountsPage /> },
              { path: 'inbox', element: <UnifiedInboxPage box="ALL_MAIL" /> },
              { path: 'sent', element: <UnifiedInboxPage box="SENT" /> },
              { path: 'spam', element: <UnifiedInboxPage box="SPAM" /> },
              { path: 'trash', element: <UnifiedInboxPage box="TRASH" /> },
              { path: 'drafts', element: <DraftsPage /> },
              {
                path: 'account/:accountId',
                children: [
                  { index: true, element: <Navigate to="inbox" replace /> },
                  { path: 'inbox', element: <AccountInboxPage box="ALL_MAIL" /> },
                  { path: 'sent', element: <AccountInboxPage box="SENT" /> },
                  { path: 'spam', element: <AccountInboxPage box="SPAM" /> },
                  { path: 'trash', element: <AccountInboxPage box="TRASH" /> },
                  { path: 'drafts', element: <AccountDraftsPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}
