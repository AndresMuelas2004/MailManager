import { createBrowserRouter, RouterProvider } from "react-router-dom";

import AppShell from "../layout/AppShell";
import RequireAuth from "./RequireAuth";
import LoginPage from "../../features/auth/pages/LoginPage";

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
        children: [],
      },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}
