import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './msw/server';

// Start the mock service worker before any test runs. `onUnhandledRequest:
// 'error'` turns unexpected network traffic into a loud failure instead of
// letting the request escape into the real network — a broken boundary is
// always a test bug, never a silent success.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset any per-test `server.use(...)` overrides so one test's failure
// simulation never leaks into the next one. Also unmount any component
// left over from the previous render — with `globals: false`, Testing
// Library's auto-cleanup is not wired, so we do it here.
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

// Close the server cleanly after the suite completes.
afterAll(() => server.close());
