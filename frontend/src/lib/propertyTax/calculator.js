/**
 * Property Tax Calculator
 * @module lib/propertyTax/calculator
 */

import { getCountyByFips, getDefaultEffectiveRate } from './countyData';

/**
 * Estimate property tax for a given property
 * @param {import('./types').TaxInput} input - Tax calculation input
 * @returns {import('./types').TaxOutput}
 */
export function estimatePropertyTax(input) {
  const { countyConfig, propertyUse, marketValue, exemptions } = input;

  if (countyConfig?.advanced) {
    return calculateAdvancedTax(input);
  } else {
    return calculateEffectiveRateTax(input);
  }
}

/**
 * Calculate tax using advanced millage-based method
 * @param {import('./types').TaxInput} input
 * @returns {import('./types').TaxOutput}
 */
function calculateAdvancedTax(input) {
  const { countyConfig, propertyUse, marketValue, exemptions } = input;
  const advanced = countyConfig.advanced;

  const assessmentRatio = advanced.assessmentRatios?.[propertyUse] || 0.04;
  const assessedValue = Math.round(marketValue * assessmentRatio);

  const baseMillage = advanced.millageRates?.baseMillage || 0;
  const baseTax = assessedValue * baseMillage;

  let credits = 0;
  if (advanced.creditsPerDollar) {
    const countyCredit = (advanced.creditsPerDollar.countyCredit || 0) * marketValue;
    const cityCredit = (advanced.creditsPerDollar.cityCredit || 0) * marketValue;
    credits = countyCredit + cityCredit;
  }

  let ptrCredit = 0;
  if (advanced.ptrMillage && propertyUse === 'primaryResidence') {
    ptrCredit = assessedValue * advanced.ptrMillage;
  }

  const flatFees = (advanced.flatFees?.solidWaste || 0) + (advanced.flatFees?.fireFee || 0);

  let taxAfterCredits = Math.max(baseTax - credits - ptrCredit, 0);

  if (exemptions?.customPercentReduction) {
    taxAfterCredits *= (1 - exemptions.customPercentReduction);
  }

  const annualTax = Math.round(taxAfterCredits + flatFees);
  const monthlyTax = Math.round(annualTax / 12);

  return {
    annualTax,
    monthlyTax,
    method: 'advanced',
    debug: {
      state: countyConfig.state,
      countyName: countyConfig.countyName,
      marketValue,
      assessedValue,
      baseMillage,
      taxBeforeCredits: baseTax,
      totalCredits: credits,
      ptrCredit,
      taxAfterCredits,
      totalFlatFees: flatFees,
    },
  };
}

/**
 * Calculate tax using simple effective rate method
 * @param {import('./types').TaxInput} input
 * @returns {import('./types').TaxOutput}
 */
function calculateEffectiveRateTax(input) {
  const { countyConfig, marketValue, exemptions } = input;

  const effectiveRate = countyConfig?.effectiveRate || 0.01;
  let annualTax = marketValue * effectiveRate;

  if (exemptions?.customPercentReduction) {
    annualTax *= (1 - exemptions.customPercentReduction);
  }

  annualTax = Math.round(annualTax);
  const monthlyTax = Math.round(annualTax / 12);

  return {
    annualTax,
    monthlyTax,
    method: 'effectiveRate',
    debug: {
      state: countyConfig?.state,
      countyName: countyConfig?.countyName,
      marketValue,
      effectiveRate,
    },
  };
}

/**
 * Estimate property tax with minimal inputs
 * @param {Object} params
 * @param {number} params.homeValue - Home market value
 * @param {string} [params.stateCode] - Two-letter state code
 * @param {string} [params.countyFips] - County FIPS code
 * @param {string} [params.propertyUse='primaryResidence'] - Property use type
 * @returns {import('./types').TaxOutput}
 */
export function estimatePropertyTaxSimple({
  homeValue,
  stateCode,
  countyFips,
  propertyUse = 'primaryResidence',
}) {
  let countyConfig = null;

  if (countyFips) {
    countyConfig = getCountyByFips(countyFips);
  }

  if (!countyConfig && stateCode) {
    // Use state default rate
    countyConfig = {
      state: stateCode,
      countyName: 'Default',
      fips: 'default',
      effectiveRate: getDefaultEffectiveRate(stateCode),
    };
  }

  if (!countyConfig) {
    // Use national average
    countyConfig = {
      state: 'US',
      countyName: 'Default',
      fips: 'default',
      effectiveRate: 0.0107,
    };
  }

  return estimatePropertyTax({
    countyConfig,
    propertyUse,
    marketValue: homeValue,
  });
}

/**
 * Calculate monthly mortgage payment (P&I only)
 * @param {Object} params
 * @param {number} params.loanAmount
 * @param {number} params.interestRate - Annual rate as decimal (e.g., 0.07 for 7%)
 * @param {number} params.loanTermMonths
 * @returns {number}
 */
export function calculatePrincipalAndInterest({ loanAmount, interestRate, loanTermMonths }) {
  const monthlyRate = interestRate / 12;

  if (monthlyRate === 0) {
    return loanAmount / loanTermMonths;
  }

  return (loanAmount * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -loanTermMonths));
}

/**
 * Calculate complete monthly payment with all components
 * @param {Object} params
 * @param {number} params.loanAmount
 * @param {number} params.interestRate - Annual rate as decimal
 * @param {number} params.loanTermMonths
 * @param {number} params.propertyTaxMonthly
 * @param {number} params.homeownersInsuranceMonthly
 * @param {number} [params.hoaMonthly=0]
 * @param {number} [params.pmiMonthly=0]
 * @returns {Object}
 */
export function calculateMonthlyPayment({
  loanAmount,
  interestRate,
  loanTermMonths,
  propertyTaxMonthly,
  homeownersInsuranceMonthly,
  hoaMonthly = 0,
  pmiMonthly = 0,
}) {
  const principalAndInterest = calculatePrincipalAndInterest({
    loanAmount,
    interestRate,
    loanTermMonths,
  });

  return {
    principalAndInterest: Math.round(principalAndInterest),
    propertyTax: Math.round(propertyTaxMonthly),
    homeownersInsurance: Math.round(homeownersInsuranceMonthly),
    hoa: Math.round(hoaMonthly),
    pmi: Math.round(pmiMonthly),
    totalMonthly: Math.round(
      principalAndInterest + propertyTaxMonthly + homeownersInsuranceMonthly + hoaMonthly + pmiMonthly
    ),
  };
}

/**
 * Calculate PMI estimate based on LTV (simple version for backward compatibility)
 * For detailed MI calculations, use the mortgageInsurance module
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} [creditScore=720] - Borrower's credit score
 * @returns {number} Monthly PMI amount
 */
export function estimatePMI(loanAmount, homeValue, creditScore = 720) {
  const ltv = loanAmount / homeValue;

  if (ltv <= 0.80) {
    return 0; // No PMI needed
  }

  // Use credit score to determine rate tier
  let rateMultiplier = 1.0;
  if (creditScore >= 760) {
    rateMultiplier = 0.65;
  } else if (creditScore >= 740) {
    rateMultiplier = 0.75;
  } else if (creditScore >= 720) {
    rateMultiplier = 0.85;
  } else if (creditScore >= 700) {
    rateMultiplier = 1.0;
  } else if (creditScore >= 680) {
    rateMultiplier = 1.15;
  } else if (creditScore >= 660) {
    rateMultiplier = 1.35;
  } else {
    rateMultiplier = 1.55;
  }

  // Base PMI rates by LTV
  let baseAnnualRate;
  if (ltv > 0.95) {
    baseAnnualRate = 0.0118; // 1.18%
  } else if (ltv > 0.90) {
    baseAnnualRate = 0.0095; // 0.95%
  } else if (ltv > 0.85) {
    baseAnnualRate = 0.0065; // 0.65%
  } else {
    baseAnnualRate = 0.0044; // 0.44%
  }

  const annualPMIRate = baseAnnualRate * rateMultiplier;
  return Math.round((loanAmount * annualPMIRate) / 12);
}

/**
 * Format currency for display
 * @param {number} amount
 * @returns {string}
 */
export function formatCurrency(amount) {
  if (amount === null || amount === undefined) {
    return '$0';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format percentage for display
 * @param {number} value - Decimal value (e.g., 0.07 for 7%)
 * @param {number} [decimals=2]
 * @returns {string}
 */
export function formatPercentage(value, decimals = 2) {
  if (value === null || value === undefined) {
    return '0%';
  }
  return `${(value * 100).toFixed(decimals)}%`;
}
