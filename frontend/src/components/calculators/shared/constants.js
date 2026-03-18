/**
 * Shared constants for calculator components
 */

// ============================================================================
// STATE/COUNTY TAX AND INSURANCE RATES
// ============================================================================

export const STATE_DATA = {
  CA: {
    name: 'California',
    avgTaxRate: 0.0073,
    avgInsuranceRate: 0.0035,
    counties: {
      'Los Angeles': { taxRate: 0.0072, insuranceRate: 0.0032 },
      'San Francisco': { taxRate: 0.0062, insuranceRate: 0.0045 },
      'San Diego': { taxRate: 0.0073, insuranceRate: 0.0030 },
      'Orange': { taxRate: 0.0076, insuranceRate: 0.0028 },
      'Santa Clara': { taxRate: 0.0067, insuranceRate: 0.0038 },
      'Alameda': { taxRate: 0.0081, insuranceRate: 0.0035 },
      'Sacramento': { taxRate: 0.0082, insuranceRate: 0.0028 },
      'Riverside': { taxRate: 0.0095, insuranceRate: 0.0032 },
    },
  },
  TX: {
    name: 'Texas',
    avgTaxRate: 0.0180,
    avgInsuranceRate: 0.0055,
    counties: {
      'Harris': { taxRate: 0.0218, insuranceRate: 0.0060 },
      'Dallas': { taxRate: 0.0195, insuranceRate: 0.0052 },
      'Travis': { taxRate: 0.0178, insuranceRate: 0.0048 },
      'Bexar': { taxRate: 0.0210, insuranceRate: 0.0045 },
      'Tarrant': { taxRate: 0.0220, insuranceRate: 0.0055 },
      'Collin': { taxRate: 0.0195, insuranceRate: 0.0042 },
    },
  },
  FL: {
    name: 'Florida',
    avgTaxRate: 0.0089,
    avgInsuranceRate: 0.0085,
    counties: {
      'Miami-Dade': { taxRate: 0.0097, insuranceRate: 0.0120 },
      'Broward': { taxRate: 0.0093, insuranceRate: 0.0110 },
      'Palm Beach': { taxRate: 0.0098, insuranceRate: 0.0095 },
      'Hillsborough': { taxRate: 0.0093, insuranceRate: 0.0075 },
      'Orange': { taxRate: 0.0089, insuranceRate: 0.0070 },
      'Duval': { taxRate: 0.0091, insuranceRate: 0.0065 },
    },
  },
  NY: {
    name: 'New York',
    avgTaxRate: 0.0172,
    avgInsuranceRate: 0.0045,
    counties: {
      'New York': { taxRate: 0.0088, insuranceRate: 0.0055 },
      'Kings': { taxRate: 0.0067, insuranceRate: 0.0048 },
      'Queens': { taxRate: 0.0088, insuranceRate: 0.0045 },
      'Suffolk': { taxRate: 0.0218, insuranceRate: 0.0042 },
      'Nassau': { taxRate: 0.0228, insuranceRate: 0.0040 },
      'Westchester': { taxRate: 0.0189, insuranceRate: 0.0038 },
    },
  },
  AZ: {
    name: 'Arizona',
    avgTaxRate: 0.0062,
    avgInsuranceRate: 0.0035,
    counties: {
      'Maricopa': { taxRate: 0.0058, insuranceRate: 0.0032 },
      'Pima': { taxRate: 0.0098, insuranceRate: 0.0030 },
      'Pinal': { taxRate: 0.0075, insuranceRate: 0.0028 },
    },
  },
  CO: {
    name: 'Colorado',
    avgTaxRate: 0.0051,
    avgInsuranceRate: 0.0038,
    counties: {
      'Denver': { taxRate: 0.0054, insuranceRate: 0.0042 },
      'El Paso': { taxRate: 0.0048, insuranceRate: 0.0035 },
      'Arapahoe': { taxRate: 0.0052, insuranceRate: 0.0038 },
      'Jefferson': { taxRate: 0.0055, insuranceRate: 0.0040 },
    },
  },
  WA: {
    name: 'Washington',
    avgTaxRate: 0.0093,
    avgInsuranceRate: 0.0028,
    counties: {
      'King': { taxRate: 0.0092, insuranceRate: 0.0030 },
      'Pierce': { taxRate: 0.0108, insuranceRate: 0.0028 },
      'Snohomish': { taxRate: 0.0088, insuranceRate: 0.0025 },
    },
  },
  NV: {
    name: 'Nevada',
    avgTaxRate: 0.0053,
    avgInsuranceRate: 0.0030,
    counties: {
      'Clark': { taxRate: 0.0054, insuranceRate: 0.0032 },
      'Washoe': { taxRate: 0.0063, insuranceRate: 0.0028 },
    },
  },
};

// Get rates for a location
export const getLocationRates = (state, county) => {
  const stateData = STATE_DATA[state];
  if (!stateData) {
    return { taxRate: 0.0107, insuranceRate: 0.0035, source: 'default' };
  }

  if (county && stateData.counties[county]) {
    return {
      taxRate: stateData.counties[county].taxRate,
      insuranceRate: stateData.counties[county].insuranceRate,
      source: 'county'
    };
  }

  return {
    taxRate: stateData.avgTaxRate,
    insuranceRate: stateData.avgInsuranceRate,
    source: 'state'
  };
};

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
    colorPrimary: '#8b5cf6',
    colorBg: '#f5f3ff',
    colorBorder: '#ddd6fe',
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
    colorPrimary: '#10b981',
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
  budget: {
    housing: 0,
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
  pointsDiscount: 0.25,
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
