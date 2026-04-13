import { createBrowserRouter, RouterProvider } from "react-router-dom";

import AppShell from "../layout/AppShell";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}
