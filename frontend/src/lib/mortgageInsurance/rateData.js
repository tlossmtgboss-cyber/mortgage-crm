/**
 * Mortgage Insurance Rate Data
 * @module lib/mortgageInsurance/rateData
 *
 * Rate tables based on industry averages from major PMI providers (MGIC, Radian, Essent, etc.)
 * FHA MIP rates from HUD guidelines
 * VA Funding Fee rates from VA guidelines
 */

/**
 * Conventional PMI Monthly Rates
 * Rates are annual percentages of loan amount
 * Organized by LTV range and credit score
 */
export const conventionalPMIRates = {
  // Credit Score 760+
  excellent: {
    '95.01-97': 0.0098,   // 0.98%
    '90.01-95': 0.0078,   // 0.78%
    '85.01-90': 0.0052,   // 0.52%
    '80.01-85': 0.0032,   // 0.32%
  },
  // Credit Score 740-759
  veryGood: {
    '95.01-97': 0.0105,   // 1.05%
    '90.01-95': 0.0085,   // 0.85%
    '85.01-90': 0.0058,   // 0.58%
    '80.01-85': 0.0038,   // 0.38%
  },
  // Credit Score 720-739
  good: {
    '95.01-97': 0.0118,   // 1.18%
    '90.01-95': 0.0095,   // 0.95%
    '85.01-90': 0.0065,   // 0.65%
    '80.01-85': 0.0044,   // 0.44%
  },
  // Credit Score 700-719
  aboveAverage: {
    '95.01-97': 0.0135,   // 1.35%
    '90.01-95': 0.0108,   // 1.08%
    '85.01-90': 0.0078,   // 0.78%
    '80.01-85': 0.0052,   // 0.52%
  },
  // Credit Score 680-699
  average: {
    '95.01-97': 0.0155,   // 1.55%
    '90.01-95': 0.0125,   // 1.25%
    '85.01-90': 0.0095,   // 0.95%
    '80.01-85': 0.0065,   // 0.65%
  },
  // Credit Score 660-679
  belowAverage: {
    '95.01-97': 0.0185,   // 1.85%
    '90.01-95': 0.0150,   // 1.50%
    '85.01-90': 0.0115,   // 1.15%
    '80.01-85': 0.0082,   // 0.82%
  },
  // Credit Score 640-659
  fair: {
    '95.01-97': 0.0210,   // 2.10%
    '90.01-95': 0.0175,   // 1.75%
    '85.01-90': 0.0135,   // 1.35%
    '80.01-85': 0.0098,   // 0.98%
  },
  // Credit Score 620-639
  minimum: {
    '95.01-97': 0.0235,   // 2.35%
    '90.01-95': 0.0195,   // 1.95%
    '85.01-90': 0.0155,   // 1.55%
    '80.01-85': 0.0115,   // 1.15%
  },
};

/**
 * Single Premium PMI Rates (one-time upfront payment)
 * Can be financed into the loan or paid at closing
 * Generally 1.5x to 3x the annual rate as a one-time payment
 */
export const singlePremiumPMIRates = {
  excellent: {
    '95.01-97': 0.0295,   // 2.95% one-time
    '90.01-95': 0.0235,   // 2.35%
    '85.01-90': 0.0155,   // 1.55%
    '80.01-85': 0.0095,   // 0.95%
  },
  veryGood: {
    '95.01-97': 0.0320,
    '90.01-95': 0.0255,
    '85.01-90': 0.0175,
    '80.01-85': 0.0115,
  },
  good: {
    '95.01-97': 0.0355,
    '90.01-95': 0.0285,
    '85.01-90': 0.0195,
    '80.01-85': 0.0135,
  },
  aboveAverage: {
    '95.01-97': 0.0405,
    '90.01-95': 0.0325,
    '85.01-90': 0.0235,
    '80.01-85': 0.0155,
  },
  average: {
    '95.01-97': 0.0465,
    '90.01-95': 0.0375,
    '85.01-90': 0.0285,
    '80.01-85': 0.0195,
  },
  belowAverage: {
    '95.01-97': 0.0555,
    '90.01-95': 0.0450,
    '85.01-90': 0.0345,
    '80.01-85': 0.0245,
  },
  fair: {
    '95.01-97': 0.0630,
    '90.01-95': 0.0525,
    '85.01-90': 0.0405,
    '80.01-85': 0.0295,
  },
  minimum: {
    '95.01-97': 0.0705,
    '90.01-95': 0.0585,
    '85.01-90': 0.0465,
    '80.01-85': 0.0345,
  },
};

/**
 * FHA Mortgage Insurance Premium (MIP) Rates
 * Current rates as of 2024
 */
export const fhaMIPRates = {
  // Upfront MIP - same for all loans
  upfront: 0.0175, // 1.75% of loan amount

  // Annual MIP rates based on loan term and LTV
  // For loans > 15 years (most common)
  annual: {
    standard: {
      // LTV <= 90%: 11 years of MIP
      '90AndUnder': {
        rate: 0.0050, // 0.50% annually
        duration: 11, // years
        forLifeOfLoan: false,
      },
      // LTV > 90%: MIP for life of loan
      'over90': {
        rate: 0.0055, // 0.55% annually
        duration: null,
        forLifeOfLoan: true,
      },
    },
    // For loans <= 15 years with loan amount <= $726,200
    shortTerm: {
      '90AndUnder': {
        rate: 0.0015, // 0.15%
        duration: 11,
        forLifeOfLoan: false,
      },
      'over90': {
        rate: 0.0040, // 0.40%
        duration: null,
        forLifeOfLoan: true,
      },
    },
  },

  // Minimum down payment requirements
  minimumDown: {
    creditScore580Plus: 0.035, // 3.5% minimum down
    creditScore500to579: 0.10, // 10% minimum down
  },
};

/**
 * VA Funding Fee Rates
 * Rates vary by down payment, loan type, and whether first or subsequent use
 */
export const vaFundingFeeRates = {
  purchase: {
    firstUse: {
      'noDown': 0.0215,      // 2.15% with no down payment
      '5to10Down': 0.0150,   // 1.50% with 5-10% down
      '10PlusDown': 0.0125,  // 1.25% with 10%+ down
    },
    subsequentUse: {
      'noDown': 0.0330,      // 3.30% with no down payment
      '5to10Down': 0.0150,   // 1.50% with 5-10% down
      '10PlusDown': 0.0125,  // 1.25% with 10%+ down
    },
  },
  refinance: {
    cashOut: {
      firstUse: 0.0215,
      subsequentUse: 0.0330,
    },
    irrrl: 0.0050, // Interest Rate Reduction Refinance Loan
  },

  // Exemptions - no funding fee required
  exemptions: [
    'Receiving VA disability compensation',
    'Eligible for VA disability compensation (pending rating)',
    'Surviving spouse of veteran who died in service or from service-connected disability',
    'Purple Heart recipient serving on active duty',
  ],
};

/**
 * USDA Guarantee Fee Rates
 * For Rural Development loans
 */
export const usdaGuaranteeFeeRates = {
  upfront: 0.01, // 1.0% of loan amount
  annual: 0.0035, // 0.35% annually (for life of loan)
};

/**
 * Get credit tier based on credit score
 * @param {number} creditScore
 * @returns {string} tier name
 */
export function getCreditTier(creditScore) {
  if (creditScore >= 760) return 'excellent';
  if (creditScore >= 740) return 'veryGood';
  if (creditScore >= 720) return 'good';
  if (creditScore >= 700) return 'aboveAverage';
  if (creditScore >= 680) return 'average';
  if (creditScore >= 660) return 'belowAverage';
  if (creditScore >= 640) return 'fair';
  if (creditScore >= 620) return 'minimum';
  return 'subMinimum';
}

/**
 * Get LTV range key for rate lookup
 * @param {number} ltv - LTV as decimal (e.g., 0.95)
 * @returns {string} LTV range key
 */
export function getLTVRangeKey(ltv) {
  const ltvPercent = ltv * 100;
  if (ltvPercent > 95) return '95.01-97';
  if (ltvPercent > 90) return '90.01-95';
  if (ltvPercent > 85) return '85.01-90';
  if (ltvPercent > 80) return '80.01-85';
  return null; // No PMI needed
}

/**
 * Get conventional PMI rate
 * @param {number} creditScore
 * @param {number} ltv - LTV as decimal
 * @param {boolean} [singlePremium=false] - Use single premium rates
 * @returns {number|null} Annual rate as decimal, or null if no PMI needed
 */
export function getConventionalPMIRate(creditScore, ltv, singlePremium = false) {
  if (ltv <= 0.80) return null;

  const tier = getCreditTier(creditScore);
  const ltvKey = getLTVRangeKey(ltv);

  if (!ltvKey) return null;

  const rateTable = singlePremium ? singlePremiumPMIRates : conventionalPMIRates;
  const tierRates = rateTable[tier];

  if (!tierRates) {
    // Credit score too low for conventional, use highest available rate
    return rateTable.minimum[ltvKey] * 1.1;
  }

  return tierRates[ltvKey] || null;
}

/**
 * Get FHA MIP rates
 * @param {number} ltv - LTV as decimal
 * @param {number} loanTermYears
 * @param {number} loanAmount
 * @returns {{upfront: number, annual: number, duration: number|null, forLifeOfLoan: boolean}}
 */
export function getFHAMIPRates(ltv, loanTermYears = 30, loanAmount = 0) {
  const isShortTerm = loanTermYears <= 15 && loanAmount <= 726200;
  const ltvCategory = ltv <= 0.90 ? '90AndUnder' : 'over90';

  const annualData = isShortTerm
    ? fhaMIPRates.annual.shortTerm[ltvCategory]
    : fhaMIPRates.annual.standard[ltvCategory];

  return {
    upfront: fhaMIPRates.upfront,
    annual: annualData.rate,
    duration: annualData.duration,
    forLifeOfLoan: annualData.forLifeOfLoan,
  };
}

/**
 * Get VA Funding Fee rate
 * @param {number} downPaymentPercent - Down payment as percentage (e.g., 5 for 5%)
 * @param {boolean} isFirstUse
 * @param {boolean} isExempt
 * @returns {number} Funding fee rate as decimal
 */
export function getVAFundingFeeRate(downPaymentPercent, isFirstUse = true, isExempt = false) {
  if (isExempt) return 0;

  const useType = isFirstUse ? 'firstUse' : 'subsequentUse';

  if (downPaymentPercent >= 10) {
    return vaFundingFeeRates.purchase[useType]['10PlusDown'];
  } else if (downPaymentPercent >= 5) {
    return vaFundingFeeRates.purchase[useType]['5to10Down'];
  } else {
    return vaFundingFeeRates.purchase[useType]['noDown'];
  }
}

/**
 * Get USDA Guarantee Fee rates
 * @returns {{upfront: number, annual: number}}
 */
export function getUSDAGuaranteeFeeRates() {
  return {
    upfront: usdaGuaranteeFeeRates.upfront,
    annual: usdaGuaranteeFeeRates.annual,
  };
}
