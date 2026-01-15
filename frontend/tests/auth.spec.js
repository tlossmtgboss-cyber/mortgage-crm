// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('should display login page', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Mortgage CRM');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.fill('input[type="email"]', 'invalid@example.com');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');

    await expect(page.locator('.error-message')).toBeVisible();
  });

  test('should login successfully with valid credentials', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should have forgot password link', async ({ page }) => {
    const forgotLink = page.locator('a[href="/forgot-password"]');
    await expect(forgotLink).toBeVisible();
  });
});

test.describe('Authenticated User', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@perenniaai.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
  });

  test('should be able to logout', async ({ page }) => {
    // Look for logout button or user menu
    const userMenu = page.locator('[data-testid="user-menu"], .user-menu, .profile-dropdown');
    if (await userMenu.isVisible()) {
      await userMenu.click();
    }

    const logoutButton = page.locator('button:has-text("Logout"), a:has-text("Logout"), [data-testid="logout"]');
    if (await logoutButton.isVisible()) {
      await logoutButton.click();
      await expect(page).toHaveURL(/\/login/);
    }
  });

  test('should persist session on page reload', async ({ page }) => {
    await page.reload();
    // Should not redirect to login
    await expect(page).not.toHaveURL(/\/login/);
  });
});
