// @ts-check
/**
 * Mobile E2E Testing Framework — Setup & Utilities
 *
 * Provides device presets, Capacitor mocking, and shared helpers
 * for testing the Perennia AI mobile experience with Playwright.
 */
import { test as base, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Device viewport presets
// ---------------------------------------------------------------------------
export const DEVICES = {
  iPhone14: { width: 390, height: 844 },
  iPhone14ProMax: { width: 430, height: 932 },
  iPhoneSE: { width: 375, height: 667 },
  iPadMini: { width: 744, height: 1133 },
  iPadPro: { width: 1024, height: 1366 },
};

// iOS Safari user agents
export const USER_AGENTS = {
  iPhone:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
  iPad:
    'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
};

// Test credentials (same as existing fixtures.js)
export const TEST_ADMIN = {
  email: 'admin@perenniaai.com',
  password: 'demo123',
};

// ---------------------------------------------------------------------------
// Capacitor mock injection
// ---------------------------------------------------------------------------

/**
 * Inject Capacitor mocks into the page so that code paths gated behind
 * `Capacitor.isNativePlatform()` or native plugin imports execute correctly
 * in a Playwright browser context.
 */
export async function injectCapacitorMocks(page) {
  await page.addInitScript(() => {
    // Core Capacitor mock
    window.Capacitor = {
      isNativePlatform: () => true,
      getPlatform: () => 'ios',
      isPluginAvailable: (name) => {
        const available = [
          'PushNotifications',
          'NativeBiometric',
          'Haptics',
          'Network',
          'Preferences',
          'Keyboard',
          'StatusBar',
          'SplashScreen',
          'App',
          'Camera',
        ];
        return available.includes(name);
      },
      Plugins: {},
    };

    // PushNotifications mock
    window.Capacitor.Plugins.PushNotifications = {
      requestPermissions: async () => ({ receive: 'granted' }),
      register: async () => {},
      addListener: () => ({ remove: () => {} }),
      getDeliveredNotifications: async () => ({ notifications: [] }),
    };

    // NativeBiometric mock
    window.Capacitor.Plugins.NativeBiometric = {
      isAvailable: async () => ({
        isAvailable: true,
        biometryType: 1, // FACE_ID
      }),
      verifyIdentity: async () => {},
      getCredentials: async () => ({ username: '', password: '' }),
      setCredentials: async () => {},
      deleteCredentials: async () => {},
    };

    // Haptics mock
    window.Capacitor.Plugins.Haptics = {
      impact: async () => {},
      notification: async () => {},
      vibrate: async () => {},
      selectionStart: async () => {},
      selectionChanged: async () => {},
      selectionEnd: async () => {},
    };

    // Network mock (online by default)
    const networkListeners = [];
    window.__mockNetwork = {
      setOnline(online) {
        networkListeners.forEach((cb) =>
          cb({ connected: online, connectionType: online ? 'wifi' : 'none' })
        );
        // Also dispatch browser-level events for navigator.onLine fallback
        window.dispatchEvent(new Event(online ? 'online' : 'offline'));
      },
    };

    window.Capacitor.Plugins.Network = {
      getStatus: async () => ({
        connected: navigator.onLine,
        connectionType: navigator.onLine ? 'wifi' : 'none',
      }),
      addListener: (_event, callback) => {
        networkListeners.push(callback);
        return { remove: () => {} };
      },
    };

    // Preferences mock (uses localStorage under the hood)
    window.Capacitor.Plugins.Preferences = {
      get: async ({ key }) => ({ value: localStorage.getItem(key) }),
      set: async ({ key, value }) => localStorage.setItem(key, value),
      remove: async ({ key }) => localStorage.removeItem(key),
      clear: async () => localStorage.clear(),
    };

    // Keyboard mock
    window.Capacitor.Plugins.Keyboard = {
      show: async () => {},
      hide: async () => {},
      setAccessoryBarVisible: async () => {},
      setScroll: async () => {},
      setStyle: async () => {},
      setResizeMode: async () => {},
      addListener: () => ({ remove: () => {} }),
    };

    // StatusBar mock
    window.Capacitor.Plugins.StatusBar = {
      setStyle: async () => {},
      setBackgroundColor: async () => {},
      show: async () => {},
      hide: async () => {},
      setOverlaysWebView: async () => {},
    };

    // SplashScreen mock
    window.Capacitor.Plugins.SplashScreen = {
      show: async () => {},
      hide: async () => {},
    };

    // App mock
    window.Capacitor.Plugins.App = {
      addListener: () => ({ remove: () => {} }),
      getInfo: async () => ({
        name: 'Perennia AI',
        id: 'com.perenniaai.crm',
        build: '1',
        version: '1.0.2',
      }),
      getLaunchUrl: async () => ({ url: '' }),
      exitApp: async () => {},
    };
  });
}

// ---------------------------------------------------------------------------
// Mobile context setup
// ---------------------------------------------------------------------------

/**
 * Configure a Playwright page as a mobile device.
 *
 * @param {import('@playwright/test').Page} page
 * @param {keyof typeof DEVICES} [deviceName='iPhone14']
 * @param {{ native?: boolean }} [options]
 */
export async function setupMobileContext(page, deviceName = 'iPhone14', options = {}) {
  const viewport = DEVICES[deviceName] || DEVICES.iPhone14;
  const isTablet = deviceName.startsWith('iPad');
  const userAgent = isTablet ? USER_AGENTS.iPad : USER_AGENTS.iPhone;

  await page.setViewportSize(viewport);

  // Override user-agent via extra HTTP headers (works in Chromium)
  await page.setExtraHTTPHeaders({ 'User-Agent': userAgent });

  // Enable touch events via CDP if available
  try {
    const context = page.context();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true });
    await cdp.detach();
  } catch {
    // Non-Chromium or CDP unavailable — touch emulation skipped
  }

  if (options.native !== false) {
    await injectCapacitorMocks(page);
  }
}

// ---------------------------------------------------------------------------
// Extended test fixture with mobile helpers
// ---------------------------------------------------------------------------

export const mobileTest = base.extend({
  /**
   * A page pre-configured for iPhone 14 with Capacitor mocks.
   */
  mobilePage: async ({ page }, use) => {
    await setupMobileContext(page, 'iPhone14');
    await use(page);
  },

  /**
   * A page pre-configured AND logged in.
   */
  authedMobilePage: async ({ page }, use) => {
    await setupMobileContext(page, 'iPhone14');
    await page.goto('/login');
    await page.fill('input[type="email"]', TEST_ADMIN.email);
    await page.fill('input[type="password"]', TEST_ADMIN.password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(dashboard|leads|active-loans|aria)/, { timeout: 15000 });
    await use(page);
  },
});

// ---------------------------------------------------------------------------
// Shared assertion helpers
// ---------------------------------------------------------------------------

/**
 * Assert that every matching element meets the minimum touch target size
 * (Apple HIG recommends 44x44 CSS px).
 */
export async function assertTouchTargets(page, selector, minSize = 44) {
  const elements = page.locator(selector);
  const count = await elements.count();
  for (let i = 0; i < count; i++) {
    const box = await elements.nth(i).boundingBox();
    if (box) {
      expect(
        box.width >= minSize || box.height >= minSize,
        `Element ${i} (${selector}) touch target too small: ${box.width}x${box.height}, minimum ${minSize}px`
      ).toBe(true);
    }
  }
}

/**
 * Assert no horizontal overflow (the page body should not scroll horizontally).
 */
export async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => {
    return document.documentElement.scrollWidth > document.documentElement.clientWidth;
  });
  expect(overflow, 'Page has horizontal overflow').toBe(false);
}

/**
 * Assert that inputs use at least 16px font-size to prevent iOS zoom on focus.
 */
export async function assertInputFontSize(page, minPx = 16) {
  const tooSmall = await page.evaluate((min) => {
    const inputs = document.querySelectorAll('input, select, textarea');
    const failures = [];
    inputs.forEach((el) => {
      const size = parseFloat(window.getComputedStyle(el).fontSize);
      if (size < min) {
        failures.push({
          tag: el.tagName,
          id: el.id || el.name || '(unnamed)',
          fontSize: size,
        });
      }
    });
    return failures;
  }, minPx);
  expect(
    tooSmall,
    `Inputs with font-size < ${minPx}px (will trigger iOS zoom): ${JSON.stringify(tooSmall)}`
  ).toEqual([]);
}

/**
 * Simulate going offline using both the browser API and the Capacitor mock.
 */
export async function goOffline(page) {
  await page.context().setOffline(true);
  await page.evaluate(() => {
    if (window.__mockNetwork) {
      window.__mockNetwork.setOnline(false);
    }
  });
}

/**
 * Simulate coming back online.
 */
export async function goOnline(page) {
  await page.context().setOffline(false);
  await page.evaluate(() => {
    if (window.__mockNetwork) {
      window.__mockNetwork.setOnline(true);
    }
  });
}

/**
 * Login helper for mobile tests.
 */
export async function mobileLogin(page, email = TEST_ADMIN.email, password = TEST_ADMIN.password) {
  await page.goto('/login');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(dashboard|leads|active-loans|aria)/, { timeout: 15000 });
}

// Re-export expect for convenience
export { expect };
