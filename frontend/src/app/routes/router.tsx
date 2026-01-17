import { createBrowserRouter, RouterProvider } from "react-router-dom";

import AppShell from "../layout/AppShell";
import InboxPage from "../../pages/InboxPage";
import MailboxesPage from "../../pages/MailboxesPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <MailboxesPage /> },
      { path: "m/:mailboxId/inbox", element: <InboxPage /> },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

