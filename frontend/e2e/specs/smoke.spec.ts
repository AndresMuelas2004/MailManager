import { expect, test } from '@playwright/test';

/**
 * Smoke test — verifies the app boots, serves the login page at `/login`,
 * and does not crash the React tree on first paint. Runs without
 * authentication and without depending on the backend DB state.
 *
 * Real end-to-end flows (full Google login, inbox navigation, draft send)
 * live in sibling specs and require the pre-seeded test accounts documented
 * in `backend/tests/e2e/`.
 */
test.describe('smoke', () => {
  test('serves the login route without crashing', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/login');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator('body')).toBeVisible();

    expect(errors).toEqual([]);
  });
});
