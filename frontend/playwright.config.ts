import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the frontend end-to-end suite.
 *
 * End-to-end tests run against a real, running backend — either a local
 * instance on port 8000 or a deterministic staging environment. Override
 * `PLAYWRIGHT_BASE_URL` and `PLAYWRIGHT_API_BASE_URL` to point the suite
 * elsewhere.
 *
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './e2e/specs',
  outputDir: './e2e/.artifacts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
