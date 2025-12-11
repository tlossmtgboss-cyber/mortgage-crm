/**
 * Homeowners Insurance Calculator
 * @module lib/insurance/calculator
 */

import { getStateInsuranceData, getCountyInsuranceData } from './stateData';

/**
 * Estimate homeowners insurance premium
 * @param {import('./types').InsuranceInput} input
 * @returns {import('./types').InsuranceOutput}
 */
export function estimateHomeownersInsurance(input) {
  const { homeCharacteristics, riskFactors } = input;

  if (homeCharacteristics && riskFactors) {
    return calculateAdvancedPremium(input);
  } else if (input.countyFips) {
    return calculateStandardPremium(input);
  } else {
    return calculateBasicPremium(input);
  }
}

/**
 * Calculate basic premium using state averages
 * @param {import('./types').InsuranceInput} input
 * @returns {import('./types').InsuranceOutput}
 */
function calculateBasicPremium(input) {
  const { stateCode, homeValue, coverageOptions, discounts } = input;
  const stateData = getStateInsuranceData(stateCode);

  const dwellingCoverage = coverageOptions.dwellingCoverage;
  const basePremium = (dwellingCoverage / 1000) * (stateData?.costPerThousand || 5.5);

  const deductibleFactor = getDeductibleFactor(coverageOptions.deductible);
  const adjustedPremium = basePremium * deductibleFactor;

  let discountAmount = 0;
  if (discounts?.multiPolicy) {
    discountAmount = adjustedPremium * 0.15;
  }

  const finalPremium = adjustedPremium - discountAmount;
  const annualPremium = Math.round(finalPremium);
  const monthlyPremium = Math.round(annualPremium / 12);

  return {
    annualPremium,
    monthlyPremium,
    method: 'basic',
    breakdown: {
      basePremium: Math.round(basePremium),
      riskAdjustments: Math.round(adjustedPremium - basePremium),
      discountAmount: Math.round(discountAmount),
      finalPremium: annualPremium,
    },
    coverageSummary: {
      dwelling: dwellingCoverage,
      personalProperty: Math.round(dwellingCoverage * 0.5),
      liability: coverageOptions.liabilityCoverage || 100000,
      deductible: coverageOptions.deductible,
    },
  };
}

/**
 * Calculate standard premium with county adjustments
 * @param {import('./types').InsuranceInput} input
 * @returns {import('./types').InsuranceOutput}
 */
function calculateStandardPremium(input) {
  const { stateCode, countyFips, coverageOptions, riskFactors, discounts } = input;
  const stateData = getStateInsuranceData(stateCode);
  const countyData = getCountyInsuranceData(stateCode, countyFips);

  const dwellingCoverage = coverageOptions.dwellingCoverage;
  let basePremium = (dwellingCoverage / 1000) * (stateData?.costPerThousand || 5.5);

  if (countyData) {
    basePremium *= countyData.riskMultiplier;
  }

  let riskAdjustment = 0;
  if (riskFactors) {
    if (riskFactors.coastalProperty) riskAdjustment += basePremium * 0.25;
    if (riskFactors.wildFireZone) riskAdjustment += basePremium * 0.20;
    if (riskFactors.windstormZone) riskAdjustment += basePremium * 0.10;
    if (riskFactors.floodZone) riskAdjustment += basePremium * 0.15;
    if (riskFactors.crimeHigh) riskAdjustment += basePremium * 0.10;
    if (riskFactors.crimeLow) riskAdjustment -= basePremium * 0.05;
    if (riskFactors.gatedCommunity) riskAdjustment -= basePremium * 0.05;
  }

  const premiumAfterRisk = basePremium + riskAdjustment;
  const deductibleFactor = getDeductibleFactor(coverageOptions.deductible);
  const premiumAfterDeductible = premiumAfterRisk * deductibleFactor;
  const discountAmount = calculateDiscounts(premiumAfterDeductible, discounts);

  const finalPremium = premiumAfterDeductible - discountAmount;
  const annualPremium = Math.round(finalPremium);
  const monthlyPremium = Math.round(annualPremium / 12);

  return {
    annualPremium,
    monthlyPremium,
    method: 'standard',
    breakdown: {
      basePremium: Math.round(basePremium),
      riskAdjustments: Math.round(riskAdjustment),
      discountAmount: Math.round(discountAmount),
      finalPremium: annualPremium,
    },
    coverageSummary: {
      dwelling: dwellingCoverage,
      personalProperty: Math.round(dwellingCoverage * 0.6),
      liability: coverageOptions.liabilityCoverage || 300000,
      deductible: coverageOptions.deductible,
    },
  };
}

/**
 * Calculate advanced premium with home characteristics
 * @param {import('./types').InsuranceInput} input
 * @returns {import('./types').InsuranceOutput}
 */
function calculateAdvancedPremium(input) {
  const { stateCode, coverageOptions, homeCharacteristics, riskFactors, discounts } = input;
  const stateData = getStateInsuranceData(stateCode);
  const dwellingCoverage = coverageOptions.dwellingCoverage;

  let basePremium = (dwellingCoverage / 1000) * (stateData?.costPerThousand || 5.5);
  let riskAdjustment = 0;
  const recommendations = [];

  if (homeCharacteristics) {
    const homeAge = new Date().getFullYear() - homeCharacteristics.yearBuilt;
    if (homeAge > 40) {
      riskAdjustment += basePremium * 0.15;
      recommendations.push('Consider updating electrical and plumbing for lower rates.');
    } else if (homeAge < 10) {
      riskAdjustment -= basePremium * 0.10;
    }

    switch (homeCharacteristics.constructionType) {
      case 'masonry':
        riskAdjustment -= basePremium * 0.10;
        break;
      case 'superior':
        riskAdjustment -= basePremium * 0.15;
        break;
      case 'manufactured':
        riskAdjustment += basePremium * 0.25;
        break;
    }

    if (homeCharacteristics.roofAge && homeCharacteristics.roofAge > 20) {
      riskAdjustment += basePremium * 0.10;
      recommendations.push('A new roof could reduce your premium.');
    }

    if (homeCharacteristics.swimmingPool) {
      riskAdjustment += basePremium * 0.10;
      recommendations.push('Installing a pool fence may reduce your premium.');
    }
    if (homeCharacteristics.trampoline) {
      riskAdjustment += basePremium * 0.05;
    }
    if (homeCharacteristics.dogBreed === 'high-risk') {
      riskAdjustment += basePremium * 0.10;
    }
  }

  if (riskFactors) {
    if (riskFactors.coastalProperty) {
      riskAdjustment += basePremium * 0.30;
      recommendations.push('Consider additional wind/hurricane coverage.');
    }
    if (riskFactors.wildFireZone) {
      riskAdjustment += basePremium * 0.25;
      recommendations.push('Create defensible space around your home for potential discounts.');
    }
    if (riskFactors.floodZone) {
      recommendations.push('Flood insurance is recommended and may be required by your lender.');
    }
    if (riskFactors.gatedCommunity) {
      riskAdjustment -= basePremium * 0.05;
    }
    if (riskFactors.crimeHigh) {
      riskAdjustment += basePremium * 0.08;
    }
    if (riskFactors.crimeLow) {
      riskAdjustment -= basePremium * 0.05;
    }
  }

  const premiumAfterRisk = Math.max(basePremium + riskAdjustment, basePremium * 0.5);
  const deductibleFactor = getDeductibleFactor(coverageOptions.deductible);
  const premiumAfterDeductible = premiumAfterRisk * deductibleFactor;
  const discountAmount = calculateDiscounts(premiumAfterDeductible, discounts);

  const finalPremium = premiumAfterDeductible - discountAmount;
  const annualPremium = Math.round(finalPremium);
  const monthlyPremium = Math.round(annualPremium / 12);

  return {
    annualPremium,
    monthlyPremium,
    method: 'advanced',
    breakdown: {
      basePremium: Math.round(basePremium),
      riskAdjustments: Math.round(riskAdjustment),
      discountAmount: Math.round(discountAmount),
      finalPremium: annualPremium,
    },
    coverageSummary: {
      dwelling: dwellingCoverage,
      personalProperty: Math.round(dwellingCoverage * 0.7),
      liability: coverageOptions.liabilityCoverage || 300000,
      deductible: coverageOptions.deductible,
    },
    recommendations: recommendations.length > 0 ? recommendations : undefined,
  };
}

/**
 * Calculate total discounts
 * @param {number} basePremium
 * @param {import('./types').Discounts} [discounts]
 * @returns {number}
 */
function calculateDiscounts(basePremium, discounts) {
  if (!discounts) return 0;

  let totalDiscount = 0;
  if (discounts.multiPolicy) totalDiscount += basePremium * 0.15;
  if (discounts.securitySystem) totalDiscount += basePremium * 0.13;
  if (discounts.fireAlarm) totalDiscount += basePremium * 0.07;
  if (discounts.sprinklerSystem) totalDiscount += basePremium * 0.10;
  if (discounts.deadbolts) totalDiscount += basePremium * 0.02;
  if (discounts.newHome) totalDiscount += basePremium * 0.10;
  if (discounts.seniorCitizen) totalDiscount += basePremium * 0.10;
  if (discounts.nonSmoker) totalDiscount += basePremium * 0.05;
  if (discounts.paidInFull) totalDiscount += basePremium * 0.05;

  if (discounts.claimsFreeDays) {
    const years = discounts.claimsFreeDays / 365;
    totalDiscount += basePremium * Math.min(years * 0.05, 0.25);
  }

  // Cap total discount at 40%
  return Math.min(totalDiscount, basePremium * 0.40);
}

/**
 * Get deductible adjustment factor
 * @param {number} deductible
 * @returns {number}
 */
function getDeductibleFactor(deductible) {
  if (deductible >= 5000) return 0.80;
  if (deductible >= 2500) return 0.85;
  if (deductible >= 2000) return 0.90;
  if (deductible >= 1000) return 0.95;
  return 1.0;
}

/**
 * Estimate insurance with minimal inputs
 * @param {Object} params
 * @param {number} params.homeValue
 * @param {string} [params.stateCode]
 * @param {number} [params.deductible=1000]
 * @returns {import('./types').InsuranceOutput}
 */
export function estimateInsuranceSimple({
  homeValue,
  stateCode = 'US',
  deductible = 1000,
}) {
  return estimateHomeownersInsurance({
    stateCode,
    homeValue,
    coverageOptions: {
      dwellingCoverage: homeValue,
      deductible,
    },
  });
}
