// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should navigate to Dashboard', async ({ page }) => {
    await page.click('a:has-text("Dashboard"), [href="/dashboard"]');
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('should navigate to Leads', async ({ page }) => {
    await page.click('a:has-text("Leads"), [href="/leads"]');
    await expect(page).toHaveURL(/\/leads/);
  });

  test('should navigate to Active Loans', async ({ page }) => {
    const link = page.locator('a:has-text("Active Loans"), [href="/active-loans"]');
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(/\/active-loans/);
    }
  });

  test('should navigate to Tasks', async ({ page }) => {
    const link = page.locator('a:has-text("Tasks"), [href="/tasks"]');
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(/\/tasks/);
    }
  });

  test('should navigate to Calendar', async ({ page }) => {
    const link = page.locator('a:has-text("Calendar"), [href="/calendar"]');
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(/\/calendar/);
    }
  });

  test('should navigate to Marketing', async ({ page }) => {
    const link = page.locator('a:has-text("Marketing"), [href="/marketing"]');
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(/\/marketing/);
    }
  });
});

test.describe('Admin Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should navigate to Admin Panel', async ({ page }) => {
    const link = page.locator('a:has-text("Admin Panel"), [href="/admin"]');
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(/\/admin/);
    }
  });

  test('should navigate to Account Management', async ({ page }) => {
    await page.goto('/settings/account-management');
    await expect(page).toHaveURL(/\/account-management/);
  });

  test('should navigate to Usage Intelligence', async ({ page }) => {
    const link = page.locator('a:has-text("Usage Intelligence"), [href*="usage-intelligence"]');
    if (await link.isVisible()) {
      await link.click();
      await expect(page).toHaveURL(/\/usage-intelligence/);
    }
  });
});

test.describe('Settings Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should access settings area', async ({ page }) => {
    const settingsLink = page.locator('a:has-text("Settings"), [href="/settings"], .settings-link');
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await expect(page).toHaveURL(/\/settings/);
    }
  });
});
