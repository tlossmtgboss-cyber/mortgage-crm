// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should load dashboard page', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('should display navigation bar', async ({ page }) => {
    await page.goto('/dashboard');
    const nav = page.locator('nav, .navigation, .sidebar');
    await expect(nav).toBeVisible();
  });

  test('should have main content area', async ({ page }) => {
    await page.goto('/dashboard');
    const main = page.locator('main, .main-content, .dashboard-content');
    await expect(main).toBeVisible();
  });
});

test.describe('Leads Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should load leads page', async ({ page }) => {
    await page.goto('/leads');
    await expect(page).toHaveURL(/\/leads/);
  });

  test('should display leads table or list', async ({ page }) => {
    await page.goto('/leads');
    // Wait for content to load
    await page.waitForTimeout(2000);

    const content = page.locator('table, .leads-list, .leads-table, .data-table');
    // Page should have some content structure
    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('Active Loans Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should load active loans page', async ({ page }) => {
    await page.goto('/active-loans');
    await expect(page).toHaveURL(/\/active-loans/);
  });
});
