// @ts-check
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  timeout: 60000,
  use: {
    baseURL: process.env.TEST_BASE_URL || 'https://frontend-tim-loss-projects.vercel.app',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'api',
      testMatch: /api\.spec\.js/,
      use: {},
    },
  ],

  // Only start web server for local testing
  ...(process.env.TEST_LOCAL && {
    webServer: {
      command: 'npm start',
      url: 'http://localhost:3000',
      reuseExistingServer: true,
      timeout: 120 * 1000,
    },
  }),
});
