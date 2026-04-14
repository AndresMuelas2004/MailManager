import { createBrowserRouter, RouterProvider } from "react-router-dom";

import RequireAuth from "./RequireAuth";
import LoginPage from "../../features/auth/pages/LoginPage";
import CreateMailboxPage from "../../features/mailboxes/pages/CreateMailboxPage";
import MailboxGatewayPage from "../../features/mailboxes/pages/MailboxGatewayPage";
import MailboxLayout from "../layout/MailboxLayout";
import ConnectedAccountsPage from "../../features/accounts/pages/ConnectedAccountsPage";
import EmailListPage from "../../features/emails/pages/EmailListPage";
import DraftsPage from "../../features/drafts/pages/DraftsPage";

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: <RequireAuth />,
    children: [
      { index: true, element: <MailboxGatewayPage /> },
      { path: "create-mailbox", element: <CreateMailboxPage /> },
      {
        path: "m/:mailboxId",
        element: <MailboxLayout />,
        children: [
          { path: "accounts", element: <ConnectedAccountsPage /> },
          { path: "inbox", element: <EmailListPage box="ALL_MAIL" /> },
          { path: "sent", element: <EmailListPage box="SENT" /> },
          { path: "spam", element: <EmailListPage box="SPAM" /> },
          { path: "trash", element: <EmailListPage box="TRASH" /> },
          { path: "drafts", element: <DraftsPage /> },
          { path: "account/:accountId", element: <EmailListPage box="ALL_MAIL" /> },
        ],
      },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}
