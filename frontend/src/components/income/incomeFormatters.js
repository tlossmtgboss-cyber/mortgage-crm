/**
 * incomeFormatters.js
 *
 * Consolidated formatting utilities for income calculator components.
 * Replaces duplicated helpers across IncomeCalculator, SmartDocsIncome,
 * IncomeWorksheet, UnifiedIncomeCalculator, IncomeCalculatorModal, etc.
 */

// ---------------------------------------------------------------------------
// Pay frequency multipliers (periodic -> annual)
// ---------------------------------------------------------------------------

/** @type {Record<string, number>} */
export const PAY_FREQUENCY_ANNUAL_MULTIPLIERS = {
  MONTHLY: 12,
  SEMI_MONTHLY: 24,
  BI_WEEKLY: 26,
  WEEKLY: 52,
};

// ---------------------------------------------------------------------------
// Currency formatting
// ---------------------------------------------------------------------------

/**
 * Format a number as US dollars.
 *
 * @param {number|null|undefined} amount - The value to format.
 * @param {Object} [options]
 * @param {number} [options.decimals] - Fraction digits (0 by default, 2 for precise mode).
 * @returns {string} Formatted currency string, e.g. '$5,000' or '$5,000.00'.
 */
export function formatCurrency(amount, options = {}) {
  if (amount == null) return '$0';
  const decimals = options.decimals ?? 0;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(amount));
}

/**
 * Format a number as US dollars with exactly 2 decimal places.
 * Intended for worksheets and detail tables where cent precision matters.
 *
 * @param {number|null|undefined} amount
 * @returns {string} e.g. '$5,000.00'
 */
export function formatCurrencyPrecise(amount) {
  return formatCurrency(amount, { decimals: 2 });
}

// ---------------------------------------------------------------------------
// Percent formatting
// ---------------------------------------------------------------------------

/**
 * Format a numeric value as a percentage string.
 *
 * @param {number|null|undefined} value - The percentage value (e.g. 85.5).
 * @param {number} [decimals=1] - Number of decimal places.
 * @returns {string} e.g. '85.5%' or 'N/A' if null/undefined.
 */
export function formatPercent(value, decimals = 1) {
  if (value == null) return 'N/A';
  return `${Number(value).toFixed(decimals)}%`;
}

// ---------------------------------------------------------------------------
// Date formatting
// ---------------------------------------------------------------------------

/**
 * Format a date string as a relative label when recent, otherwise short date.
 *
 * - Same calendar day: 'Today'
 * - Previous calendar day: 'Yesterday'
 * - 2-6 days ago: 'N days ago'
 * - Older: short month + day (e.g. 'Jan 15')
 *
 * @param {string|null|undefined} dateString - ISO date string or parseable date.
 * @returns {string}
 */
export function formatDate(dateString) {
  if (!dateString) return '-';

  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '-';

  const now = new Date();

  // Compare by calendar date in local timezone
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today - target) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays >= 2 && diffDays <= 6) return `${diffDays} days ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Format a date string as an absolute date: 'Jan 15, 2026'.
 *
 * @param {string|null|undefined} dateString
 * @returns {string}
 */
export function formatDateAbsolute(dateString) {
  if (!dateString) return '-';

  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '-';

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Confidence helpers
// ---------------------------------------------------------------------------

/**
 * Return a CSS class string for a confidence badge.
 *
 * @param {number|null|undefined} confidence - Confidence score 0-100.
 * @returns {string} 'confidence-high' | 'confidence-medium' | 'confidence-low'
 */
export function getConfidenceBadgeClass(confidence) {
  const pct = Number(confidence);
  if (pct >= 90) return 'confidence-high';
  if (pct >= 70) return 'confidence-medium';
  return 'confidence-low';
}

/**
 * Return a hex color for a confidence value.
 *
 * @param {number|null|undefined} confidence - Confidence score 0-100.
 * @returns {string} Hex color string.
 */
export function getConfidenceColor(confidence) {
  const pct = Number(confidence);
  if (pct >= 90) return '#217F8D';
  if (pct >= 70) return '#A84B2F';
  return '#C0152F';
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

/**
 * Map an income-source status to a badge CSS class.
 *
 * @param {string|null|undefined} status - e.g. 'APPROVED', 'REJECTED', 'PENDING'.
 * @returns {string} CSS class string for the badge.
 */
export function getStatusBadgeClass(status) {
  const s = (status || '').toUpperCase();
  if (s === 'APPROVED') return 'status-badge status-badge--success';
  if (s === 'REJECTED') return 'status-badge status-badge--error';
  return 'status-badge status-badge--warning';
}

// ---------------------------------------------------------------------------
// Income display helpers
// ---------------------------------------------------------------------------

/**
 * Format monthly and annual income into a display object.
 *
 * @param {number|null|undefined} monthly
 * @param {number|null|undefined} annual
 * @returns {{ monthly: string, annual: string }}
 */
export function formatIncomeAmount(monthly, annual) {
  return {
    monthly: `${formatCurrency(monthly)}/mo`,
    annual: `${formatCurrency(annual)}/yr`,
  };
}

/**
 * Format a trend direction and percentage into a display object.
 *
 * @param {string} direction - 'increasing', 'decreasing', or 'stable'.
 * @param {number|null|undefined} percentage - e.g. 5.2
 * @returns {{ icon: string, label: string, className: string }}
 */
export function formatTrend(direction, percentage) {
  const dir = (direction || '').toLowerCase();

  let icon;
  let className;
  let sign;

  if (dir === 'increasing') {
    icon = '\u2191'; // ↑
    className = 'trend-increasing';
    sign = '+';
  } else if (dir === 'decreasing') {
    icon = '\u2193'; // ↓
    className = 'trend-decreasing';
    sign = '-';
  } else {
    icon = '\u2192'; // →
    className = 'trend-stable';
    sign = '';
  }

  const pct = percentage != null ? Number(percentage) : null;
  const label = pct != null ? `${sign}${Math.abs(pct).toFixed(1)}%` : '';

  return { icon, label, className };
}

// ---------------------------------------------------------------------------
// Calculation helpers
// ---------------------------------------------------------------------------

/**
 * Sum monthly income from an array of income source objects.
 * Looks for `monthly_amount` first, then falls back to `amount`.
 *
 * @param {Array<Object>} sources - Array of income source objects.
 * @returns {number} Total monthly income.
 */
export function calcTotalMonthly(sources) {
  if (!Array.isArray(sources)) return 0;
  return sources.reduce(
    (sum, src) => sum + Number(src.monthly_amount || src.amount || 0),
    0,
  );
}

/**
 * Convert a periodic income amount to an annual amount.
 *
 * @param {number} amount - Income per period.
 * @param {string} frequency - One of 'MONTHLY', 'SEMI_MONTHLY', 'BI_WEEKLY', 'WEEKLY'.
 * @returns {number} Annualized amount.
 */
export function annualize(amount, frequency) {
  const multiplier = PAY_FREQUENCY_ANNUAL_MULTIPLIERS[frequency];
  if (multiplier == null) {
    throw new Error(`Unknown pay frequency: ${frequency}`);
  }
  return Number(amount) * multiplier;
}

/**
 * Convert an annual amount to monthly (annual / 12).
 *
 * @param {number|null|undefined} annual
 * @returns {number}
 */
export function monthlyFromAnnual(annual) {
  if (annual == null) return 0;
  return Number(annual) / 12;
}
