/**
 * Toast Notification Verification Script
 *
 * Tests that all settings pages properly display toast notifications
 * for success and error states.
 *
 * Usage:
 *   npm install puppeteer
 *   node tests/toast-verification.js
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

// Helper to wait
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

// Configuration
const CONFIG = {
  baseUrl: 'https://mortgage-crm-nine.vercel.app',
  credentials: {
    email: 'admin@perenniaai.com',
    password: 'demo123'
  },
  screenshotDir: path.join(__dirname, 'screenshots'),
  timeout: 60000,
};

// Settings pages to test
const SETTINGS_PAGES = [
  { name: 'Email Integration Settings', path: '/settings/email' },
  { name: 'User Profile Settings', path: '/settings/profile' },
  { name: 'Document Upload Settings', path: '/settings/documents' },
  { name: 'Lead Capture Settings', path: '/settings/lead-capture' },
];

// Test results
const results = {
  passed: [],
  failed: [],
  errors: [],
  consoleErrors: [],
  screenshots: [],
};

// Wait for toast notification
async function waitForToast(page, timeout = 5000) {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    const toast = await page.evaluate(() => {
      // Look for various toast implementations
      const selectors = [
        '.Toastify__toast',
        '.toast',
        '[role="alert"]',
        '.notification',
        '.toast-notification',
        '[class*="toast"]',
      ];

      for (const selector of selectors) {
        const elements = document.querySelectorAll(selector);
        for (const el of elements) {
          if (el.offsetParent !== null && el.textContent.trim()) {
            const text = el.textContent.trim();
            const className = el.className || '';
            const isSuccess = className.toLowerCase().includes('success') ||
                            text.toLowerCase().includes('success') ||
                            text.toLowerCase().includes('saved');
            const isError = className.toLowerCase().includes('error') ||
                          text.toLowerCase().includes('error') ||
                          text.toLowerCase().includes('failed') ||
                          text.toLowerCase().includes('network');
            return {
              text,
              className,
              type: isSuccess ? 'success' : (isError ? 'error' : 'unknown'),
              visible: true,
            };
          }
        }
      }
      return null;
    });

    if (toast) return toast;
    await delay(200);
  }

  return null;
}

// Find and click save button
async function clickSaveButton(page) {
  // Try to find and click save button using various methods
  const clicked = await page.evaluate(() => {
    // Method 1: Find by text content
    const buttons = Array.from(document.querySelectorAll('button'));

    // Priority order: "Save Changes", "Save Settings", "Save", "Update"
    const saveTexts = ['save changes', 'save settings', 'save', 'update'];

    for (const saveText of saveTexts) {
      const btn = buttons.find(b => {
        const text = b.textContent.toLowerCase().trim();
        return text.includes(saveText) && !b.disabled && b.offsetParent !== null;
      });

      if (btn) {
        btn.click();
        return { success: true, text: btn.textContent.trim() };
      }
    }

    // Method 2: Find by class
    const primaryBtn = document.querySelector('.btn-primary:not([disabled])');
    if (primaryBtn && primaryBtn.offsetParent !== null) {
      primaryBtn.click();
      return { success: true, text: primaryBtn.textContent.trim() };
    }

    // Method 3: Submit button
    const submitBtn = document.querySelector('button[type="submit"]:not([disabled])');
    if (submitBtn && submitBtn.offsetParent !== null) {
      submitBtn.click();
      return { success: true, text: submitBtn.textContent.trim() };
    }

    return { success: false, reason: 'No save button found' };
  });

  return clicked;
}

async function runTests() {
  console.log('🚀 Starting Toast Verification Tests\n');
  console.log(`📍 Base URL: ${CONFIG.baseUrl}`);
  console.log(`📧 Test User: ${CONFIG.credentials.email}\n`);

  // Create screenshots directory
  if (!fs.existsSync(CONFIG.screenshotDir)) {
    fs.mkdirSync(CONFIG.screenshotDir, { recursive: true });
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    protocolTimeout: 120000,
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  // Clear cache and cookies to ensure fresh content
  const client = await page.createCDPSession();
  await client.send('Network.clearBrowserCache');
  await client.send('Network.clearBrowserCookies');
  await client.send('Network.setCacheDisabled', { cacheDisabled: true });
  console.log('🧹 Cleared browser cache and cookies, disabled caching');

  // Capture console errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Filter out common non-critical errors
      if (!text.includes('favicon') && !text.includes('net::ERR')) {
        results.consoleErrors.push({ text, location: msg.location() });
      }
    }
  });

  page.on('pageerror', error => {
    results.consoleErrors.push({ text: error.message, type: 'pageerror' });
  });

  // Handle dialogs (alert, confirm, prompt)
  let alertDetected = false;
  page.on('dialog', async dialog => {
    alertDetected = true;
    console.log(`   ⚠️  Alert detected: "${dialog.message()}"`);
    results.failed.push({
      test: 'No Alert Popups',
      details: `Browser alert() detected: ${dialog.message()}`,
    });
    await dialog.dismiss();
  });

  try {
    // Verify bundle version
    console.log('📋 Verifying deployed bundle version...');
    await page.goto(CONFIG.baseUrl, { waitUntil: 'domcontentloaded', timeout: CONFIG.timeout });
    const bundleUrl = await page.evaluate(() => {
      const scripts = Array.from(document.querySelectorAll('script[src*="main."]'));
      return scripts.length > 0 ? scripts[0].src : 'NOT_FOUND';
    });
    console.log(`   Bundle: ${bundleUrl}`);

    // Step 1: Login
    console.log('📝 Step 1: Logging in...');
    await page.goto(`${CONFIG.baseUrl}/login`, {
      waitUntil: 'networkidle2',
      timeout: CONFIG.timeout
    });

    await page.screenshot({ path: path.join(CONFIG.screenshotDir, '01-login-page.png') });

    // Wait for and fill login form
    await page.waitForSelector('input[type="email"], input[name="email"]', { timeout: 10000 });

    const emailInput = await page.$('input[type="email"]') || await page.$('input[name="email"]');
    const passwordInput = await page.$('input[type="password"]') || await page.$('input[name="password"]');

    await emailInput.type(CONFIG.credentials.email, { delay: 50 });
    await passwordInput.type(CONFIG.credentials.password, { delay: 50 });

    // Click login and wait for navigation
    const loginButton = await page.$('button[type="submit"]');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle2', timeout: CONFIG.timeout }).catch(() => {}),
      loginButton.click(),
    ]);

    await delay(2000);
    await page.screenshot({ path: path.join(CONFIG.screenshotDir, '02-after-login.png') });

    const currentUrl = page.url();
    if (currentUrl.includes('login')) {
      throw new Error('Login failed - still on login page');
    }

    console.log('✅ Login successful\n');
    results.passed.push({ test: 'Login', details: 'Successfully authenticated' });

    // Step 2: Test each settings page
    let screenshotIndex = 3;

    for (const settingsPage of SETTINGS_PAGES) {
      console.log(`\n📋 Testing: ${settingsPage.name}`);
      console.log(`   URL: ${settingsPage.path}`);

      try {
        // Navigate to settings page
        await page.goto(`${CONFIG.baseUrl}${settingsPage.path}`, {
          waitUntil: 'networkidle2',
          timeout: CONFIG.timeout
        });
        await delay(2000);

        // Screenshot: Page loaded
        const pageSlug = settingsPage.name.toLowerCase().replace(/\s+/g, '-');
        await page.screenshot({
          path: path.join(CONFIG.screenshotDir, `${screenshotIndex++}-${pageSlug}-loaded.png`)
        });

        // ========== TEST 1: SUCCESS TOAST (ONLINE SAVE) ==========
        console.log('   🔄 Test 1: Testing success toast (online save)...');

        const saveResult = await clickSaveButton(page);

        if (!saveResult.success) {
          console.log(`   ⚠️  ${saveResult.reason}`);
          results.failed.push({
            test: `${settingsPage.name} - Find Save Button`,
            details: saveResult.reason,
          });
          continue;
        }

        console.log(`   📌 Clicked: "${saveResult.text}"`);
        await delay(500);

        const successToast = await waitForToast(page, 5000);
        await page.screenshot({
          path: path.join(CONFIG.screenshotDir, `${screenshotIndex++}-${pageSlug}-after-save.png`)
        });

        if (successToast) {
          console.log(`   ✅ Toast appeared: "${successToast.text.substring(0, 50)}"`);
          results.passed.push({
            test: `${settingsPage.name} - Success Toast`,
            details: successToast.text,
          });
        } else {
          console.log('   ❌ No success toast detected');
          results.failed.push({
            test: `${settingsPage.name} - Success Toast`,
            details: 'No toast appeared after successful save',
          });
        }

        // Wait for toast to auto-dismiss
        await delay(4000);

        // ========== TEST 2: ERROR TOAST (OFFLINE SAVE) ==========
        console.log('   🔄 Test 2: Testing error toast (offline save)...');

        // Go offline
        await page.setOfflineMode(true);
        console.log('   📴 Network: OFFLINE');

        const offlineSaveResult = await clickSaveButton(page);
        if (!offlineSaveResult.success) {
          console.log(`   ⚠️  ${offlineSaveResult.reason}`);
          await page.setOfflineMode(false);
          continue;
        }

        console.log(`   📌 Clicked: "${offlineSaveResult.text}"`);
        await delay(500);

        const errorToast = await waitForToast(page, 5000);
        await page.screenshot({
          path: path.join(CONFIG.screenshotDir, `${screenshotIndex++}-${pageSlug}-offline-error.png`)
        });

        if (errorToast) {
          console.log(`   ✅ Error toast appeared: "${errorToast.text.substring(0, 50)}"`);
          results.passed.push({
            test: `${settingsPage.name} - Error Toast (Offline)`,
            details: errorToast.text,
          });

          // Check if error is specific (mentions network)
          const text = errorToast.text.toLowerCase();
          if (text.includes('network') || text.includes('connection') || text.includes('offline') || text.includes('unable')) {
            console.log('   ✅ Error message is specific (mentions network issue)');
            results.passed.push({
              test: `${settingsPage.name} - Specific Error Message`,
              details: 'Error message mentions network/connection issue',
            });
          }
        } else {
          console.log('   ❌ No error toast detected');
          results.failed.push({
            test: `${settingsPage.name} - Error Toast (Offline)`,
            details: 'No toast appeared after failed save',
          });
        }

        // Go back online
        await page.setOfflineMode(false);
        console.log('   📶 Network: ONLINE');
        await delay(2000);

      } catch (pageError) {
        console.log(`   ❌ Error: ${pageError.message}`);
        results.errors.push({
          test: settingsPage.name,
          error: pageError.message,
        });
        await page.setOfflineMode(false);
      }
    }

    // Check for alerts
    if (!alertDetected) {
      console.log('\n✅ No browser alert() popups detected');
      results.passed.push({
        test: 'No Alert Popups',
        details: 'Errors shown via toast, not alert()',
      });
    }

  } catch (error) {
    console.error(`\n❌ Test suite error: ${error.message}`);
    results.errors.push({ test: 'Test Suite', error: error.message });
    await page.screenshot({ path: path.join(CONFIG.screenshotDir, 'error-state.png') }).catch(() => {});
  } finally {
    await browser.close();
  }

  // Generate report
  generateReport();
}

function generateReport() {
  console.log('\n' + '='.repeat(60));
  console.log('📊 TEST RESULTS SUMMARY');
  console.log('='.repeat(60));

  console.log(`\n✅ PASSED: ${results.passed.length}`);
  for (const test of results.passed) {
    console.log(`   • ${test.test}`);
  }

  console.log(`\n❌ FAILED: ${results.failed.length}`);
  for (const test of results.failed) {
    console.log(`   • ${test.test}`);
    if (test.details) console.log(`     └─ ${test.details}`);
  }

  console.log(`\n⚠️  ERRORS: ${results.errors.length}`);
  for (const error of results.errors) {
    console.log(`   • ${error.test}: ${error.error}`);
  }

  console.log(`\n🔴 CONSOLE ERRORS: ${results.consoleErrors.length}`);
  const uniqueErrors = [...new Set(results.consoleErrors.map(e => e.text))].slice(0, 5);
  for (const error of uniqueErrors) {
    console.log(`   • ${error.substring(0, 80)}...`);
  }

  // Calculate score
  const totalTests = results.passed.length + results.failed.length;
  const score = totalTests > 0 ? Math.round((results.passed.length / totalTests) * 100) : 0;

  console.log('\n' + '='.repeat(60));
  console.log(`📈 SCORE: ${score}% (${results.passed.length}/${totalTests} tests passed)`);

  const criticalConsoleErrors = results.consoleErrors.filter(e =>
    e.type === 'pageerror' || e.text.includes('Uncaught')
  ).length;

  const status = score >= 80 && criticalConsoleErrors === 0 ? '✅ PASS' : '❌ FAIL';
  console.log(`\n${status} - Acceptance: ≥80% pass, 0 critical console errors`);
  console.log('='.repeat(60));

  // Write JSON report
  const reportPath = path.join(CONFIG.screenshotDir, 'test-report.json');
  fs.writeFileSync(reportPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    summary: { passed: results.passed.length, failed: results.failed.length, score, status },
    results,
  }, null, 2));

  console.log(`\n📄 Report: ${reportPath}`);
  console.log(`📸 Screenshots: ${CONFIG.screenshotDir}`);
}

runTests().catch(console.error);
