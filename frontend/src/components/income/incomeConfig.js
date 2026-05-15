/**
 * incomeConfig.js
 *
 * SINGLE SOURCE OF TRUTH for all income type configuration across the frontend.
 * Mirrors the backend UnifiedIncomeType enum in
 *   backend/services/income/unified_income_calculator.py
 *
 * Previously duplicated in:
 *   - UnifiedIncomeCalculator.js
 *   - IncomeCalculatorModal.js
 *   - IncomeCalculatorTabs.js
 *
 * Design system colors reference CSS variables:
 *   --color-primary: #1F3D2E (teal)
 *   --color-success, --color-warning, --color-error
 */

// =============================================================================
// INCOME TYPES — 14 types matching backend UnifiedIncomeType enum
// =============================================================================

/** @typedef {'employment'|'nontaxable'|'nonqm'|'rental'|'selfemployed'|'other'} IncomeCategory */

/**
 * @typedef {Object} IncomeTypeConfig
 * @property {string} key           - Enum key matching backend UnifiedIncomeType
 * @property {string} label         - Full display label
 * @property {string} icon          - Lucide icon name
 * @property {string} shortLabel    - Abbreviated label for compact UI
 * @property {string} color         - Hex color for badges and accents
 * @property {IncomeCategory} category - Grouping category
 * @property {number} [grossUpFactor] - Non-taxable gross-up multiplier
 * @property {string} [description]   - Method description for bank statement types
 */

/** @type {IncomeTypeConfig[]} */
export const INCOME_TYPES = [
  {
    key: 'W2_HOURLY',
    label: 'W-2 Hourly',
    icon: 'clock',
    shortLabel: 'Hourly',
    color: '#3b82f6',
    category: 'employment',
  },
  {
    key: 'W2_SALARY',
    label: 'W-2 Salary',
    icon: 'briefcase',
    shortLabel: 'Salary',
    color: '#3b82f6',
    category: 'employment',
  },
  {
    key: 'OT_BONUS',
    label: 'Overtime & Bonus',
    icon: 'trending-up',
    shortLabel: 'OT/Bonus',
    color: '#B8924A',
    category: 'employment',
  },
  {
    key: 'COMMISSION',
    label: 'Commission',
    icon: 'percent',
    shortLabel: 'Commission',
    color: '#B8924A',
    category: 'employment',
  },
  {
    key: 'OTHER_INCOME',
    label: 'Other Income',
    icon: 'plus-circle',
    shortLabel: 'Other',
    color: '#6b7280',
    category: 'other',
  },
  {
    key: 'NONTAX_SS',
    label: 'Social Security (Non-Taxable)',
    icon: 'shield',
    shortLabel: 'SS',
    color: '#2D7A52',
    category: 'nontaxable',
    grossUpFactor: 1.25,
  },
  {
    key: 'NONTAX_OTHER',
    label: 'Non-Taxable Other',
    icon: 'heart',
    shortLabel: 'Non-Tax',
    color: '#2D7A52',
    category: 'nontaxable',
    grossUpFactor: 1.25,
  },
  {
    key: 'BANK_STATEMENT_PERSONAL',
    label: 'Bank Statement (Personal)',
    icon: 'credit-card',
    shortLabel: 'Bank Personal',
    color: '#ec4899',
    category: 'nonqm',
  },
  {
    key: 'BANK_STATEMENT_BUSINESS_M1',
    label: 'Bank Statement (Business M1)',
    icon: 'building',
    shortLabel: 'Bank Biz M1',
    color: '#ec4899',
    category: 'nonqm',
    description: 'Deposits minus expenses',
  },
  {
    key: 'BANK_STATEMENT_BUSINESS_M2',
    label: 'Bank Statement (Business M2)',
    icon: 'building',
    shortLabel: 'Bank Biz M2',
    color: '#ec4899',
    category: 'nonqm',
    description: 'Gross deposits with expense ratio',
  },
  {
    key: 'BANK_STATEMENT_BUSINESS_M3',
    label: 'Bank Statement (Business M3)',
    icon: 'building',
    shortLabel: 'Bank Biz M3',
    color: '#ec4899',
    category: 'nonqm',
    description: 'P&L with deposits verification',
  },
  {
    key: 'RENTAL_SCHEDULE_E',
    label: 'Rental (Schedule E)',
    icon: 'home',
    shortLabel: 'Rental',
    color: '#f59e0b',
    category: 'rental',
  },
  {
    key: 'SELF_EMPLOYMENT_1084',
    label: 'Self-Employment (1084)',
    icon: 'file-text',
    shortLabel: 'Self-Emp',
    color: '#f59e0b',
    category: 'selfemployed',
  },
];

// =============================================================================
// INCOME CATEGORIES — grouped view of INCOME_TYPES
// =============================================================================

/**
 * Income types grouped by category.
 * Derived from INCOME_TYPES at module load; always in sync.
 *
 * @type {Record<IncomeCategory, IncomeTypeConfig[]>}
 */
export const INCOME_CATEGORIES = INCOME_TYPES.reduce((acc, type) => {
  if (!acc[type.category]) {
    acc[type.category] = [];
  }
  acc[type.category].push(type);
  return acc;
}, /** @type {Record<string, IncomeTypeConfig[]>} */ ({}));

// =============================================================================
// VERIFICATION STATUSES
// =============================================================================

/**
 * @typedef {Object} VerificationStatusConfig
 * @property {string} label   - Display label
 * @property {string} color   - Text / icon color
 * @property {string} bgColor - Badge background color
 */

/** @type {Record<string, VerificationStatusConfig>} */
export const VERIFICATION_STATUSES = {
  PENDING: {
    label: 'Pending',
    color: '#92400e',
    bgColor: 'rgba(168,75,47,0.08)',
  },
  DOCS_RECEIVED: {
    label: 'Docs Received',
    color: '#1d4ed8',
    bgColor: 'rgba(33,127,141,0.08)',
  },
  VERIFIED: {
    label: 'Verified',
    color: '#065f46',
    bgColor: 'rgba(33,127,141,0.12)',
  },
  NEEDS_DOCS: {
    label: 'Needs Docs',
    color: '#dc2626',
    bgColor: 'rgba(192,21,47,0.08)',
  },
  CALCULATED: {
    label: 'Calculated',
    color: '#1F3D2E',
    bgColor: 'rgba(33,127,141,0.08)',
  },
};

// =============================================================================
// CALCULATION STATUSES
// =============================================================================

/**
 * @typedef {Object} CalculationStatusConfig
 * @property {string} label - Display label
 * @property {string} color - Accent color
 */

/** @type {Record<string, CalculationStatusConfig>} */
export const CALCULATION_STATUSES = {
  PENDING: {
    label: 'Pending',
    color: '#6b7280',
  },
  IN_PROGRESS: {
    label: 'In Progress',
    color: '#3b82f6',
  },
  COMPLETED: {
    label: 'Completed',
    color: '#2D7A52',
  },
  NEEDS_REVIEW: {
    label: 'Needs Review',
    color: '#f59e0b',
  },
  REVIEWED: {
    label: 'Reviewed',
    color: '#1F3D2E',
  },
  APPROVED: {
    label: 'Approved',
    color: '#065f46',
  },
  REJECTED: {
    label: 'Rejected',
    color: '#dc2626',
  },
};

// =============================================================================
// PAY FREQUENCIES — matches backend PayFrequency + FREQUENCY_MULTIPLIERS
// =============================================================================

/**
 * @typedef {Object} PayFrequencyConfig
 * @property {string} key        - Enum key matching backend PayFrequency
 * @property {string} label      - Display label
 * @property {number} multiplier - Monthly multiplier (payments per month)
 */

/** @type {PayFrequencyConfig[]} */
export const PAY_FREQUENCIES = [
  { key: 'MONTHLY', label: 'Monthly (1x)', multiplier: 1 },
  { key: 'SEMI_MONTHLY', label: 'Semi-Monthly (2x)', multiplier: 2 },
  { key: 'BI_WEEKLY', label: 'Bi-Weekly (2.1667x)', multiplier: 2.1667 },
  { key: 'WEEKLY', label: 'Weekly (4.333x)', multiplier: 4.333 },
];

// =============================================================================
// CONFIDENCE THRESHOLDS — AI extraction confidence scoring
// =============================================================================

/**
 * Minimum confidence score (0-100) required for each review tier.
 * Scores are compared >= threshold, evaluated top-down.
 *
 * @type {Record<string, number>}
 */
export const CONFIDENCE_THRESHOLDS = {
  /** 98+ : No human review needed */
  AUTO_APPROVE: 98,
  /** 90-97 : Quick spot-check */
  QUICK_REVIEW: 90,
  /** 80-89 : Standard review */
  STANDARD_REVIEW: 80,
  /** 60-79 : Detailed line-by-line review */
  DETAILED_REVIEW: 60,
  /** 0-59  : Manual data entry required */
  MANUAL_ENTRY: 0,
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/** @type {Map<string, IncomeTypeConfig>} */
const _incomeTypeIndex = new Map(INCOME_TYPES.map((t) => [t.key, t]));

/**
 * Look up an income type configuration by its key.
 *
 * @param {string} key - Income type key (e.g. 'W2_SALARY')
 * @returns {IncomeTypeConfig|undefined}
 */
export function getIncomeType(key) {
  return _incomeTypeIndex.get(key);
}

/**
 * Return all income types belonging to a category.
 *
 * @param {IncomeCategory} category
 * @returns {IncomeTypeConfig[]}
 */
export function getIncomeTypesByCategory(category) {
  return INCOME_CATEGORIES[category] || [];
}

/**
 * Look up a verification status configuration by its key.
 *
 * @param {string} key - Status key (e.g. 'VERIFIED')
 * @returns {VerificationStatusConfig|undefined}
 */
export function getVerificationStatus(key) {
  return VERIFICATION_STATUSES[key];
}

/**
 * @typedef {Object} ConfidenceLevelResult
 * @property {string} level - Threshold key (e.g. 'QUICK_REVIEW')
 * @property {string} label - Human-readable label
 * @property {string} color - Accent color for the confidence badge
 */

/**
 * Determine the confidence level for a given score.
 * Evaluates thresholds top-down; returns the highest matching tier.
 *
 * @param {number} score - Confidence score 0-100
 * @returns {ConfidenceLevelResult}
 */
export function getConfidenceLevel(score) {
  if (score >= CONFIDENCE_THRESHOLDS.AUTO_APPROVE) {
    return { level: 'AUTO_APPROVE', label: 'Auto-Approve', color: '#065f46' };
  }
  if (score >= CONFIDENCE_THRESHOLDS.QUICK_REVIEW) {
    return { level: 'QUICK_REVIEW', label: 'Quick Review', color: '#1F3D2E' };
  }
  if (score >= CONFIDENCE_THRESHOLDS.STANDARD_REVIEW) {
    return { level: 'STANDARD_REVIEW', label: 'Standard Review', color: '#f59e0b' };
  }
  if (score >= CONFIDENCE_THRESHOLDS.DETAILED_REVIEW) {
    return { level: 'DETAILED_REVIEW', label: 'Detailed Review', color: '#ea580c' };
  }
  return { level: 'MANUAL_ENTRY', label: 'Manual Entry', color: '#dc2626' };
}
