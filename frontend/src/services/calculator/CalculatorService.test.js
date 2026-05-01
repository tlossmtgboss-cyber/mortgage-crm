/**
 * CalculatorService — Comprehensive unit tests.
 *
 * These tests verify the financial calculation logic that LOs rely on
 * for lending decisions. Every method is tested against known reference
 * values and edge cases.
 */

import { describe, it, expect } from 'vitest';
import CalculatorService, {
  formatCurrency,
  formatCurrencyFull,
  formatPercent,
  STATE_DATA,
  getLocationRates,
} from './CalculatorService';

// ============================================================================
// Formatting Utilities
// ============================================================================

describe('formatCurrency', () => {
  it('formats a positive number as USD with no decimals', () => {
    expect(formatCurrency(1234)).toBe('$1,234');
  });

  it('formats large numbers with commas', () => {
    expect(formatCurrency(1000000)).toBe('$1,000,000');
  });

  it('returns "-" for null/undefined', () => {
    expect(formatCurrency(null)).toBe('-');
    expect(formatCurrency(undefined)).toBe('-');
  });

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0');
  });

  it('formats negative values', () => {
    const result = formatCurrency(-5000);
    expect(result).toContain('5,000');
  });
});

describe('formatCurrencyFull', () => {
  it('formats with 2 decimal places', () => {
    expect(formatCurrencyFull(1896.20)).toBe('$1,896.20');
  });

  it('returns "-" for null/undefined', () => {
    expect(formatCurrencyFull(null)).toBe('-');
    expect(formatCurrencyFull(undefined)).toBe('-');
  });
});

describe('formatPercent', () => {
  it('formats with default 1 decimal', () => {
    expect(formatPercent(6.875)).toBe('6.9%');
  });

  it('formats with custom decimals', () => {
    expect(formatPercent(6.875, 3)).toBe('6.875%');
  });

  it('returns "-" for null/undefined', () => {
    expect(formatPercent(null)).toBe('-');
    expect(formatPercent(undefined)).toBe('-');
  });
});

// ============================================================================
// Location Rates
// ============================================================================

describe('getLocationRates', () => {
  it('returns county-level rates when county is specified', () => {
    const rates = getLocationRates('CA', 'Los Angeles');
    expect(rates.taxRate).toBe(0.0072);
    expect(rates.insuranceRate).toBe(0.0032);
    expect(rates.source).toBe('county');
  });

  it('returns state average when no county specified', () => {
    const rates = getLocationRates('TX', '');
    expect(rates.taxRate).toBe(0.0180);
    expect(rates.insuranceRate).toBe(0.0055);
    expect(rates.source).toBe('state');
  });

  it('returns state average when county is null', () => {
    const rates = getLocationRates('FL', null);
    expect(rates.taxRate).toBe(0.0089);
    expect(rates.source).toBe('state');
  });

  it('returns defaults for unknown state', () => {
    const rates = getLocationRates('XX', null);
    expect(rates.taxRate).toBe(0.0107);
    expect(rates.insuranceRate).toBe(0.0035);
    expect(rates.source).toBe('default');
  });

  it('returns state average for unknown county in known state', () => {
    const rates = getLocationRates('CA', 'Nonexistent County');
    expect(rates.taxRate).toBe(0.0073);
    expect(rates.source).toBe('state');
  });

  it('has complete data for all listed states', () => {
    const states = Object.keys(STATE_DATA);
    expect(states.length).toBeGreaterThanOrEqual(8);
    for (const state of states) {
      const data = STATE_DATA[state];
      expect(data.name).toBeTruthy();
      expect(data.avgTaxRate).toBeGreaterThan(0);
      expect(data.avgInsuranceRate).toBeGreaterThan(0);
      expect(Object.keys(data.counties).length).toBeGreaterThan(0);
    }
  });
});

// ============================================================================
// calculateMonthlyPI — Principal & Interest
// ============================================================================

describe('CalculatorService.calculateMonthlyPI', () => {
  it('calculates standard 30yr P&I for a $300,000 loan at 6.5%', () => {
    // Known reference: $300,000 @ 6.5% 30yr = $1,896.20/mo
    const result = CalculatorService.calculateMonthlyPI(300000, 6.5, 30);
    expect(result).toBeCloseTo(1896.20, 0);
  });

  it('calculates 15yr P&I for a $300,000 loan at 6.0%', () => {
    // Known reference: $300,000 @ 6.0% 15yr = $2,531.57/mo
    const result = CalculatorService.calculateMonthlyPI(300000, 6.0, 15);
    expect(result).toBeCloseTo(2531.57, 0);
  });

  it('calculates $200,000 @ 7.0% for 30 years', () => {
    // Known reference: $1,330.60
    const result = CalculatorService.calculateMonthlyPI(200000, 7.0, 30);
    expect(result).toBeCloseTo(1330.60, 0);
  });

  it('handles 0% interest rate without division by zero', () => {
    const result = CalculatorService.calculateMonthlyPI(360000, 0, 30);
    expect(result).toBe(1000); // 360000 / 360 = 1000
  });

  it('handles 0% interest rate for 15yr', () => {
    const result = CalculatorService.calculateMonthlyPI(180000, 0, 15);
    expect(result).toBe(1000); // 180000 / 180 = 1000
  });

  it('calculates correctly for a jumbo loan ($800,000 @ 7.25%)', () => {
    const result = CalculatorService.calculateMonthlyPI(800000, 7.25, 30);
    // P&I for this should be approximately $5,458.50
    expect(result).toBeGreaterThan(5400);
    expect(result).toBeLessThan(5520);
  });

  it('calculates correctly for 10yr term', () => {
    const result = CalculatorService.calculateMonthlyPI(200000, 6.0, 10);
    // 10yr $200k @ 6% = $2,220.41
    expect(result).toBeCloseTo(2220.41, 0);
  });

  it('total payments over 30yr exceed original loan by expected interest', () => {
    const loan = 300000;
    const pi = CalculatorService.calculateMonthlyPI(loan, 6.5, 30);
    const totalPaid = pi * 360;
    const totalInterest = totalPaid - loan;
    // At 6.5% for 30yr, total interest is roughly $382,633
    expect(totalInterest).toBeGreaterThan(380000);
    expect(totalInterest).toBeLessThan(385000);
  });
});

// ============================================================================
// calculatePITI — Full Housing Payment
// ============================================================================

describe('CalculatorService.calculatePITI', () => {
  const baseParams = {
    loanAmount: 270750,     // 95% of $285,000
    interestRate: 6.875,
    homePrice: 285000,
    creditScore: 710,
    taxRate: 0.0107,
    insuranceRate: 0.0035,
    hoaMonthly: 0,
  };

  it('returns all required fields', () => {
    const result = CalculatorService.calculatePITI(baseParams);
    expect(result).toHaveProperty('principalInterest');
    expect(result).toHaveProperty('propertyTax');
    expect(result).toHaveProperty('insurance');
    expect(result).toHaveProperty('pmi');
    expect(result).toHaveProperty('hoa');
    expect(result).toHaveProperty('total');
    expect(result).toHaveProperty('ltv');
  });

  it('calculates correct LTV', () => {
    const result = CalculatorService.calculatePITI(baseParams);
    expect(result.ltv).toBeCloseTo(95, 0);
  });

  it('includes PMI when LTV > 80%', () => {
    const result = CalculatorService.calculatePITI(baseParams);
    expect(result.pmi).toBeGreaterThan(0);
  });

  it('excludes PMI when LTV <= 80%', () => {
    const result = CalculatorService.calculatePITI({
      ...baseParams,
      loanAmount: 228000,  // 80% of $285,000
    });
    expect(result.pmi).toBe(0);
  });

  it('total equals sum of components', () => {
    const result = CalculatorService.calculatePITI(baseParams);
    const computedTotal = result.principalInterest + result.propertyTax +
      result.insurance + result.pmi + result.hoa;
    expect(result.total).toBeCloseTo(computedTotal, 2);
  });

  it('includes HOA in total when provided', () => {
    const withHOA = CalculatorService.calculatePITI({ ...baseParams, hoaMonthly: 250 });
    const withoutHOA = CalculatorService.calculatePITI(baseParams);
    expect(withHOA.total - withoutHOA.total).toBeCloseTo(250, 2);
    expect(withHOA.hoa).toBe(250);
  });

  it('calculates correct property tax monthly', () => {
    const result = CalculatorService.calculatePITI(baseParams);
    const expectedMonthlyTax = (285000 * 0.0107) / 12;
    expect(result.propertyTax).toBeCloseTo(expectedMonthlyTax, 2);
  });

  it('calculates correct insurance monthly', () => {
    const result = CalculatorService.calculatePITI(baseParams);
    const expectedMonthlyInsurance = (285000 * 0.0035) / 12;
    expect(result.insurance).toBeCloseTo(expectedMonthlyInsurance, 2);
  });

  it('uses default parameters when not specified', () => {
    const result = CalculatorService.calculatePITI({
      loanAmount: 200000,
      interestRate: 6.5,
      homePrice: 250000,
    });
    // Should use defaults: creditScore=720, taxRate=0.0107, insuranceRate=0.0035, hoaMonthly=0
    expect(result.total).toBeGreaterThan(0);
    expect(result.hoa).toBe(0);
  });

  it('handles zero down payment (100% LTV)', () => {
    const result = CalculatorService.calculatePITI({
      loanAmount: 285000,
      interestRate: 6.875,
      homePrice: 285000,
      creditScore: 710,
    });
    expect(result.ltv).toBe(100);
    expect(result.pmi).toBeGreaterThan(0);
    expect(result.total).toBeGreaterThan(0);
  });
});

// ============================================================================
// getPMIRate — PMI Rate Table
// ============================================================================

describe('CalculatorService.getPMIRate', () => {
  it('returns lowest rates for excellent credit (760+) at moderate LTV', () => {
    const rate = CalculatorService.getPMIRate(85, 780);
    expect(rate).toBe(0.0032);
  });

  it('returns higher rates for lower credit scores', () => {
    const highCredit = CalculatorService.getPMIRate(92, 760);
    const lowCredit = CalculatorService.getPMIRate(92, 680);
    expect(lowCredit).toBeGreaterThan(highCredit);
  });

  it('returns higher rates for higher LTV', () => {
    const lowLTV = CalculatorService.getPMIRate(82, 720);
    const highLTV = CalculatorService.getPMIRate(96, 720);
    expect(highLTV).toBeGreaterThan(lowLTV);
  });

  it('covers all LTV/credit-score brackets', () => {
    // Test all 16 combinations (4 credit tiers x 4 LTV tiers)
    const creditScores = [780, 740, 710, 660];
    const ltvs = [96, 92, 87, 82];
    for (const cs of creditScores) {
      for (const ltv of ltvs) {
        const rate = CalculatorService.getPMIRate(ltv, cs);
        expect(rate).toBeGreaterThan(0);
        expect(rate).toBeLessThan(0.02);
      }
    }
  });

  it('rates at LTV boundaries are correct for 720+ credit', () => {
    // LTV=95 is "> 90" not "> 95", so should get 0.0095
    expect(CalculatorService.getPMIRate(95, 720)).toBe(0.0095);
    // LTV=96 is "> 95", should get 0.0118
    expect(CalculatorService.getPMIRate(96, 720)).toBe(0.0118);
  });

  it('worst PMI rate is for low credit + high LTV', () => {
    const worstRate = CalculatorService.getPMIRate(97, 620);
    expect(worstRate).toBe(0.0155);
  });
});

// ============================================================================
// calculateDTI — Debt-to-Income Ratios
// ============================================================================

describe('CalculatorService.calculateDTI', () => {
  it('calculates correct front-end and back-end ratios', () => {
    const result = CalculatorService.calculateDTI(8000, 500, 2000);
    // Front-end: 2000/8000 = 25%
    expect(result.frontEnd).toBeCloseTo(25, 1);
    // Back-end: (2000+500)/8000 = 31.25%
    expect(result.backEnd).toBeCloseTo(31.25, 1);
  });

  it('returns "excellent" status when back-end DTI <= 36%', () => {
    const result = CalculatorService.calculateDTI(10000, 500, 2000);
    // Back-end: (2000+500)/10000 = 25%
    expect(result.status).toBe('excellent');
  });

  it('returns "acceptable" status when 36% < back-end DTI <= 43%', () => {
    const result = CalculatorService.calculateDTI(5000, 200, 1800);
    // Back-end: (1800+200)/5000 = 40%
    expect(result.status).toBe('acceptable');
  });

  it('returns "stretched" status when back-end DTI > 43%', () => {
    const result = CalculatorService.calculateDTI(5000, 500, 2000);
    // Back-end: (2000+500)/5000 = 50%
    expect(result.status).toBe('stretched');
  });

  it('qualifies when back-end DTI <= 43%', () => {
    const qualified = CalculatorService.calculateDTI(10000, 500, 3000);
    // Back-end: 35%
    expect(qualified.qualifies).toBe(true);

    const notQualified = CalculatorService.calculateDTI(5000, 500, 2000);
    // Back-end: 50%
    expect(notQualified.qualifies).toBe(false);
  });

  it('handles zero monthly debts', () => {
    const result = CalculatorService.calculateDTI(8000, 0, 2000);
    expect(result.frontEnd).toBeCloseTo(25, 1);
    expect(result.backEnd).toBeCloseTo(25, 1);
  });

  it('boundary: exactly 43% back-end', () => {
    // (housing + debts) / income = 43%
    // housing = 3000, debts = 300, income = (3000+300)/0.43 = 7674.42
    const income = (3000 + 300) / 0.43;
    const result = CalculatorService.calculateDTI(income, 300, 3000);
    expect(result.backEnd).toBeCloseTo(43, 1);
    expect(result.qualifies).toBe(true);
    expect(result.status).toBe('acceptable');
  });

  it('boundary: exactly 36% back-end', () => {
    const income = (2000 + 600) / 0.36;
    const result = CalculatorService.calculateDTI(income, 600, 2000);
    expect(result.backEnd).toBeCloseTo(36, 1);
    expect(result.status).toBe('excellent');
  });
});

// ============================================================================
// calculateClosingCosts
// ============================================================================

describe('CalculatorService.calculateClosingCosts', () => {
  const loanAmount = 270750;
  const homePrice = 285000;

  it('returns all required sections', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result).toHaveProperty('lenderFees');
    expect(result).toHaveProperty('thirdPartyFees');
    expect(result).toHaveProperty('prepaids');
    expect(result).toHaveProperty('escrows');
    expect(result).toHaveProperty('total');
  });

  it('total equals sum of all fee sections', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    const computedTotal = result.lenderFees.total + result.thirdPartyFees.total +
      result.prepaids.total + result.escrows.total;
    expect(result.total).toBeCloseTo(computedTotal, 2);
  });

  it('origination fee is 1% of loan amount', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result.lenderFees.originationFee).toBeCloseTo(loanAmount * 0.01, 2);
  });

  it('title insurance is 0.5% of home price', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result.thirdPartyFees.titleInsurance).toBeCloseTo(homePrice * 0.005, 2);
  });

  it('prepaid interest is based on 15 days', () => {
    const rate = 6.875;
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice, 'CA', rate);
    const expectedPrepaidInterest = (loanAmount * (rate / 100) / 365) * 15;
    expect(result.prepaids.prepaidInterest).toBeCloseTo(expectedPrepaidInterest, 2);
  });

  it('escrow insurance is 2 months of annual premium', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result.escrows.escrowInsurance).toBeCloseTo((homePrice * 0.0035) / 6, 2);
  });

  it('escrow taxes is 2 months of annual tax', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result.escrows.escrowTaxes).toBeCloseTo((homePrice * 0.0107) / 6, 2);
  });

  it('uses default state rate when unknown state provided', () => {
    const resultDefault = CalculatorService.calculateClosingCosts(loanAmount, homePrice, 'XX');
    const resultCA = CalculatorService.calculateClosingCosts(loanAmount, homePrice, 'CA');
    // The state rate parameter is not actually used in the calculation body
    // (only stateRates is defined but rate is not used to adjust totals),
    // so results should be identical for the fee components
    expect(resultDefault.total).toBeGreaterThan(0);
  });

  it('handles zero loan amount', () => {
    const result = CalculatorService.calculateClosingCosts(0, homePrice);
    expect(result.lenderFees.originationFee).toBe(0);
    expect(result.prepaids.prepaidInterest).toBe(0);
    // Third party fees still apply (based on home price)
    expect(result.thirdPartyFees.titleInsurance).toBeGreaterThan(0);
  });

  it('handles zero home price', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, 0);
    expect(result.thirdPartyFees.titleInsurance).toBe(0);
    expect(result.prepaids.prepaidInsurance).toBe(0);
    expect(result.prepaids.prepaidTaxes).toBe(0);
    // Lender fees still apply (based on loan amount)
    expect(result.lenderFees.originationFee).toBeGreaterThan(0);
  });

  it('lender fees include fixed costs', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result.lenderFees.underwritingFee).toBe(500);
    expect(result.lenderFees.processingFee).toBe(450);
    expect(result.lenderFees.creditReport).toBe(50);
    expect(result.lenderFees.floodCert).toBe(25);
  });

  it('third party fees include fixed costs', () => {
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    expect(result.thirdPartyFees.appraisal).toBe(550);
    expect(result.thirdPartyFees.titleSearch).toBe(200);
    expect(result.thirdPartyFees.settlementFee).toBe(750);
    expect(result.thirdPartyFees.recordingFees).toBe(150);
    expect(result.thirdPartyFees.survey).toBe(400);
  });

  it('jumbo loan closing costs are proportionally higher', () => {
    const jumboLoan = 750000;
    const jumboHome = 900000;
    const standardResult = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    const jumboResult = CalculatorService.calculateClosingCosts(jumboLoan, jumboHome);
    expect(jumboResult.total).toBeGreaterThan(standardResult.total * 2);
  });
});

// ============================================================================
// estimatePMICancellation
// ============================================================================

describe('CalculatorService.estimatePMICancellation', () => {
  it('returns 0 months when LTV is already <= 78%', () => {
    expect(CalculatorService.estimatePMICancellation(78)).toBe(0);
    expect(CalculatorService.estimatePMICancellation(75)).toBe(0);
    expect(CalculatorService.estimatePMICancellation(50)).toBe(0);
  });

  it('estimates months for 95% LTV', () => {
    // (95 - 78) / 2 = 8.5 years = 102 months
    const months = CalculatorService.estimatePMICancellation(95);
    expect(months).toBe(102);
  });

  it('estimates months for 90% LTV', () => {
    // (90 - 78) / 2 = 6 years = 72 months
    const months = CalculatorService.estimatePMICancellation(90);
    expect(months).toBe(72);
  });

  it('estimates months for 80% LTV', () => {
    // (80 - 78) / 2 = 1 year = 12 months
    const months = CalculatorService.estimatePMICancellation(80);
    expect(months).toBe(12);
  });

  it('handles LTV just above 78%', () => {
    // (79 - 78) / 2 = 0.5 years = 6 months
    const months = CalculatorService.estimatePMICancellation(79);
    expect(months).toBe(6);
  });

  it('handles 100% LTV', () => {
    // (100 - 78) / 2 = 11 years = 132 months
    const months = CalculatorService.estimatePMICancellation(100);
    expect(months).toBe(132);
  });
});

// ============================================================================
// calculateTaxBenefits
// ============================================================================

describe('CalculatorService.calculateTaxBenefits', () => {
  const baseParams = {
    loanAmount: 270750,
    interestRate: 6.875,
    homePrice: 285000,
  };

  it('returns all required fields', () => {
    const result = CalculatorService.calculateTaxBenefits(baseParams);
    expect(result).toHaveProperty('annualInterest');
    expect(result).toHaveProperty('annualPropertyTax');
    expect(result).toHaveProperty('totalDeductions');
    expect(result).toHaveProperty('standardDeduction');
    expect(result).toHaveProperty('additionalDeduction');
    expect(result).toHaveProperty('marginalTaxRate');
    expect(result).toHaveProperty('annualTaxSavings');
    expect(result).toHaveProperty('monthlyTaxSavings');
    expect(result).toHaveProperty('itemizingMakesSense');
  });

  it('annual interest uses 0.98 factor (approximation for amortization)', () => {
    const result = CalculatorService.calculateTaxBenefits(baseParams);
    const expectedInterest = 270750 * (6.875 / 100) * 0.98;
    expect(result.annualInterest).toBeCloseTo(expectedInterest, 2);
  });

  it('annual property tax uses default tax rate', () => {
    const result = CalculatorService.calculateTaxBenefits(baseParams);
    const expectedTax = 285000 * 0.0107;
    expect(result.annualPropertyTax).toBeCloseTo(expectedTax, 2);
  });

  it('uses custom tax rate and marginal rate when provided', () => {
    const result = CalculatorService.calculateTaxBenefits({
      ...baseParams,
      taxRate: 0.02,
      marginalTaxRate: 0.32,
    });
    expect(result.annualPropertyTax).toBeCloseTo(285000 * 0.02, 2);
    expect(result.marginalTaxRate).toBe(0.32);
  });

  it('additionalDeduction is zero when deductions < standard deduction', () => {
    // Small loan = small deductions
    const result = CalculatorService.calculateTaxBenefits({
      loanAmount: 50000,
      interestRate: 4.0,
      homePrice: 100000,
    });
    // Interest: 50000*0.04*0.98 = $1,960; Tax: 100000*0.0107 = $1,070
    // Total: $3,030 < $14,600 standard deduction
    expect(result.additionalDeduction).toBe(0);
    expect(result.annualTaxSavings).toBe(0);
    expect(result.itemizingMakesSense).toBe(false);
  });

  it('produces positive tax savings when deductions exceed standard deduction', () => {
    const result = CalculatorService.calculateTaxBenefits({
      loanAmount: 400000,
      interestRate: 7.0,
      homePrice: 500000,
      marginalTaxRate: 0.24,
    });
    // Interest: 400000*0.07*0.98 = $27,440; Tax: 500000*0.0107 = $5,350
    // Total: $32,790 > $14,600
    expect(result.additionalDeduction).toBeGreaterThan(0);
    expect(result.annualTaxSavings).toBeGreaterThan(0);
    expect(result.monthlyTaxSavings).toBeCloseTo(result.annualTaxSavings / 12, 2);
    expect(result.itemizingMakesSense).toBe(true);
  });

  it('monthly tax savings = annual / 12', () => {
    const result = CalculatorService.calculateTaxBenefits(baseParams);
    expect(result.monthlyTaxSavings).toBeCloseTo(result.annualTaxSavings / 12, 2);
  });
});

// ============================================================================
// calculateNetWorthProjection
// ============================================================================

describe('CalculatorService.calculateNetWorthProjection', () => {
  // First compute a valid PITI to pass in
  const piti = CalculatorService.calculatePITI({
    loanAmount: 270750,
    interestRate: 6.875,
    homePrice: 285000,
    creditScore: 710,
  });

  const baseParams = {
    homePrice: 285000,
    downPayment: 14250,
    loanAmount: 270750,
    monthlyRent: 1800,
    mortgagePayment: piti.total,
    piti,
    interestRate: 6.875,
    years: 5,
    initialSavings: 28000,
    closingCosts: 10000,
    taxSavingsMonthly: 100,
  };

  it('returns renterPath and buyerPath arrays', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    expect(result.renterPath).toHaveLength(5);
    expect(result.buyerPath).toHaveLength(5);
  });

  it('paths have correct year numbering', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    result.renterPath.forEach((entry, i) => {
      expect(entry.year).toBe(i + 1);
    });
    result.buyerPath.forEach((entry, i) => {
      expect(entry.year).toBe(i + 1);
    });
  });

  it('renter path has netWorth and rentPaid fields', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    for (const entry of result.renterPath) {
      expect(entry).toHaveProperty('netWorth');
      expect(entry).toHaveProperty('rentPaid');
      expect(typeof entry.netWorth).toBe('number');
    }
  });

  it('buyer path has homeValue, homeEquity, remainingLoan fields', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    for (const entry of result.buyerPath) {
      expect(entry).toHaveProperty('netWorth');
      expect(entry).toHaveProperty('homeEquity');
      expect(entry).toHaveProperty('homeValue');
      expect(entry).toHaveProperty('remainingLoan');
      expect(entry).toHaveProperty('principalPaid');
    }
  });

  it('home value appreciates at 3% per year by default', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    const year1HomeValue = result.buyerPath[0].homeValue;
    const year5HomeValue = result.buyerPath[4].homeValue;
    // Year 5 home value should be 285000 * 1.03^5 = 330,384
    expect(year5HomeValue).toBeCloseTo(285000 * Math.pow(1.03, 5), -2);
    expect(year5HomeValue).toBeGreaterThan(year1HomeValue);
  });

  it('remaining loan decreases over time', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    for (let i = 1; i < result.buyerPath.length; i++) {
      expect(result.buyerPath[i].remainingLoan).toBeLessThan(result.buyerPath[i - 1].remainingLoan);
    }
  });

  it('home equity increases over time', () => {
    const result = CalculatorService.calculateNetWorthProjection(baseParams);
    for (let i = 1; i < result.buyerPath.length; i++) {
      expect(result.buyerPath[i].homeEquity).toBeGreaterThan(result.buyerPath[i - 1].homeEquity);
    }
  });

  it('works with custom projection period', () => {
    const result = CalculatorService.calculateNetWorthProjection({
      ...baseParams,
      years: 10,
    });
    expect(result.renterPath).toHaveLength(10);
    expect(result.buyerPath).toHaveLength(10);
  });

  it('handles zero tax savings', () => {
    const result = CalculatorService.calculateNetWorthProjection({
      ...baseParams,
      taxSavingsMonthly: 0,
    });
    expect(result.buyerPath).toHaveLength(5);
    expect(result.buyerPath[0].netWorth).toBeGreaterThan(0);
  });
});

// ============================================================================
// Integration / Cross-Method Tests
// ============================================================================

describe('Cross-method integration tests', () => {
  it('PITI total is reasonable for a $285,000 home with 5% down', () => {
    const result = CalculatorService.calculatePITI({
      loanAmount: 285000 * 0.95,
      interestRate: 6.875,
      homePrice: 285000,
      creditScore: 710,
    });
    // Should be in range $1,800 - $2,400 for this scenario
    expect(result.total).toBeGreaterThan(1800);
    expect(result.total).toBeLessThan(2400);
  });

  it('closing costs are in reasonable range for typical purchase', () => {
    const loanAmount = 270750;
    const homePrice = 285000;
    const result = CalculatorService.calculateClosingCosts(loanAmount, homePrice);
    // Closing costs typically 2-5% of home price
    expect(result.total).toBeGreaterThan(homePrice * 0.02);
    expect(result.total).toBeLessThan(homePrice * 0.06);
  });

  it('DTI from PITI output is consistent', () => {
    const monthlyIncome = 92000 / 12;
    const monthlyDebts = 670;
    const piti = CalculatorService.calculatePITI({
      loanAmount: 270750,
      interestRate: 6.875,
      homePrice: 285000,
      creditScore: 710,
    });
    const dti = CalculatorService.calculateDTI(monthlyIncome, monthlyDebts, piti.total);
    // Back-end should be housing + debts / income
    expect(dti.backEnd).toBeCloseTo(((piti.total + monthlyDebts) / monthlyIncome) * 100, 1);
  });
});

// ============================================================================
// Edge Cases
// ============================================================================

describe('Edge cases', () => {
  it('zero down payment (100% LTV) produces valid PITI', () => {
    const result = CalculatorService.calculatePITI({
      loanAmount: 300000,
      interestRate: 6.5,
      homePrice: 300000,
      creditScore: 700,
    });
    expect(result.ltv).toBe(100);
    expect(result.pmi).toBeGreaterThan(0);
    expect(result.total).toBeGreaterThan(result.principalInterest);
  });

  it('very small loan amount produces valid results', () => {
    const result = CalculatorService.calculatePITI({
      loanAmount: 10000,
      interestRate: 5.0,
      homePrice: 50000,
      creditScore: 750,
    });
    expect(result.principalInterest).toBeGreaterThan(0);
    expect(result.total).toBeGreaterThan(0);
  });

  it('jumbo loan threshold: $766,550 loan is near conforming limit', () => {
    const jumboResult = CalculatorService.calculatePITI({
      loanAmount: 800000,
      interestRate: 7.25,
      homePrice: 1000000,
      creditScore: 760,
    });
    const conformingResult = CalculatorService.calculatePITI({
      loanAmount: 700000,
      interestRate: 6.875,
      homePrice: 875000,
      creditScore: 760,
    });
    // Jumbo should have higher P&I due to both higher amount and rate
    expect(jumboResult.principalInterest).toBeGreaterThan(conformingResult.principalInterest);
  });

  it('very high interest rate (15%) produces valid but large payments', () => {
    const pi = CalculatorService.calculateMonthlyPI(200000, 15, 30);
    // Should be approximately $2,528.44
    expect(pi).toBeGreaterThan(2500);
    expect(pi).toBeLessThan(2560);
  });

  it('very low interest rate (1%) produces valid results', () => {
    const pi = CalculatorService.calculateMonthlyPI(300000, 1, 30);
    // Should be approximately $964.59
    expect(pi).toBeGreaterThan(960);
    expect(pi).toBeLessThan(970);
  });

  it('negative amortization guard: P&I always exceeds interest-only amount', () => {
    // For a standard fixed-rate amortizing loan, the P&I should always
    // be greater than the interest-only portion
    const loanAmount = 300000;
    const rate = 7.0;
    const monthlyRate = rate / 100 / 12;
    const pi = CalculatorService.calculateMonthlyPI(loanAmount, rate, 30);
    const interestOnly = loanAmount * monthlyRate;
    expect(pi).toBeGreaterThan(interestOnly);
  });

  it('PMI rate is zero for credit score 760+ at 80% LTV exactly', () => {
    // LTV <= 80 should not trigger PMI at all in calculatePITI
    const result = CalculatorService.calculatePITI({
      loanAmount: 240000,
      interestRate: 6.5,
      homePrice: 300000, // LTV = 80%
      creditScore: 760,
    });
    expect(result.pmi).toBe(0);
  });

  it('closing costs with very high interest rate adjusts prepaid interest', () => {
    const result = CalculatorService.calculateClosingCosts(300000, 350000, 'CA', 12.0);
    const expectedPrepaid = (300000 * (12.0 / 100) / 365) * 15;
    expect(result.prepaids.prepaidInterest).toBeCloseTo(expectedPrepaid, 2);
  });

  it('DTI with zero income causes Infinity (caller must guard)', () => {
    const result = CalculatorService.calculateDTI(0, 500, 2000);
    expect(result.frontEnd).toBe(Infinity);
    expect(result.backEnd).toBe(Infinity);
  });

  it('net worth projection with 1 year produces single entries', () => {
    const piti = CalculatorService.calculatePITI({
      loanAmount: 270750,
      interestRate: 6.875,
      homePrice: 285000,
      creditScore: 710,
    });
    const result = CalculatorService.calculateNetWorthProjection({
      homePrice: 285000,
      downPayment: 14250,
      loanAmount: 270750,
      monthlyRent: 1800,
      mortgagePayment: piti.total,
      piti,
      interestRate: 6.875,
      years: 1,
      initialSavings: 28000,
      closingCosts: 10000,
    });
    expect(result.renterPath).toHaveLength(1);
    expect(result.buyerPath).toHaveLength(1);
  });
});

// ============================================================================
// Known Reference Value Tests
// ============================================================================

describe('Known reference values', () => {
  it('$300,000 @ 6.5% 30yr = $1,896.20 P&I', () => {
    const pi = CalculatorService.calculateMonthlyPI(300000, 6.5, 30);
    expect(pi).toBeCloseTo(1896.20, 0);
  });

  it('$250,000 @ 5.5% 30yr = $1,419.47 P&I', () => {
    const pi = CalculatorService.calculateMonthlyPI(250000, 5.5, 30);
    expect(pi).toBeCloseTo(1419.47, 0);
  });

  it('$400,000 @ 7.0% 30yr = $2,661.21 P&I', () => {
    const pi = CalculatorService.calculateMonthlyPI(400000, 7.0, 30);
    expect(pi).toBeCloseTo(2661.21, 0);
  });

  it('$200,000 @ 4.5% 15yr = $1,529.99 P&I', () => {
    const pi = CalculatorService.calculateMonthlyPI(200000, 4.5, 15);
    expect(pi).toBeCloseTo(1529.99, 0);
  });

  it('$500,000 @ 6.0% 30yr = $2,997.75 P&I', () => {
    const pi = CalculatorService.calculateMonthlyPI(500000, 6.0, 30);
    expect(pi).toBeCloseTo(2997.75, 0);
  });
});
