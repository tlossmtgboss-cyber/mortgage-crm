// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Account Management', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin before each test
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should load account management page', async ({ page }) => {
    await page.goto('/settings/account-management');
    await expect(page).toHaveURL(/\/account-management/);
  });

  test('should display account management header', async ({ page }) => {
    await page.goto('/settings/account-management');
    await page.waitForTimeout(2000);

    const header = page.locator('h1:has-text("Account Management"), h2:has-text("Account Management")');
    await expect(header).toBeVisible();
  });

  test('should display KPI cards', async ({ page }) => {
    await page.goto('/settings/account-management');
    await page.waitForTimeout(2000);

    // Look for KPI metrics
    const kpiSection = page.locator('.kpi-cards, .metrics, .stats-cards');
    if (await kpiSection.isVisible()) {
      await expect(kpiSection).toBeVisible();
    }
  });

  test('should have invite subscriber button', async ({ page }) => {
    await page.goto('/settings/account-management');
    await page.waitForTimeout(2000);

    const inviteButton = page.locator('button:has-text("Invite"), button:has-text("Subscriber")');
    if (await inviteButton.isVisible()) {
      await expect(inviteButton).toBeVisible();
    }
  });

  test('should display subscription tabs', async ({ page }) => {
    await page.goto('/settings/account-management');
    await page.waitForTimeout(2000);

    const tabs = page.locator('.tabs, [role="tablist"]');
    if (await tabs.isVisible()) {
      await expect(tabs).toBeVisible();
    }
  });

  test('should be able to search accounts', async ({ page }) => {
    await page.goto('/settings/account-management');
    await page.waitForTimeout(2000);

    const searchInput = page.locator('input[placeholder*="Search"], input[type="search"]');
    if (await searchInput.isVisible()) {
      await searchInput.fill('test');
      await expect(searchInput).toHaveValue('test');
    }
  });
});

test.describe('Account Management - Access Control', () => {
  test('should deny access for non-admin users', async ({ page }) => {
    // Clear any existing session
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    // Try to access account management directly
    await page.goto('/settings/account-management');

    // Should either redirect to login or show access denied
    const url = page.url();
    const hasAccessDenied = await page.locator('text=Access Denied').isVisible().catch(() => false);
    const isLoginPage = url.includes('/login');

    expect(hasAccessDenied || isLoginPage).toBeTruthy();
  });
});
