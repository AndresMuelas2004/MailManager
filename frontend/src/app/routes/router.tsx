import { createBrowserRouter, RouterProvider } from "react-router-dom";

import AppShell from "../layout/AppShell";
import InboxPage from "../../pages/InboxPage";
import UsersPage from "../../pages/UsersPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <UsersPage /> },
      { path: "m/:mailboxId/inbox", element: <InboxPage /> },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}

