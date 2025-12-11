/**
 * Mortgage Insurance Calculator
 * @module lib/mortgageInsurance/calculator
 */

import {
  getConventionalPMIRate,
  getFHAMIPRates,
  getVAFundingFeeRate,
  getUSDAGuaranteeFeeRates,
  getCreditTier,
  singlePremiumPMIRates,
  getLTVRangeKey,
} from './rateData';
import { LTV_THRESHOLDS } from './types';

/**
 * Calculate mortgage insurance for any loan type
 * @param {import('./types').MortgageInsuranceInput} input
 * @returns {import('./types').MortgageInsuranceOutput}
 */
export function calculateMortgageInsurance(input) {
  const {
    loanType = 'conventional',
    loanAmount,
    homeValue,
    creditScore = 720,
    paymentType = 'monthly',
    loanTermYears = 30,
    isFirstTimeVAUse = true,
    isVAExempt = false,
  } = input;

  const ltv = loanAmount / homeValue;
  const downPaymentPercent = ((homeValue - loanAmount) / homeValue) * 100;

  // Route to appropriate calculator based on loan type
  switch (loanType) {
    case 'fha':
      return calculateFHAMIP(loanAmount, homeValue, ltv, loanTermYears);
    case 'va':
      return calculateVAFundingFee(loanAmount, homeValue, ltv, downPaymentPercent, isFirstTimeVAUse, isVAExempt);
    case 'usda':
      return calculateUSDAGuaranteeFee(loanAmount, homeValue, ltv);
    case 'conventional':
    default:
      return calculateConventionalPMI(loanAmount, homeValue, ltv, creditScore, paymentType, loanTermYears);
  }
}

/**
 * Calculate conventional PMI
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} ltv
 * @param {number} creditScore
 * @param {string} paymentType
 * @param {number} loanTermYears
 * @returns {import('./types').MortgageInsuranceOutput}
 */
function calculateConventionalPMI(loanAmount, homeValue, ltv, creditScore, paymentType, loanTermYears) {
  // No PMI needed at 80% LTV or below
  if (ltv <= LTV_THRESHOLDS.NO_PMI) {
    return {
      required: false,
      type: 'none',
      monthlyPremium: 0,
      annualPremium: 0,
      upfrontPremium: 0,
      totalFirstYearCost: 0,
      annualRate: 0,
      ltv: ltv * 100,
      cancellation: {
        canCancel: false,
        method: 'not_applicable',
        requirements: 'No mortgage insurance required at 80% LTV or below',
      },
      notes: 'Congratulations! With 20% or more down, no PMI is required.',
    };
  }

  const isSinglePremium = paymentType === 'single';
  const annualRate = getConventionalPMIRate(creditScore, ltv, isSinglePremium);

  if (annualRate === null) {
    return createNoPMIResult(ltv);
  }

  let monthlyPremium = 0;
  let upfrontPremium = 0;
  let annualPremium = 0;

  if (isSinglePremium) {
    // Single premium is a one-time payment
    upfrontPremium = Math.round(loanAmount * annualRate);
    monthlyPremium = 0;
    annualPremium = 0;
  } else {
    // Monthly premium
    annualPremium = Math.round(loanAmount * annualRate);
    monthlyPremium = Math.round(annualPremium / 12);
  }

  // Calculate estimated months until PMI can be cancelled
  const estimatedMonthsToCancel = estimateMonthsToPMICancellation(
    loanAmount,
    homeValue,
    ltv,
    loanTermYears
  );

  // Get alternative payment options for comparison
  const alternatives = getAlternativeOptions(loanAmount, homeValue, ltv, creditScore, loanTermYears);

  return {
    required: true,
    type: 'PMI',
    monthlyPremium,
    annualPremium,
    upfrontPremium,
    totalFirstYearCost: upfrontPremium + (monthlyPremium * 12),
    annualRate,
    ltv: Math.round(ltv * 1000) / 10, // e.g., 95.0
    cancellation: {
      canCancel: true,
      method: 'automatic_and_request',
      automaticLTV: 78,
      requestLTV: 80,
      requirements: 'Good payment history, no subordinate liens, current on payments',
      estimatedMonths: estimatedMonthsToCancel,
    },
    creditTier: getCreditTier(creditScore),
    notes: generatePMINotes(ltv, creditScore, estimatedMonthsToCancel),
    alternatives: alternatives,
  };
}

/**
 * Calculate FHA MIP (Mortgage Insurance Premium)
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} ltv
 * @param {number} loanTermYears
 * @returns {import('./types').MortgageInsuranceOutput}
 */
function calculateFHAMIP(loanAmount, homeValue, ltv, loanTermYears) {
  const mipRates = getFHAMIPRates(ltv, loanTermYears, loanAmount);

  const upfrontPremium = Math.round(loanAmount * mipRates.upfront);
  const annualPremium = Math.round(loanAmount * mipRates.annual);
  const monthlyPremium = Math.round(annualPremium / 12);

  let cancellationInfo;
  if (mipRates.forLifeOfLoan) {
    cancellationInfo = {
      canCancel: false,
      method: 'refinance_only',
      requirements: 'MIP is required for the life of the loan when LTV > 90%. Refinance to conventional loan to remove.',
    };
  } else {
    cancellationInfo = {
      canCancel: true,
      method: 'automatic',
      automaticLTV: null,
      requirements: `MIP automatically cancels after ${mipRates.duration} years with LTV ≤ 90% at origination`,
      estimatedMonths: mipRates.duration * 12,
    };
  }

  return {
    required: true,
    type: 'FHA MIP',
    monthlyPremium,
    annualPremium,
    upfrontPremium,
    totalFirstYearCost: upfrontPremium + (monthlyPremium * 12),
    annualRate: mipRates.annual,
    upfrontRate: mipRates.upfront,
    ltv: Math.round(ltv * 1000) / 10,
    cancellation: cancellationInfo,
    notes: generateFHANotes(ltv, mipRates),
    breakdown: {
      upfrontMIP: {
        rate: `${(mipRates.upfront * 100).toFixed(2)}%`,
        amount: upfrontPremium,
        note: 'Can be financed into loan amount',
      },
      annualMIP: {
        rate: `${(mipRates.annual * 100).toFixed(2)}%`,
        monthlyAmount: monthlyPremium,
        duration: mipRates.forLifeOfLoan ? 'Life of loan' : `${mipRates.duration} years`,
      },
    },
  };
}

/**
 * Calculate VA Funding Fee
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} ltv
 * @param {number} downPaymentPercent
 * @param {boolean} isFirstUse
 * @param {boolean} isExempt
 * @returns {import('./types').MortgageInsuranceOutput}
 */
function calculateVAFundingFee(loanAmount, homeValue, ltv, downPaymentPercent, isFirstUse, isExempt) {
  const fundingFeeRate = getVAFundingFeeRate(downPaymentPercent, isFirstUse, isExempt);
  const upfrontPremium = Math.round(loanAmount * fundingFeeRate);

  return {
    required: !isExempt && fundingFeeRate > 0,
    type: 'VA Funding Fee',
    monthlyPremium: 0, // VA has no monthly MI
    annualPremium: 0,
    upfrontPremium,
    totalFirstYearCost: upfrontPremium,
    annualRate: 0,
    upfrontRate: fundingFeeRate,
    ltv: Math.round(ltv * 1000) / 10,
    cancellation: {
      canCancel: false,
      method: 'not_applicable',
      requirements: 'VA loans have no monthly mortgage insurance. Funding fee is one-time.',
    },
    notes: generateVANotes(downPaymentPercent, isFirstUse, isExempt, fundingFeeRate),
    breakdown: {
      fundingFee: {
        rate: `${(fundingFeeRate * 100).toFixed(2)}%`,
        amount: upfrontPremium,
        note: 'Can be financed into loan amount',
        useType: isFirstUse ? 'First time use' : 'Subsequent use',
      },
    },
  };
}

/**
 * Calculate USDA Guarantee Fee
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} ltv
 * @returns {import('./types').MortgageInsuranceOutput}
 */
function calculateUSDAGuaranteeFee(loanAmount, homeValue, ltv) {
  const usdaRates = getUSDAGuaranteeFeeRates();

  const upfrontPremium = Math.round(loanAmount * usdaRates.upfront);
  const annualPremium = Math.round(loanAmount * usdaRates.annual);
  const monthlyPremium = Math.round(annualPremium / 12);

  return {
    required: true,
    type: 'USDA Guarantee Fee',
    monthlyPremium,
    annualPremium,
    upfrontPremium,
    totalFirstYearCost: upfrontPremium + (monthlyPremium * 12),
    annualRate: usdaRates.annual,
    upfrontRate: usdaRates.upfront,
    ltv: Math.round(ltv * 1000) / 10,
    cancellation: {
      canCancel: false,
      method: 'refinance_only',
      requirements: 'USDA annual fee is required for the life of the loan. Refinance to conventional to remove.',
    },
    notes: 'USDA loans offer 100% financing for eligible rural properties. Annual fee is lower than FHA MIP.',
    breakdown: {
      upfrontFee: {
        rate: `${(usdaRates.upfront * 100).toFixed(2)}%`,
        amount: upfrontPremium,
        note: 'Can be financed into loan amount',
      },
      annualFee: {
        rate: `${(usdaRates.annual * 100).toFixed(2)}%`,
        monthlyAmount: monthlyPremium,
        duration: 'Life of loan',
      },
    },
  };
}

/**
 * Estimate months until PMI can be cancelled
 * Based on normal amortization schedule
 */
function estimateMonthsToPMICancellation(loanAmount, homeValue, ltv, loanTermYears, interestRate = 0.07) {
  if (ltv <= 0.80) return 0;

  const targetLTV = 0.78; // Automatic cancellation threshold
  const targetLoanBalance = homeValue * targetLTV;
  const monthlyRate = interestRate / 12;
  const totalPayments = loanTermYears * 12;

  // Calculate monthly P&I payment
  const monthlyPayment = loanAmount * (monthlyRate * Math.pow(1 + monthlyRate, totalPayments)) /
    (Math.pow(1 + monthlyRate, totalPayments) - 1);

  // Simulate amortization to find when balance hits target
  let balance = loanAmount;
  let months = 0;

  while (balance > targetLoanBalance && months < totalPayments) {
    const interestPayment = balance * monthlyRate;
    const principalPayment = monthlyPayment - interestPayment;
    balance -= principalPayment;
    months++;
  }

  return months;
}

/**
 * Get alternative PMI payment options for comparison
 */
function getAlternativeOptions(loanAmount, homeValue, ltv, creditScore, loanTermYears) {
  const alternatives = [];
  const tier = getCreditTier(creditScore);
  const ltvKey = getLTVRangeKey(ltv);

  if (!ltvKey) return alternatives;

  // Monthly option
  const monthlyRate = getConventionalPMIRate(creditScore, ltv, false);
  if (monthlyRate) {
    const monthlyAnnual = loanAmount * monthlyRate;
    const monthlyPremium = monthlyAnnual / 12;
    alternatives.push({
      paymentType: 'monthly',
      monthlyPremium: Math.round(monthlyPremium),
      upfrontPremium: 0,
      totalCost5Years: Math.round(monthlyAnnual * 5),
      effectiveRate: monthlyRate,
      description: 'Pay monthly until 78% LTV reached',
    });
  }

  // Single premium option
  const singleRate = getConventionalPMIRate(creditScore, ltv, true);
  if (singleRate) {
    const singlePremium = loanAmount * singleRate;
    alternatives.push({
      paymentType: 'single',
      monthlyPremium: 0,
      upfrontPremium: Math.round(singlePremium),
      totalCost5Years: Math.round(singlePremium), // One-time cost
      effectiveRate: singleRate,
      description: 'One-time upfront payment (can be financed)',
    });
  }

  return alternatives;
}

/**
 * Create result for no PMI needed
 */
function createNoPMIResult(ltv) {
  return {
    required: false,
    type: 'none',
    monthlyPremium: 0,
    annualPremium: 0,
    upfrontPremium: 0,
    totalFirstYearCost: 0,
    annualRate: 0,
    ltv: Math.round(ltv * 1000) / 10,
    cancellation: {
      canCancel: false,
      method: 'not_applicable',
    },
  };
}

/**
 * Generate helpful notes for PMI
 */
function generatePMINotes(ltv, creditScore, estimatedMonths) {
  const notes = [];

  if (ltv > 0.95) {
    notes.push('High LTV (>95%) results in higher PMI rates. Consider a larger down payment if possible.');
  }

  if (creditScore < 700) {
    notes.push('Improving your credit score could significantly reduce your PMI rate.');
  }

  if (estimatedMonths) {
    const years = Math.floor(estimatedMonths / 12);
    const months = estimatedMonths % 12;
    if (years > 0) {
      notes.push(`PMI could be removed in approximately ${years} year${years > 1 ? 's' : ''}${months > 0 ? ` and ${months} month${months > 1 ? 's' : ''}` : ''} through normal payments.`);
    } else {
      notes.push(`PMI could be removed in approximately ${months} months through normal payments.`);
    }
  }

  notes.push('You can request PMI cancellation at 80% LTV with good payment history.');

  return notes.join(' ');
}

/**
 * Generate helpful notes for FHA MIP
 */
function generateFHANotes(ltv, mipRates) {
  const notes = [];

  notes.push(`Upfront MIP of ${(mipRates.upfront * 100).toFixed(2)}% can be financed into your loan.`);

  if (mipRates.forLifeOfLoan) {
    notes.push('With LTV > 90%, annual MIP is required for the life of the loan. Consider refinancing to conventional once you reach 20% equity to eliminate MI.');
  } else {
    notes.push(`Annual MIP will automatically cancel after ${mipRates.duration} years.`);
  }

  return notes.join(' ');
}

/**
 * Generate helpful notes for VA Funding Fee
 */
function generateVANotes(downPaymentPercent, isFirstUse, isExempt, fundingFeeRate) {
  if (isExempt) {
    return 'You are exempt from the VA Funding Fee due to disability status or other qualifying exemption.';
  }

  const notes = [];

  notes.push(`VA loans have no monthly mortgage insurance - only a one-time funding fee of ${(fundingFeeRate * 100).toFixed(2)}%.`);

  if (downPaymentPercent < 5) {
    notes.push('A down payment of 5% or more would reduce your funding fee.');
  }

  if (!isFirstUse) {
    notes.push('Subsequent VA loan use has higher funding fees than first-time use.');
  }

  notes.push('The funding fee can be financed into your loan amount.');

  return notes.join(' ');
}

/**
 * Simple PMI estimate for quick calculations
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} [creditScore=720]
 * @param {string} [loanType='conventional']
 * @returns {number} Monthly PMI amount
 */
export function estimateMortgageInsuranceSimple(loanAmount, homeValue, creditScore = 720, loanType = 'conventional') {
  const result = calculateMortgageInsurance({
    loanType,
    loanAmount,
    homeValue,
    creditScore,
  });

  return result.monthlyPremium;
}

/**
 * Compare all loan types for MI costs
 * @param {number} loanAmount
 * @param {number} homeValue
 * @param {number} creditScore
 * @returns {Object} Comparison of MI costs by loan type
 */
export function compareMortgageInsuranceByLoanType(loanAmount, homeValue, creditScore) {
  const ltv = loanAmount / homeValue;
  const downPaymentPercent = ((homeValue - loanAmount) / homeValue) * 100;

  const comparison = {
    conventional: calculateConventionalPMI(loanAmount, homeValue, ltv, creditScore, 'monthly', 30),
    fha: calculateFHAMIP(loanAmount, homeValue, ltv, 30),
    va: calculateVAFundingFee(loanAmount, homeValue, ltv, downPaymentPercent, true, false),
    usda: calculateUSDAGuaranteeFee(loanAmount, homeValue, ltv),
  };

  // Calculate 5-year cost for each
  const fiveYearComparison = {};
  for (const [type, result] of Object.entries(comparison)) {
    const monthlyMonths = type === 'conventional' ?
      Math.min(60, result.cancellation?.estimatedMonths || 60) : 60;

    fiveYearComparison[type] = {
      type: result.type,
      upfrontCost: result.upfrontPremium,
      monthlyPayment: result.monthlyPremium,
      fiveYearCost: result.upfrontPremium + (result.monthlyPremium * monthlyMonths),
      canCancel: result.cancellation?.canCancel || false,
    };
  }

  return {
    details: comparison,
    fiveYearComparison,
    recommendation: generateRecommendation(fiveYearComparison, creditScore, ltv),
  };
}

/**
 * Generate recommendation based on comparison
 */
function generateRecommendation(comparison, creditScore, ltv) {
  const costs = Object.entries(comparison)
    .map(([type, data]) => ({ type, ...data }))
    .sort((a, b) => a.fiveYearCost - b.fiveYearCost);

  const cheapest = costs[0];
  let recommendation = `Based on 5-year cost, ${cheapest.type.toUpperCase()} has the lowest mortgage insurance cost.`;

  if (cheapest.type === 'conventional' && comparison.conventional.canCancel) {
    recommendation += ' Conventional PMI can be cancelled once you reach 20% equity, potentially saving more long-term.';
  }

  if (creditScore >= 720 && ltv <= 0.95) {
    recommendation += ' Your good credit score qualifies you for competitive conventional PMI rates.';
  }

  return recommendation;
}
