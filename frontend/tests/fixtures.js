// @ts-check
const { test as base } = require('@playwright/test');

// Test credentials
const TEST_ADMIN = {
  email: 'admin@perenniaai.com',
  password: 'demo123',
};

// Extend base test with authenticated context
const test = base.extend({
  // Authenticated page fixture
  authenticatedPage: async ({ page }, use) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', TEST_ADMIN.email);
    await page.fill('input[type="password"]', TEST_ADMIN.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);
    await use(page);
  },

  // Storage state for reusing auth
  storageState: async ({ page }, use) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', TEST_ADMIN.email);
    await page.fill('input[type="password"]', TEST_ADMIN.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans)/);

    const storage = await page.context().storageState();
    await use(storage);
  },
});

// Helper functions
async function login(page, email = TEST_ADMIN.email, password = TEST_ADMIN.password) {
  await page.goto('/login');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(dashboard|leads|active-loans)/);
}

async function logout(page) {
  const userMenu = page.locator('[data-testid="user-menu"], .user-menu, .profile-dropdown');
  if (await userMenu.isVisible()) {
    await userMenu.click();
  }
  const logoutButton = page.locator('button:has-text("Logout"), a:has-text("Logout")');
  if (await logoutButton.isVisible()) {
    await logoutButton.click();
  }
}

async function clearAuth(page) {
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
}

async function waitForApiResponse(page, urlPattern) {
  return page.waitForResponse((response) =>
    response.url().includes(urlPattern) && response.status() === 200
  );
}

module.exports = {
  test,
  TEST_ADMIN,
  login,
  logout,
  clearAuth,
  waitForApiResponse,
};
