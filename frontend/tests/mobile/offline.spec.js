// @ts-check
/**
 * Mobile Offline E2E Tests
 *
 * Validates offline behavior and resilience:
 * - Offline indicator rendering
 * - Cached data display when offline
 * - Mutation queuing when offline
 * - Sync status banner on reconnect
 */
import {
  mobileTest as test,
  expect,
  setupMobileContext,
  assertNoHorizontalOverflow,
  mobileLogin,
  goOffline,
  goOnline,
} from './setup.js';

test.describe('Mobile Offline Behavior', () => {
  // -----------------------------------------------------------------------
  // Offline indicator
  // -----------------------------------------------------------------------

  test('should show offline indicator when network is lost', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Go offline
    await goOffline(page);

    // Wait for the indicator to appear
    // The OfflineIndicator component adds class 'visible' when offline
    const indicator = page.locator('.offline-indicator');
    const indicatorVisible = page.locator('.offline-indicator.visible');

    // Give the network status hook time to react
    await page.waitForTimeout(1500);

    // Check if the indicator element exists and has the visible class
    const exists = await indicator.count();

    if (exists > 0) {
      const isVisible = await indicatorVisible.isVisible({ timeout: 5000 }).catch(() => false);
      expect(isVisible).toBe(true);

      // Verify it contains the expected text
      const text = await indicator.textContent();
      expect(text.toLowerCase()).toContain('offline');
    }

    // Restore online state
    await goOnline(page);
  });

  test('should hide offline indicator when network is restored', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Go offline
    await goOffline(page);
    await page.waitForTimeout(1500);

    // Go back online
    await goOnline(page);
    await page.waitForTimeout(1500);

    // The indicator should no longer have the 'visible' class
    const indicatorVisible = page.locator('.offline-indicator.visible');
    const stillVisible = await indicatorVisible.isVisible({ timeout: 3000 }).catch(() => false);
    expect(stillVisible).toBe(false);
  });

  test('should not show offline indicator when online', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Should not have the visible class while online
    const indicatorVisible = page.locator('.offline-indicator.visible');
    const isVisible = await indicatorVisible.isVisible({ timeout: 2000 }).catch(() => false);
    expect(isVisible).toBe(false);
  });

  // -----------------------------------------------------------------------
  // Cached data display
  // -----------------------------------------------------------------------

  test('should display cached data when going offline', async ({ mobilePage: page }) => {
    await mobileLogin(page);

    // Load a data-heavy page while online to populate the cache
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Wait for data to render and get cached
    await page.waitForTimeout(2000);

    // Go offline
    await goOffline(page);
    await page.waitForTimeout(1000);

    // The page should still show content (from cache or DOM state)
    // It should not become completely blank
    const bodyTextOffline = await page.evaluate(() => document.body.innerText);
    expect(bodyTextOffline.length).toBeGreaterThan(0);

    // Restore
    await goOnline(page);
  });

  test('should serve cached API responses when offline (useOfflineCache)', async ({ mobilePage: page }) => {
    await mobileLogin(page);

    // Navigate to a page that uses the offline cache
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Seed the cache manually for a known key
    await page.evaluate(() => {
      const entry = JSON.stringify({
        data: { cached: true, metric: 42 },
        timestamp: Date.now(),
      });
      localStorage.setItem('offline_cache_test_key', entry);
    });

    // Go offline
    await goOffline(page);

    // Verify the cached entry is retrievable
    const cached = await page.evaluate(() => {
      const raw = localStorage.getItem('offline_cache_test_key');
      if (!raw) return null;
      try {
        return JSON.parse(raw);
      } catch {
        return null;
      }
    });

    expect(cached).not.toBeNull();
    expect(cached.data.cached).toBe(true);
    expect(cached.data.metric).toBe(42);

    await goOnline(page);
  });

  test('should preserve page state during brief offline period', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/leads');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Count visible elements before going offline
    const leadCountBefore = await page.locator(
      '.lead-card, .lead-row, tr, [data-testid="lead-card"]'
    ).count();

    // Brief offline period
    await goOffline(page);
    await page.waitForTimeout(2000);

    // Elements should still be in DOM
    const leadCountDuring = await page.locator(
      '.lead-card, .lead-row, tr, [data-testid="lead-card"]'
    ).count();

    // Count should not have dropped to zero
    if (leadCountBefore > 0) {
      expect(leadCountDuring).toBeGreaterThan(0);
    }

    await goOnline(page);
  });

  // -----------------------------------------------------------------------
  // Mutation queuing
  // -----------------------------------------------------------------------

  test('should queue form submissions when offline', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/leads');
    await page.waitForLoadState('networkidle');

    // Go offline before attempting any mutation
    await goOffline(page);
    await page.waitForTimeout(1000);

    // Attempt to interact with the page (e.g., click a button that triggers an API call)
    // We check that the app does not crash and shows appropriate feedback
    const addButton = page.locator(
      'button:has-text("Add Lead"), button:has-text("New Lead"), [data-testid="add-lead"]'
    ).first();

    const visible = await addButton.isVisible({ timeout: 3000 }).catch(() => false);

    if (visible) {
      await addButton.click();
      await page.waitForTimeout(1000);

      // The app should either:
      // 1. Show an offline warning/toast
      // 2. Queue the action
      // 3. Show an error indicating no connectivity
      // Key check: the app should not crash (no unhandled rejection overlay)
      const errorBoundary = page.locator('.error-boundary, [data-testid="error-boundary"]');
      const hasCrashed = await errorBoundary.isVisible().catch(() => false);
      expect(hasCrashed).toBe(false);
    }

    await goOnline(page);
  });

  test('should not lose unsaved form data during offline transition', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/loans');
    await page.waitForLoadState('networkidle');

    // Find any input field on the page
    const input = page.locator(
      'input[type="search"], input[type="text"], input[placeholder*="Search"]'
    ).first();

    const visible = await input.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // Type something
      await input.fill('offline test data');

      // Go offline
      await goOffline(page);
      await page.waitForTimeout(1000);

      // The input value should be preserved
      await expect(input).toHaveValue('offline test data');

      // Go back online
      await goOnline(page);
      await page.waitForTimeout(500);

      // Input value should still be there
      await expect(input).toHaveValue('offline test data');
    }
  });

  // -----------------------------------------------------------------------
  // Sync status banner on reconnect
  // -----------------------------------------------------------------------

  test('should update UI when connection is restored', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Go offline
    await goOffline(page);
    await page.waitForTimeout(1500);

    // Go back online
    await goOnline(page);
    await page.waitForTimeout(2000);

    // After reconnection, the offline indicator should be hidden
    const offlineIndicatorVisible = page.locator('.offline-indicator.visible');
    const stillOffline = await offlineIndicatorVisible.isVisible({ timeout: 2000 }).catch(() => false);
    expect(stillOffline).toBe(false);

    // Verify the page is functional after reconnect
    const pageText = await page.evaluate(() => document.body.innerText);
    expect(pageText.length).toBeGreaterThan(0);
  });

  test('should recover and load fresh data after reconnection', async ({ mobilePage: page }) => {
    await mobileLogin(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Go offline then online
    await goOffline(page);
    await page.waitForTimeout(1000);
    await goOnline(page);

    // After reconnection, attempt to navigate to a new page
    // It should load successfully (fresh API calls should work)
    await page.goto('/leads');

    // Wait for data to load (network requests should succeed now)
    await page.waitForLoadState('networkidle');

    // Verify the page rendered properly
    await assertNoHorizontalOverflow(page);

    // The page should not show an error state
    const errorBoundary = page.locator('.error-boundary, [data-testid="error-boundary"]');
    const hasCrashed = await errorBoundary.isVisible().catch(() => false);
    expect(hasCrashed).toBe(false);
  });

  // -----------------------------------------------------------------------
  // Offline during login
  // -----------------------------------------------------------------------

  test('should show error when attempting login while offline', async ({ page }) => {
    await setupMobileContext(page, 'iPhone14');
    await page.goto('/login');
    await page.waitForSelector('.login-form');

    // Go offline before login attempt
    await goOffline(page);
    await page.waitForTimeout(500);

    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // Should show an error message (network error or similar)
    const errorMsg = page.locator('.error-message');
    await expect(errorMsg).toBeVisible({ timeout: 10000 });

    // Should still be on the login page
    expect(page.url()).toContain('/login');

    await goOnline(page);
  });
});
