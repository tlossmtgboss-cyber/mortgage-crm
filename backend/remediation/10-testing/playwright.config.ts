/**
 * 10-testing/playwright.config.ts
 *
 * Multi-project config: desktop, iPhone SE (smallest common phone),
 * iPhone 14 Pro (common), iPad Pro (common enterprise tablet).
 *
 * Drop-in: frontend/playwright.config.ts
 */

import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:5173";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }], ["junit", { outputFile: "test-results/junit.xml" }]]
    : [["list"], ["html"]],

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "desktop-webkit",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "desktop-firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "mobile-iphone-se",
      use: { ...devices["iPhone SE"] },
      testMatch: /critical-paths\.spec\.ts/,  // only run critical-path tests on mobile
    },
    {
      name: "mobile-iphone",
      use: { ...devices["iPhone 14 Pro"] },
      testMatch: /critical-paths\.spec\.ts/,
    },
    {
      name: "mobile-ipad",
      use: { ...devices["iPad Pro 11"] },
      testMatch: /critical-paths\.spec\.ts/,
    },
  ],

  webServer: process.env.CI
    ? undefined
    : {
        command: "npm run dev",
        port: 5173,
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
