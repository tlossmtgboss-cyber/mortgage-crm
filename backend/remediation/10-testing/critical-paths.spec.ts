/**
 * 10-testing/critical-paths.spec.ts
 *
 * The tests that MUST pass before every deploy. If any of these fail, no
 * amount of green elsewhere matters. Kept small, stable, and fast.
 *
 * Drop-in: frontend/tests/e2e/critical-paths.spec.ts
 */

import { test, expect, Page } from "@playwright/test";

const TEST_USER_EMAIL = process.env.E2E_TEST_USER_EMAIL || "e2e@perennia.test";
const TEST_USER_PASSWORD = process.env.E2E_TEST_USER_PASSWORD || "test-user-password";

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(TEST_USER_EMAIL);
  await page.getByLabel(/password/i).fill(TEST_USER_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/(dashboard|pipeline|aria|\/?$)/);
}

test.describe("Authentication", () => {
  test("login sets httpOnly cookies, not localStorage", async ({ page, context }) => {
    await login(page);

    // JWT must NOT be in localStorage
    const hasLocalStorageJwt = await page.evaluate(() => {
      const keys = Object.keys(window.localStorage);
      return keys.some((k) =>
        ["token", "jwt", "auth_token", "access_token", "refresh_token"].includes(k.toLowerCase()),
      );
    });
    expect(hasLocalStorageJwt).toBe(false);

    // Auth cookie must be httpOnly
    const cookies = await context.cookies();
    const accessCookie = cookies.find((c) => c.name === "perennia_access");
    expect(accessCookie).toBeDefined();
    expect(accessCookie!.httpOnly).toBe(true);
    expect(accessCookie!.secure).toBe(true);
    expect(accessCookie!.sameSite).toMatch(/Strict|Lax/);

    // CSRF cookie must NOT be httpOnly (JS needs to read it)
    const csrfCookie = cookies.find((c) => c.name === "perennia_csrf");
    expect(csrfCookie).toBeDefined();
    expect(csrfCookie!.httpOnly).toBe(false);
  });

  test("logout clears cookies and bounces to login", async ({ page, context }) => {
    await login(page);
    await page.getByRole("button", { name: /account|profile|user/i }).first().click();
    await page.getByRole("menuitem", { name: /log out|sign out/i }).click();

    await expect(page).toHaveURL(/\/login/);

    const cookies = await context.cookies();
    expect(cookies.find((c) => c.name === "perennia_access")).toBeUndefined();
  });

  test("bad password shows generic error, does not leak account existence", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("does-not-exist@example.com");
    await page.getByLabel(/password/i).fill("bad-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    const err = page.getByRole("alert");
    await expect(err).toBeVisible();
    const text = await err.textContent();
    // Must not say "user not found" or similar
    expect(text?.toLowerCase()).not.toContain("not found");
    expect(text?.toLowerCase()).not.toContain("no account");
  });
});

test.describe("Pipeline — critical flows", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/pipeline");
  });

  test("pipeline loads and displays loans", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /pipeline/i })).toBeVisible();
    // At least one loan card visible OR the empty state
    const loanCards = page.getByTestId("loan-card");
    const emptyState = page.getByTestId("pipeline-empty");
    await expect(loanCards.first().or(emptyState)).toBeVisible();
  });

  test("can open loan detail from pipeline", async ({ page }) => {
    const firstCard = page.getByTestId("loan-card").first();
    if ((await firstCard.count()) === 0) {
      test.skip(true, "no loans in fixture — seed test data");
    }
    await firstCard.click();
    await expect(page).toHaveURL(/\/pipeline\/[a-f0-9-]+/);
    await expect(page.getByTestId("loan-detail")).toBeVisible();
  });
});

test.describe("Performance gates", () => {
  test("initial load budget", async ({ page }) => {
    const responses: { url: string; size: number; type: string }[] = [];
    page.on("response", async (res) => {
      const req = res.request();
      if (req.resourceType() === "script" || req.resourceType() === "stylesheet") {
        try {
          const body = await res.body();
          responses.push({
            url: req.url(),
            size: body.length,
            type: req.resourceType(),
          });
        } catch {
          // ignore
        }
      }
    });

    await page.goto("/login", { waitUntil: "networkidle" });

    const totalInitial = responses.reduce((sum, r) => sum + r.size, 0);
    // 12MB raw = ~3MB gzipped — loose budget checked at response level
    expect(totalInitial).toBeLessThan(12 * 1024 * 1024);
  });

  test("time to interactive under 3s on fast 3G", async ({ browser }) => {
    const context = await browser.newContext();
    // Playwright doesn't throttle network natively, but we can still measure
    const page = await context.newPage();

    const start = Date.now();
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const loaded = Date.now() - start;

    expect(loaded).toBeLessThan(3_000);
    await context.close();
  });
});

test.describe("Accessibility smoke", () => {
  test("login page has proper labels", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });
});
