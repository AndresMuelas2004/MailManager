import { createBrowserRouter, RouterProvider } from "react-router-dom";

import AppShell from "../layout/AppShell";
import RequireAuth from "./RequireAuth";
import LoginPage from "../../features/auth/pages/LoginPage";
import CreateMailboxPage from "../../features/mailboxes/pages/CreateMailboxPage";

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <CreateMailboxPage /> },
        ],
      },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}
