import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './msw/server';

// Start the mock service worker before any test runs. `onUnhandledRequest:
// 'error'` turns unexpected network traffic into a loud failure instead of
// letting the request escape into the real network — a broken boundary is
// always a test bug, never a silent success.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset any per-test `server.use(...)` overrides so one test's failure
// simulation never leaks into the next one.
afterEach(() => server.resetHandlers());

// Close the server cleanly after the suite completes.
afterAll(() => server.close());
