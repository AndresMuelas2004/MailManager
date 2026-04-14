import { Suspense } from "react";
import { Outlet } from "react-router-dom";

import DraftComposerGlobalProvider from "../providers/DraftComposerGlobalProvider";
import Spinner from "../../components/common/Spinner";

export default function RootLayout() {
  return (
    <DraftComposerGlobalProvider>
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center">
            <Spinner />
          </div>
        }
      >
        <Outlet />
      </Suspense>
    </DraftComposerGlobalProvider>
  );
}
