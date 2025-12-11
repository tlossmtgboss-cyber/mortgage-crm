/**
 * Mortgage Insurance Types
 * @module lib/mortgageInsurance/types
 */

/**
 * @typedef {'conventional' | 'fha' | 'va' | 'usda'} LoanType
 */

/**
 * @typedef {'monthly' | 'single' | 'split' | 'lender_paid'} PMIPaymentType
 * - monthly: Borrower pays monthly premium (most common)
 * - single: One-time upfront premium (can be financed)
 * - split: Combination of upfront + reduced monthly
 * - lender_paid: Lender pays PMI in exchange for higher rate
 */

/**
 * @typedef {'standard' | 'high_ltv' | 'relocation' | 'affordable'} PMIProgramType
 */

/**
 * @typedef {Object} CreditScoreTier
 * @property {number} min - Minimum credit score
 * @property {number} max - Maximum credit score
 * @property {string} tier - Tier name (excellent, good, fair, poor)
 */

/**
 * @typedef {Object} PMIRateEntry
 * @property {number} minLTV - Minimum LTV (e.g., 0.85)
 * @property {number} maxLTV - Maximum LTV (e.g., 0.90)
 * @property {number} minCredit - Minimum credit score
 * @property {number} maxCredit - Maximum credit score
 * @property {number} annualRate - Annual PMI rate as decimal (e.g., 0.0058 = 0.58%)
 */

/**
 * @typedef {Object} FHAMIPRates
 * @property {number} upfrontRate - Upfront MIP rate (currently 1.75%)
 * @property {number} annualRate - Annual MIP rate based on loan term and LTV
 * @property {number} durationYears - How long MIP is required (11 years or life of loan)
 */

/**
 * @typedef {Object} VAFundingFeeRates
 * @property {number} firstTimeUse - Rate for first-time VA loan users
 * @property {number} subsequentUse - Rate for subsequent VA loan users
 * @property {boolean} exempt - Whether veteran is exempt (disability rating)
 */

/**
 * @typedef {Object} MortgageInsuranceInput
 * @property {LoanType} loanType - Type of loan
 * @property {number} loanAmount - Loan amount in dollars
 * @property {number} homeValue - Home value / purchase price
 * @property {number} creditScore - Borrower's credit score
 * @property {PMIPaymentType} [paymentType='monthly'] - How PMI is paid
 * @property {number} [loanTermYears=30] - Loan term in years
 * @property {boolean} [isFirstTimeVAUse=true] - For VA loans, is this first use
 * @property {boolean} [isVAExempt=false] - For VA loans, disability exemption
 * @property {number} [downPaymentPercent] - Down payment percentage (calculated from LTV if not provided)
 * @property {string} [propertyType='single_family'] - Property type
 * @property {boolean} [isFirstTimeHomeBuyer=false] - First time home buyer status
 */

/**
 * @typedef {Object} MortgageInsuranceOutput
 * @property {boolean} required - Whether mortgage insurance is required
 * @property {string} type - Type of insurance (PMI, MIP, VA Funding Fee, USDA Guarantee Fee)
 * @property {number} monthlyPremium - Monthly premium amount
 * @property {number} annualPremium - Annual premium amount
 * @property {number} upfrontPremium - One-time upfront premium (if applicable)
 * @property {number} totalFirstYearCost - Total first year cost (upfront + 12 months)
 * @property {number} annualRate - Annual rate as decimal
 * @property {number} ltv - Loan-to-value ratio
 * @property {CancellationInfo} cancellation - When/how insurance can be cancelled
 * @property {string} [notes] - Additional notes or recommendations
 * @property {PMIComparison[]} [alternatives] - Alternative payment options
 */

/**
 * @typedef {Object} CancellationInfo
 * @property {boolean} canCancel - Whether PMI can be cancelled
 * @property {string} method - How to cancel (automatic, request, refinance, none)
 * @property {number} [automaticLTV] - LTV at which PMI automatically cancels
 * @property {number} [requestLTV] - LTV at which borrower can request cancellation
 * @property {string} [requirements] - Additional requirements for cancellation
 * @property {number} [estimatedMonths] - Estimated months until cancellation eligible
 */

/**
 * @typedef {Object} PMIComparison
 * @property {PMIPaymentType} paymentType
 * @property {number} monthlyPremium
 * @property {number} upfrontPremium
 * @property {number} totalCost5Years - Total cost over 5 years
 * @property {number} effectiveRate - Effective annual rate
 */

// Export constants for use in components
export const LOAN_TYPES = {
  CONVENTIONAL: 'conventional',
  FHA: 'fha',
  VA: 'va',
  USDA: 'usda',
};

export const PMI_PAYMENT_TYPES = {
  MONTHLY: 'monthly',
  SINGLE: 'single',
  SPLIT: 'split',
  LENDER_PAID: 'lender_paid',
};

export const CREDIT_SCORE_TIERS = [
  { min: 760, max: 850, tier: 'excellent' },
  { min: 720, max: 759, tier: 'very_good' },
  { min: 680, max: 719, tier: 'good' },
  { min: 640, max: 679, tier: 'fair' },
  { min: 620, max: 639, tier: 'minimum' },
  { min: 580, max: 619, tier: 'fha_minimum' },
  { min: 500, max: 579, tier: 'subprime' },
];

export const LTV_THRESHOLDS = {
  NO_PMI: 0.80,           // 80% LTV - no PMI required
  AUTOMATIC_CANCEL: 0.78, // 78% LTV - automatic PMI cancellation
  REQUEST_CANCEL: 0.80,   // 80% LTV - can request PMI cancellation
  FHA_LIFETIME_MIP: 0.90, // Above 90% LTV, FHA MIP for life of loan
  MAX_CONVENTIONAL: 0.97, // Maximum conventional LTV
  MAX_FHA: 0.9650,        // Maximum FHA LTV (96.5%)
  MAX_VA: 1.00,           // VA allows 100% financing
  MAX_USDA: 1.00,         // USDA allows 100% financing
};
