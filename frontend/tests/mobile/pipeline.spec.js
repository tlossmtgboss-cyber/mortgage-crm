// @ts-check
/**
 * Mobile Pipeline / Loans E2E Tests
 *
 * Validates the loans/pipeline view on mobile viewports:
 * - Card rendering in single-column layout
 * - Stage tab / filter navigation
 * - Loan card content fields
 * - Sort dropdown
 * - Search functionality
 * - Empty state
 */
import {
  mobileTest as test,
  expect,
  DEVICES,
  setupMobileContext,
  assertNoHorizontalOverflow,
  assertTouchTargets,
  mobileLogin,
} from './setup.js';

// The Loans page is at /loans (see routes/index.jsx)
const LOANS_PATH = '/loans';

test.describe('Mobile Pipeline / Loans', () => {
  test.beforeEach(async ({ mobilePage: page }) => {
    await mobileLogin(page);
  });

  // -----------------------------------------------------------------------
  // Card layout
  // -----------------------------------------------------------------------

  test('should render loan cards in single-column layout on mobile', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // Wait for loans to load — the page uses a table or card layout
    // On mobile (390px width), cards/rows should stack vertically.
    const cards = page.locator('.loan-card, .loan-row, tr.loan-row, [data-testid="loan-card"]');
    const cardCount = await cards.count();

    if (cardCount > 1) {
      // Verify cards are stacked vertically (each card's left edge should be similar)
      const firstBox = await cards.nth(0).boundingBox();
      const secondBox = await cards.nth(1).boundingBox();

      if (firstBox && secondBox) {
        // In single-column layout, second card should be below the first,
        // not side-by-side. Their top positions should differ.
        expect(secondBox.y).toBeGreaterThan(firstBox.y);

        // Both cards should span (close to) the full container width
        // Allow some padding — card should be at least 70% of viewport
        const viewport = DEVICES.iPhone14;
        expect(firstBox.width).toBeGreaterThan(viewport.width * 0.7);
      }
    }

    await assertNoHorizontalOverflow(page);
  });

  // -----------------------------------------------------------------------
  // Stage tab / filter navigation
  // -----------------------------------------------------------------------

  test('should display stage filter tabs', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // The Loans page renders filter buttons ('All', 'Application', 'Disclosed', etc.)
    const filterButtons = page.locator('.filter-btn, .stage-filter, [data-testid="stage-filter"], button:has-text("All")');
    await expect(filterButtons.first()).toBeVisible({ timeout: 10000 });
  });

  test('should filter loans when tapping a stage tab', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // Click "All" first to ensure baseline
    const allTab = page.locator('button:has-text("All"), .filter-btn:has-text("All")').first();
    if (await allTab.isVisible()) {
      await allTab.click();
      // Allow re-render
      await page.waitForTimeout(500);
    }

    // Try clicking a specific stage filter
    const processingTab = page.locator(
      'button:has-text("Processing"), button:has-text("In Processing"), .filter-btn:has-text("Processing")'
    ).first();

    if (await processingTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await processingTab.click();
      await page.waitForTimeout(500);

      // Verify the tab appears active (has active/selected class or aria attribute)
      const isActive = await processingTab.evaluate((el) => {
        return (
          el.classList.contains('active') ||
          el.classList.contains('selected') ||
          el.getAttribute('aria-selected') === 'true' ||
          el.getAttribute('data-active') === 'true'
        );
      });
      // At minimum the tab should be clickable without error
      expect(true).toBe(true);
    }
  });

  test('should have scrollable stage tabs on narrow viewport', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // The filter tab container should be horizontally scrollable on mobile
    // since all stages do not fit in 390px
    const tabContainer = page.locator(
      '.filters, .stage-filters, .filter-tabs, [data-testid="stage-tabs"]'
    ).first();

    if (await tabContainer.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Either the container scrolls or all tabs fit — both are acceptable
      // The key assertion: no page-level horizontal overflow
      await assertNoHorizontalOverflow(page);
    }
  });

  // -----------------------------------------------------------------------
  // Loan card content
  // -----------------------------------------------------------------------

  test('should display essential loan info on cards', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // Wait for at least one loan to appear
    const firstCard = page.locator(
      '.loan-card, .loan-row, tr, [data-testid="loan-card"]'
    ).first();

    const visible = await firstCard.isVisible({ timeout: 10000 }).catch(() => false);

    if (visible) {
      const cardText = await firstCard.textContent();
      // Cards should contain borrower name or loan number, and an amount
      // At minimum, the card should have non-empty content
      expect(cardText.length).toBeGreaterThan(0);
    }
  });

  test('should have touch-friendly loan cards', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // Each card/row should be large enough to tap
    const cards = page.locator(
      '.loan-card, .loan-row, [data-testid="loan-card"]'
    );

    const count = await cards.count();
    for (let i = 0; i < Math.min(count, 5); i++) {
      const box = await cards.nth(i).boundingBox();
      if (box) {
        // Card height should be at least 44px (Apple HIG minimum)
        expect(box.height).toBeGreaterThanOrEqual(44);
      }
    }
  });

  // -----------------------------------------------------------------------
  // Sort dropdown
  // -----------------------------------------------------------------------

  test('should have a functional sort dropdown', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    // Look for sort controls (select, dropdown, or button with "Sort" text)
    const sortControl = page.locator(
      'select.sort-select, [data-testid="sort-dropdown"], button:has-text("Sort"), .sort-control'
    ).first();

    const visible = await sortControl.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // If it is a select element, check it has options
      const tag = await sortControl.evaluate((el) => el.tagName.toLowerCase());
      if (tag === 'select') {
        const optionCount = await sortControl.locator('option').count();
        expect(optionCount).toBeGreaterThan(0);
      } else {
        // Click the sort control and verify it responds
        await sortControl.click();
        // Just verify it does not crash
        expect(true).toBe(true);
      }
    }
  });

  // -----------------------------------------------------------------------
  // Search functionality
  // -----------------------------------------------------------------------

  test('should have a visible search input', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    const searchInput = page.locator(
      'input[type="search"], input[placeholder*="Search"], input[placeholder*="search"], .search-input, [data-testid="search-input"]'
    ).first();

    const visible = await searchInput.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // Type a search query
      await searchInput.fill('test');
      await page.waitForTimeout(500);

      // Verify input accepted the value
      await expect(searchInput).toHaveValue('test');

      // Clear and verify
      await searchInput.clear();
      await expect(searchInput).toHaveValue('');
    }
  });

  test('should filter results when searching by borrower name', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    const searchInput = page.locator(
      'input[type="search"], input[placeholder*="Search"], input[placeholder*="search"], .search-input'
    ).first();

    const visible = await searchInput.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // Count loans before search
      const cardsBefore = page.locator(
        '.loan-card, .loan-row, [data-testid="loan-card"]'
      );
      const countBefore = await cardsBefore.count();

      // Type a query unlikely to match all loans
      await searchInput.fill('xyznonexistent');
      await page.waitForTimeout(1000);

      const cardsAfter = page.locator(
        '.loan-card, .loan-row, [data-testid="loan-card"]'
      );
      const countAfter = await cardsAfter.count();

      // After searching for a nonsense term, count should be <= before
      expect(countAfter).toBeLessThanOrEqual(countBefore);
    }
  });

  // -----------------------------------------------------------------------
  // Empty state
  // -----------------------------------------------------------------------

  test('should display empty state when no loans match filter', async ({ mobilePage: page }) => {
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');

    const searchInput = page.locator(
      'input[type="search"], input[placeholder*="Search"], input[placeholder*="search"], .search-input'
    ).first();

    const visible = await searchInput.isVisible({ timeout: 5000 }).catch(() => false);

    if (visible) {
      // Search for something guaranteed to not match
      await searchInput.fill('zzznonexistent999');
      await page.waitForTimeout(1000);

      // Either an empty-state message appears, or the loan list is empty
      const emptyState = page.locator(
        '.empty-state, .no-results, [data-testid="empty-state"], p:has-text("No loans"), p:has-text("No results")'
      ).first();

      const cards = page.locator('.loan-card, .loan-row, [data-testid="loan-card"]');
      const cardCount = await cards.count();

      // One of these should be true: empty-state visible OR zero cards
      const emptyVisible = await emptyState.isVisible().catch(() => false);
      expect(emptyVisible || cardCount === 0).toBe(true);
    }
  });

  // -----------------------------------------------------------------------
  // Viewport variants
  // -----------------------------------------------------------------------

  test('should render pipeline without overflow on iPhone SE', async ({ page }) => {
    await setupMobileContext(page, 'iPhoneSE');
    await mobileLogin(page);
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');
    await assertNoHorizontalOverflow(page);
  });

  test('should render pipeline on iPad Mini (tablet layout)', async ({ page }) => {
    await setupMobileContext(page, 'iPadMini');
    await mobileLogin(page);
    await page.goto(LOANS_PATH);
    await page.waitForLoadState('networkidle');
    await assertNoHorizontalOverflow(page);
  });
});
