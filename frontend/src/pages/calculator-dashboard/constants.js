/**
 * Calculator Dashboard Constants
 *
 * Phase configuration, default profiles, and market assumptions.
 */

// ============================================================================
// CALCULATOR PHASES CONFIGURATION
// ============================================================================

export const CALCULATOR_PHASES = [
  {
    id: 'phase-1',
    name: 'Can I Buy?',
    subtitle: 'Affordability & Qualification',
    icon: '\u{1F3E0}',
    colorPrimary: '#3b82f6',
    colorBg: '#eff6ff',
    colorBorder: '#bfdbfe',
    calculators: [
      'down-payment',
      'cash-reserves',
      'emergency-runway',
      'program-options',
      'dti',
      'stress-test'
    ]
  },
  {
    id: 'phase-2',
    name: 'What Does This Really Cost?',
    subtitle: 'True Cost Analysis',
    icon: '\u{1F4B0}',
    colorPrimary: '#B8924A',
    colorBg: '#FDF9F0',
    colorBorder: '#F5EDD9',
    calculators: [
      'monthly-payment',
      'closing-costs',
      'payment-shock',
      'lifestyle-fit',
      'rent-vs-buy',
      'cost-to-waiting'
    ]
  },
  {
    id: 'phase-3',
    name: 'Is This Smart Long-Term?',
    subtitle: 'Strategic Planning',
    icon: '\u{1F4C8}',
    colorPrimary: '#2D7A52',
    colorBg: '#ecfdf5',
    colorBorder: '#a7f3d0',
    calculators: [
      'break-even-horizon',
      'equity-velocity',
      'tax-benefit',
      'inflation-hedge',
      'prepay-or-invest',
      'repayment-strategy',
      'exit-strategy',
      'job-mobility'
    ]
  }
];

// Helper to get phase for a calculator
export const getCalculatorPhase = (calcId) => {
  for (const phase of CALCULATOR_PHASES) {
    if (phase.calculators.includes(calcId)) {
      return phase;
    }
  }
  return null;
};

// ============================================================================
// DEFAULT SCENARIO DATA
// ============================================================================

export const DEFAULT_PROFILE = {
  name: 'Alex',
  age: 31,
  annualIncome: 92000,
  monthlyIncome: 92000 / 12,
  savings: 28000,
  monthlyDebts: 670,
  debtBreakdown: [
    { name: 'Student Loan', amount: 450 },
    { name: 'Car Payment', amount: 220 },
  ],
  creditScore: 710,
  currentRent: 1800,
  // Budget items
  budget: {
    housing: 0, // Will be calculated
    utilities: 200,
    food: 500,
    transportation: 350,
    insurance: 150,
    healthcare: 100,
    entertainment: 200,
    savings: 400,
    other: 250,
  },
};

export const DEFAULT_MARKET = {
  interestRate: 6.875,
  termYears: 30,
  points: 0,
  pointsDiscount: 0.25, // Each point reduces rate by 0.25%
  taxRate: 0.0107,
  insuranceRate: 0.0035,
};

export const DEFAULT_PROPERTY = {
  homePrice: 285000,
  homePrices: {
    conservative: 221000,
    moderate: 248000,
    baseline: 285000,
    stretch: 320000,
  },
  downPaymentPct: 5,
  state: 'CA',
  county: 'Los Angeles',
  propertyType: 'single_family',
  hoaMonthly: 0,
  taxRateOverride: null,
  insuranceRateOverride: null,
};

// Legacy constants for backwards compatibility
export const ALEX_PROFILE = DEFAULT_PROFILE;
export const MARKET_ASSUMPTIONS = DEFAULT_MARKET;
