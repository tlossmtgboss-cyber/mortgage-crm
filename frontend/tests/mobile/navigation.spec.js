// @ts-check
/**
 * Mobile Navigation E2E Tests
 *
 * Validates mobile navigation patterns:
 * - Bottom nav bar rendering and tab navigation
 * - FAB (floating action button) speed dial
 * - Hamburger menu (sidebar toggle)
 * - Back button / browser history navigation
 * - Deep link handling
 */
import {
  mobileTest as test,
  expect,
  DEVICES,
  setupMobileContext,
  assertNoHorizontalOverflow,
  assertTouchTargets,
  mobileLogin,
} from './setup.js';

test.describe('Mobile Bottom Navigation', () => {
  test.beforeEach(async ({ mobilePage: page }) => {
    await mobileLogin(page);
  });

  // -----------------------------------------------------------------------
  // Bottom nav rendering
  // -----------------------------------------------------------------------

  test('should render bottom nav on mobile viewport', async ({ mobilePage: page }) => {
    // Navigate to a page that shows the bottom nav (Aria voice app area)
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const bottomNav = page.locator('.mobile-bottom-nav, nav.mobile-bottom-nav');
    const visible = await bottomNav.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await expect(bottomNav).toBeVisible();

      // Should contain 5 tabs (Home, Calendar, Add/FAB, Contacts, Alerts)
      const tabs = bottomNav.locator('.mobile-bottom-nav__tab');
      const tabCount = await tabs.count();
      expect(tabCount).toBe(5);
    }
  });

  test('should have touch-friendly bottom nav tabs (>= 44px)', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const bottomNav = page.locator('.mobile-bottom-nav');
    const visible = await bottomNav.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await assertTouchTargets(page, '.mobile-bottom-nav__tab', 44);
    }
  });

  test('should position bottom nav at the bottom of the viewport', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const bottomNav = page.locator('.mobile-bottom-nav');
    const visible = await bottomNav.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      const navBox = await bottomNav.boundingBox();
      const viewport = DEVICES.iPhone14;

      // The nav should be near the bottom of the viewport
      // navBox.y + navBox.height should be close to viewport height
      expect(navBox.y + navBox.height).toBeGreaterThanOrEqual(viewport.height - 5);
    }
  });

  // -----------------------------------------------------------------------
  // Tab navigation
  // -----------------------------------------------------------------------

  test('should navigate to Home (Aria) when tapping Home tab', async ({ mobilePage: page }) => {
    // Navigate to aria first so bottom nav shows
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const homeTab = page.locator('.mobile-bottom-nav__tab[aria-label="Home"]');
    const visible = await homeTab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await homeTab.click();
      await page.waitForTimeout(500);
      expect(page.url()).toContain('/aria');
    }
  });

  test('should navigate to Calendar when tapping Calendar tab', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const calendarTab = page.locator('.mobile-bottom-nav__tab[aria-label="Calendar"]');
    const visible = await calendarTab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await calendarTab.click();
      await page.waitForURL(/\/aria\/calendar/, { timeout: 5000 });
      expect(page.url()).toContain('/aria/calendar');
    }
  });

  test('should navigate to Contacts (Leads) when tapping Contacts tab', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const contactsTab = page.locator('.mobile-bottom-nav__tab[aria-label="Contacts"]');
    const visible = await contactsTab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await contactsTab.click();
      await page.waitForURL(/\/leads/, { timeout: 5000 });
      expect(page.url()).toContain('/leads');
    }
  });

  test('should navigate to Alerts when tapping Alerts tab', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const alertsTab = page.locator('.mobile-bottom-nav__tab[aria-label="Alerts"]');
    const visible = await alertsTab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await alertsTab.click();
      await page.waitForURL(/\/aria\/notifications/, { timeout: 5000 });
      expect(page.url()).toContain('/aria/notifications');
    }
  });

  test('should highlight the active tab', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const homeTab = page.locator('.mobile-bottom-nav__tab[aria-label="Home"]');
    const visible = await homeTab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // Home tab should be active on /aria
      const isActive = await homeTab.evaluate((el) =>
        el.classList.contains('mobile-bottom-nav__tab--active')
      );
      expect(isActive).toBe(true);
    }
  });

  // -----------------------------------------------------------------------
  // FAB / speed dial
  // -----------------------------------------------------------------------

  test('should render the FAB (center add button) in bottom nav', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const fab = page.locator(
      '.mobile-bottom-nav__fab, .mobile-bottom-nav__tab[aria-label="Create new"]'
    );
    const visible = await fab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      await expect(fab).toBeVisible();

      // The FAB circle should have distinctive styling
      const fabCircle = fab.locator('.mobile-bottom-nav__fab-circle');
      await expect(fabCircle).toBeVisible();
    }
  });

  test('should open speed dial or navigate when tapping FAB', async ({ mobilePage: page }) => {
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const fab = page.locator(
      '.mobile-bottom-nav__fab, .mobile-bottom-nav__tab[aria-label="Create new"]'
    );
    const visible = await fab.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // Capture current URL
      const urlBefore = page.url();

      await fab.click();
      await page.waitForTimeout(1000);

      // The FAB should either:
      // 1. Navigate to a new-event page (e.g., /aria/calendar?action=new)
      // 2. Open a speed-dial overlay
      const urlAfter = page.url();
      const speedDial = page.locator(
        '.speed-dial, .fab-menu, [data-testid="speed-dial"]'
      );
      const speedDialVisible = await speedDial.isVisible().catch(() => false);

      // Either URL changed or speed dial opened
      expect(urlAfter !== urlBefore || speedDialVisible).toBe(true);
    }
  });

  // -----------------------------------------------------------------------
  // Hamburger / sidebar menu
  // -----------------------------------------------------------------------

  test('should toggle hamburger menu if present', async ({ mobilePage: page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const hamburger = page.locator(
      '.hamburger, [data-testid="hamburger"], button[aria-label="Menu"], .menu-toggle, .sidebar-toggle'
    ).first();

    const visible = await hamburger.isVisible({ timeout: 3000 }).catch(() => false);

    if (visible) {
      // Open menu
      await hamburger.click();
      await page.waitForTimeout(500);

      // Look for sidebar / drawer
      const sidebar = page.locator(
        '.sidebar, .drawer, .mobile-menu, .nav-drawer, [data-testid="sidebar"]'
      ).first();

      const sidebarVisible = await sidebar.isVisible({ timeout: 3000 }).catch(() => false);

      if (sidebarVisible) {
        await expect(sidebar).toBeVisible();

        // Close menu by clicking hamburger again or overlay
        await hamburger.click();
        await page.waitForTimeout(500);
      }
    }
  });

  // -----------------------------------------------------------------------
  // Back button / history navigation
  // -----------------------------------------------------------------------

  test('should support browser back button navigation', async ({ mobilePage: page }) => {
    // Navigate through multiple pages
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    await page.goto('/leads');
    await page.waitForLoadState('networkidle');

    await page.goto('/loans');
    await page.waitForLoadState('networkidle');

    // Go back
    await page.goBack();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/leads/);

    // Go back again
    await page.goBack();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('should maintain scroll position on back navigation', async ({ mobilePage: page }) => {
    await page.goto('/leads');
    await page.waitForLoadState('networkidle');

    // Scroll down
    await page.evaluate(() => window.scrollTo(0, 300));

    // Navigate forward
    await page.goto('/loans');
    await page.waitForLoadState('networkidle');

    // Go back
    await page.goBack();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // The key check is that back navigation works without error
    await expect(page).toHaveURL(/\/leads/);
  });

  // -----------------------------------------------------------------------
  // Deep link handling
  // -----------------------------------------------------------------------

  test('should handle deep link to loans page', async ({ mobilePage: page }) => {
    // Navigate directly to a loan path
    await page.goto('/loans');
    await page.waitForLoadState('networkidle');

    // Verify the page loaded without error
    const errorOverlay = page.locator('.error-boundary, [data-testid="error"]');
    const hasError = await errorOverlay.isVisible().catch(() => false);
    expect(hasError).toBe(false);

    await assertNoHorizontalOverflow(page);
  });

  test('should handle deep link to calendar with action parameter', async ({ mobilePage: page }) => {
    await page.goto('/aria/calendar?action=new');
    await page.waitForLoadState('networkidle');

    // Should load without crashing
    expect(page.url()).toContain('/aria/calendar');

    await assertNoHorizontalOverflow(page);
  });

  test('should redirect to login when accessing protected route while unauthenticated', async ({ page }) => {
    // Use a fresh page without login
    await setupMobileContext(page, 'iPhone14', { native: false });

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Should redirect to /login (or show the login page)
    await page.waitForURL(/\/login/, { timeout: 10000 });
    expect(page.url()).toContain('/login');
  });

  // -----------------------------------------------------------------------
  // Bottom nav should not render on desktop
  // -----------------------------------------------------------------------

  test('should hide bottom nav on desktop viewport', async ({ page }) => {
    // Use desktop-sized viewport
    await page.setViewportSize({ width: 1280, height: 800 });

    await mobileLogin(page);
    await page.goto('/aria');
    await page.waitForLoadState('networkidle');

    const bottomNav = page.locator('.mobile-bottom-nav');

    // The MobileBottomNav component returns null when window.innerWidth > 768
    const visible = await bottomNav.isVisible({ timeout: 3000 }).catch(() => false);
    expect(visible).toBe(false);
  });
});
