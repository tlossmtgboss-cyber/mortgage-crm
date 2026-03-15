/**
 * Calculator Dashboard
 *
 * Single-page calculator dashboard with:
 * - Sidebar list of all calculators
 * - Click to view details and visuals
 * - Pre-populated with borrower scenario data
 */

import React, { useState, useMemo } from 'react';
import './CalculatorDashboard.css';

// ============================================================================
// UTILITIES
// ============================================================================

const formatCurrency = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatCurrencyFull = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
};

const formatPercent = (value, decimals = 1) => {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(decimals)}%`;
};

// ============================================================================
// CALCULATOR SERVICE (Frontend calculations)
// ============================================================================

class CalculatorService {
  static calculateMonthlyPI(loanAmount, interestRate, termYears = 30) {
    const monthlyRate = (interestRate / 100) / 12;
    const numPayments = termYears * 12;

    if (monthlyRate === 0) {
      return loanAmount / numPayments;
    }

    return (
      (loanAmount * monthlyRate * Math.pow(1 + monthlyRate, numPayments)) /
      (Math.pow(1 + monthlyRate, numPayments) - 1)
    );
  }

  static calculatePITI(params) {
    const {
      loanAmount,
      interestRate,
      termYears = 30,
      homePrice,
      creditScore = 720,
      taxRate = 0.0107,
      insuranceRate = 0.0035,
      hoaMonthly = 0,
    } = params;

    const pi = this.calculateMonthlyPI(loanAmount, interestRate, termYears);
    const monthlyTax = (homePrice * taxRate) / 12;
    const monthlyInsurance = (homePrice * insuranceRate) / 12;

    // PMI calculation (simplified)
    const ltv = (loanAmount / homePrice) * 100;
    let monthlyPMI = 0;
    if (ltv > 80) {
      const pmiRate = this.getPMIRate(ltv, creditScore);
      monthlyPMI = (loanAmount * pmiRate) / 12;
    }

    return {
      principalInterest: pi,
      propertyTax: monthlyTax,
      insurance: monthlyInsurance,
      pmi: monthlyPMI,
      hoa: hoaMonthly,
      total: pi + monthlyTax + monthlyInsurance + monthlyPMI + hoaMonthly,
      ltv,
    };
  }

  static getPMIRate(ltv, creditScore) {
    // Simplified PMI rate table
    if (creditScore >= 760) {
      if (ltv > 95) return 0.0098;
      if (ltv > 90) return 0.0078;
      if (ltv > 85) return 0.0052;
      return 0.0032;
    } else if (creditScore >= 720) {
      if (ltv > 95) return 0.0118;
      if (ltv > 90) return 0.0095;
      if (ltv > 85) return 0.0065;
      return 0.0044;
    } else if (creditScore >= 700) {
      if (ltv > 95) return 0.0135;
      if (ltv > 90) return 0.0108;
      if (ltv > 85) return 0.0078;
      return 0.0052;
    } else {
      if (ltv > 95) return 0.0155;
      if (ltv > 90) return 0.0125;
      if (ltv > 85) return 0.0095;
      return 0.0065;
    }
  }

  static calculateDTI(monthlyIncome, monthlyDebts, housingPayment) {
    const frontEnd = (housingPayment / monthlyIncome) * 100;
    const backEnd = ((housingPayment + monthlyDebts) / monthlyIncome) * 100;

    return {
      frontEnd,
      backEnd,
      qualifies: backEnd <= 43,
      status: backEnd <= 36 ? 'excellent' : backEnd <= 43 ? 'acceptable' : 'stretched',
    };
  }

  static calculateClosingCosts(loanAmount, homePrice, state = 'CA', interestRate = 6.875) {
    const stateRates = {
      CA: 0.025, NY: 0.04, TX: 0.032, FL: 0.03, default: 0.03,
    };
    const rate = stateRates[state] || stateRates.default;

    // Lender fees breakdown
    const originationFee = loanAmount * 0.01;
    const underwritingFee = 500;
    const processingFee = 450;
    const creditReport = 50;
    const floodCert = 25;
    const lenderFees = originationFee + underwritingFee + processingFee + creditReport + floodCert;

    // Third party fees breakdown
    const appraisal = 550;
    const titleSearch = 200;
    const titleInsurance = homePrice * 0.005;
    const settlementFee = 750;
    const recordingFees = 150;
    const survey = 400;
    const thirdPartyFees = appraisal + titleSearch + titleInsurance + settlementFee + recordingFees + survey;

    // Prepaids breakdown
    const prepaidInterest = (loanAmount * (interestRate / 100) / 365) * 15; // 15 days
    const prepaidInsurance = homePrice * 0.0035; // 1 year
    const prepaidTaxes = (homePrice * 0.0107) / 4; // 3 months
    const prepaids = prepaidInterest + prepaidInsurance + prepaidTaxes;

    // Escrow reserves breakdown
    const escrowInsurance = (homePrice * 0.0035) / 6; // 2 months
    const escrowTaxes = (homePrice * 0.0107) / 6; // 2 months
    const escrows = escrowInsurance + escrowTaxes;

    return {
      lenderFees: {
        total: lenderFees,
        originationFee,
        underwritingFee,
        processingFee,
        creditReport,
        floodCert,
      },
      thirdPartyFees: {
        total: thirdPartyFees,
        appraisal,
        titleSearch,
        titleInsurance,
        settlementFee,
        recordingFees,
        survey,
      },
      prepaids: {
        total: prepaids,
        prepaidInterest,
        prepaidInsurance,
        prepaidTaxes,
      },
      escrows: {
        total: escrows,
        escrowInsurance,
        escrowTaxes,
      },
      total: lenderFees + thirdPartyFees + prepaids + escrows,
    };
  }

  static estimatePMICancellation(ltv, interestRate = 6.875) {
    if (ltv <= 78) return 0;
    // Simplified estimate
    const targetLTV = 78;
    const yearlyEquityGain = 2; // ~2% equity per year from payments
    const yearsToCancel = (ltv - targetLTV) / yearlyEquityGain;
    return Math.round(yearsToCancel * 12);
  }

  static calculateTaxBenefits(params) {
    const {
      loanAmount,
      interestRate,
      homePrice,
      taxRate = 0.0107,
      marginalTaxRate = 0.22, // Alex is likely in 22% bracket at $92k income
      standardDeduction = 14600, // 2024 single filer
    } = params;

    // First year mortgage interest (approximate - slightly less than loan * rate due to amortization)
    const annualInterest = loanAmount * (interestRate / 100) * 0.98;
    const annualPropertyTax = homePrice * taxRate;

    // Total itemized deductions from homeownership
    const totalDeductions = annualInterest + annualPropertyTax;

    // Only benefit if itemized > standard deduction
    const additionalDeduction = Math.max(0, totalDeductions - standardDeduction);
    const annualTaxSavings = additionalDeduction * marginalTaxRate;
    const monthlyTaxSavings = annualTaxSavings / 12;

    return {
      annualInterest,
      annualPropertyTax,
      totalDeductions,
      standardDeduction,
      additionalDeduction,
      marginalTaxRate,
      annualTaxSavings,
      monthlyTaxSavings,
      itemizingMakesSense: totalDeductions > standardDeduction,
    };
  }

  static calculateNetWorthProjection(params) {
    const {
      homePrice,
      downPayment,
      loanAmount,
      monthlyRent,
      mortgagePayment,
      piti,
      interestRate,
      appreciationRate = 0.03, // 3% annual appreciation
      rentIncreaseRate = 0.03, // 3% annual rent increase
      investmentReturn = 0.07, // 7% stock market return
      years = 5,
      initialSavings,
      closingCosts,
      taxSavingsMonthly = 0,
    } = params;

    const renterPath = [];
    const buyerPath = [];

    // Renter starts with full savings, invests the difference
    let renterNetWorth = initialSavings;
    let currentRent = monthlyRent;

    // Buyer puts down payment + closing costs
    let buyerNetWorth = initialSavings - downPayment - closingCosts;
    let homeValue = homePrice;
    let remainingLoan = loanAmount;
    const monthlyRate = (interestRate / 100) / 12;

    for (let year = 1; year <= years; year++) {
      // Renter: invests difference between mortgage and rent + tax savings
      let yearlyRentPaid = 0;
      for (let month = 0; month < 12; month++) {
        yearlyRentPaid += currentRent;
        // Monthly savings invested = mortgage - rent (if positive, renter saves; if negative, buyer saves)
        const monthlySavings = mortgagePayment - currentRent;
        if (monthlySavings > 0) {
          // Renter pays less, invests the difference
          renterNetWorth += monthlySavings;
        }
      }
      // Apply investment returns to renter's portfolio
      renterNetWorth *= (1 + investmentReturn);
      // Rent increases for next year
      currentRent *= (1 + rentIncreaseRate);

      // Buyer: home appreciates, principal paid down
      homeValue *= (1 + appreciationRate);

      // Calculate principal paid in this year (simplified)
      let principalPaidThisYear = 0;
      for (let month = 0; month < 12; month++) {
        const interestPayment = remainingLoan * monthlyRate;
        const principalPayment = piti.principalInterest - interestPayment;
        principalPaidThisYear += principalPayment;
        remainingLoan -= principalPayment;
      }

      // Add tax savings to buyer's cash
      buyerNetWorth += (taxSavingsMonthly * 12);

      // Buyer's net worth = home equity + remaining cash
      const homeEquity = homeValue - remainingLoan;

      // If mortgage is higher than rent, buyer has less to invest
      const monthlyExtraCost = mortgagePayment - monthlyRent * Math.pow(1 + rentIncreaseRate, year - 1);
      if (monthlyExtraCost < 0) {
        buyerNetWorth += Math.abs(monthlyExtraCost) * 12;
      }

      // Buyer's remaining cash grows with investment returns (what they don't spend on housing)
      buyerNetWorth *= (1 + investmentReturn * 0.5); // More conservative for emergency fund

      renterPath.push({
        year,
        netWorth: Math.round(renterNetWorth),
        rentPaid: Math.round(yearlyRentPaid),
      });

      buyerPath.push({
        year,
        netWorth: Math.round(homeEquity + Math.max(0, buyerNetWorth)),
        homeEquity: Math.round(homeEquity),
        homeValue: Math.round(homeValue),
        remainingLoan: Math.round(remainingLoan),
        principalPaid: Math.round(principalPaidThisYear),
      });
    }

    return { renterPath, buyerPath };
  }
}

// ============================================================================
// STATE/COUNTY TAX AND INSURANCE RATES
// ============================================================================

const STATE_DATA = {
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
const getLocationRates = (state, county) => {
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

const CALCULATOR_PHASES = [
  {
    id: 'phase-1',
    name: 'Can I Buy?',
    subtitle: 'Affordability & Qualification',
    icon: '🏠',
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
    icon: '💰',
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
    icon: '📈',
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
const getCalculatorPhase = (calcId) => {
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

const DEFAULT_PROFILE = {
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

const DEFAULT_MARKET = {
  interestRate: 6.875,
  termYears: 30,
  points: 0,
  pointsDiscount: 0.25, // Each point reduces rate by 0.25%
  taxRate: 0.0107,
  insuranceRate: 0.0035,
};

const DEFAULT_PROPERTY = {
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
const ALEX_PROFILE = DEFAULT_PROFILE;
const MARKET_ASSUMPTIONS = DEFAULT_MARKET;

// ============================================================================
// CALCULATOR DEFINITIONS
// ============================================================================

const buildCalculators = (profile, market, propertyData = DEFAULT_PROPERTY) => {
  // Calculate data for each calculator
  const monthlyIncome = profile.monthlyIncome;

  // Comfort Zone calculations
  const conservativePayment = monthlyIncome * 0.25;
  const moderatePayment = monthlyIncome * 0.28;

  // Home prices from property data
  const homePrices = {
    conservative: propertyData.homePrices?.conservative || 221000,
    moderate: propertyData.homePrices?.moderate || 248000,
    baseline: propertyData.homePrice || propertyData.homePrices?.baseline || 285000,
  };

  // Down payment scenarios
  const downPaymentScenarios = [
    { pct: 0.03, label: '3% Down' },
    { pct: 0.05, label: '5% Down' },
    { pct: 0.10, label: '10% Down' },
  ].map((scenario) => {
    const downPayment = homePrices.baseline * scenario.pct;
    const loanAmount = homePrices.baseline - downPayment;
    const piti = CalculatorService.calculatePITI({
      loanAmount,
      interestRate: market.interestRate,
      homePrice: homePrices.baseline,
      creditScore: profile.creditScore,
    });
    const closing = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline);

    return {
      ...scenario,
      downPayment,
      loanAmount,
      piti,
      closingCosts: closing.total,
      cashRemaining: profile.savings - downPayment - closing.total,
      ltv: (loanAmount / homePrices.baseline) * 100,
      pmiMonths: CalculatorService.estimatePMICancellation((loanAmount / homePrices.baseline) * 100),
    };
  });

  // DTI for baseline scenario
  const baselinePiti = CalculatorService.calculatePITI({
    loanAmount: homePrices.baseline * 0.95,
    interestRate: market.interestRate,
    homePrice: homePrices.baseline,
    creditScore: profile.creditScore,
  });
  const dti = CalculatorService.calculateDTI(
    monthlyIncome,
    profile.monthlyDebts,
    baselinePiti.total
  );

  // Rent vs Buy calculations
  const fiveYearRent = Array.from({ length: 5 }, (_, i) =>
    profile.currentRent * 12 * Math.pow(1.03, i)
  ).reduce((a, b) => a + b, 0);
  const fiveYearEquity = homePrices.baseline * Math.pow(1.03, 5) - homePrices.baseline * 0.95 * 0.92;

  // Max affordability at 43% DTI
  const maxHousingPayment = monthlyIncome * 0.43 - profile.monthlyDebts;

  return [
    {
      id: 'down-payment',
      name: 'Down Payment Options',
      color: '#3b82f6',
      shortDescription: 'Compare 3%, 5%, and 10% down',
      data: {
        homePrice: homePrices.baseline,
        scenarios: downPaymentScenarios,
        savings: profile.savings,
      },
    },
    {
      id: 'monthly-payment',
      name: 'Monthly Payment (PITI)',
      color: '#8b5cf6',
      shortDescription: 'Compare payments by down payment',
      data: {
        homePrice: homePrices.baseline,
        scenarios: downPaymentScenarios,
        rate: market.interestRate,
        term: market.termYears,
      },
    },
    {
      id: 'dti',
      name: 'Debt-to-Income (DTI)',
      color: '#f59e0b',
      shortDescription: 'Your total debt burden',
      data: {
        monthlyIncome,
        housingPayment: baselinePiti.total,
        otherDebts: profile.monthlyDebts,
        dti,
        remaining: monthlyIncome - baselinePiti.total - profile.monthlyDebts,
      },
    },
    {
      id: 'rent-vs-buy',
      name: 'Rent vs. Buy',
      color: '#ec4899',
      shortDescription: 'True cost comparison with tax benefits',
      data: (() => {
        const loanAmount = homePrices.baseline * 0.95;
        const downPayment = homePrices.baseline * 0.05;
        const closingCosts = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;

        // Tax benefits calculation
        const taxBenefits = CalculatorService.calculateTaxBenefits({
          loanAmount,
          interestRate: market.interestRate,
          homePrice: homePrices.baseline,
        });

        // True cost after tax benefits
        const effectiveMonthlyPayment = baselinePiti.total - taxBenefits.monthlyTaxSavings;

        // Net worth projection
        const netWorthProjection = CalculatorService.calculateNetWorthProjection({
          homePrice: homePrices.baseline,
          downPayment,
          loanAmount,
          monthlyRent: profile.currentRent,
          mortgagePayment: baselinePiti.total,
          piti: baselinePiti,
          interestRate: market.interestRate,
          years: 5,
          initialSavings: profile.savings,
          closingCosts,
          taxSavingsMonthly: taxBenefits.monthlyTaxSavings,
        });

        // Calculate true monthly cost (excluding principal which is savings)
        const monthlyInterest = loanAmount * (market.interestRate / 100) / 12;
        const trueMonthlyCost = monthlyInterest + baselinePiti.propertyTax + baselinePiti.insurance + baselinePiti.pmi - taxBenefits.monthlyTaxSavings;

        return {
          currentRent: profile.currentRent,
          mortgagePayment: baselinePiti.total,
          monthlyDifference: baselinePiti.total - profile.currentRent,
          fiveYearRent,
          fiveYearEquity,
          firstYearEquity: baselinePiti.principalInterest * 12 * 0.18,
          breakEvenYears: 2.1,
          // New data
          taxBenefits,
          effectiveMonthlyPayment,
          trueMonthlyCost,
          principalBuildup: baselinePiti.principalInterest - monthlyInterest,
          netWorthProjection,
          homePrice: homePrices.baseline,
          downPayment,
          loanAmount,
        };
      })(),
    },
    {
      id: 'cash-reserves',
      name: 'Cash Reserves',
      color: '#06b6d4',
      shortDescription: 'Your tailored down payment fit',
      data: (() => {
        const monthlyExpenses = monthlyIncome * 0.5;
        const emergencyFundTarget = monthlyExpenses * 3; // 3 months minimum
        const comfortFundTarget = monthlyExpenses * 6; // 6 months ideal

        // Calculate suitability score for each scenario
        const scoredScenarios = downPaymentScenarios.map((s) => {
          const monthsReserve = s.cashRemaining / monthlyExpenses;

          // Suitability scoring (0-100)
          let suitabilityScore = 0;
          const factors = [];

          // Emergency fund factor (0-40 points)
          if (s.cashRemaining >= comfortFundTarget) {
            suitabilityScore += 40;
            factors.push({ name: 'Emergency Fund', score: 40, max: 40, status: 'excellent', note: '6+ months reserve' });
          } else if (s.cashRemaining >= emergencyFundTarget) {
            const fundScore = 25 + ((s.cashRemaining - emergencyFundTarget) / (comfortFundTarget - emergencyFundTarget)) * 15;
            suitabilityScore += fundScore;
            factors.push({ name: 'Emergency Fund', score: Math.round(fundScore), max: 40, status: 'good', note: '3-6 months reserve' });
          } else if (s.cashRemaining > 0) {
            const fundScore = (s.cashRemaining / emergencyFundTarget) * 25;
            suitabilityScore += fundScore;
            factors.push({ name: 'Emergency Fund', score: Math.round(fundScore), max: 40, status: 'tight', note: '<3 months reserve' });
          } else {
            factors.push({ name: 'Emergency Fund', score: 0, max: 40, status: 'fail', note: 'Negative balance' });
          }

          // Monthly payment factor (0-25 points) - lower PMI with higher down
          const pmiSavings = s.ltv <= 80 ? 25 : (97 - s.ltv) * 1.5;
          suitabilityScore += pmiSavings;
          factors.push({
            name: 'Monthly Payment',
            score: Math.round(pmiSavings),
            max: 25,
            status: s.ltv <= 80 ? 'excellent' : s.ltv <= 90 ? 'good' : 'fair',
            note: s.ltv <= 80 ? 'No PMI required' : `PMI: ${formatCurrencyFull(s.piti.pmi)}/mo`,
          });

          // Financial flexibility factor (0-20 points)
          const flexScore = Math.min(20, (s.cashRemaining / 5000) * 10);
          suitabilityScore += Math.max(0, flexScore);
          factors.push({
            name: 'Financial Flexibility',
            score: Math.round(Math.max(0, flexScore)),
            max: 20,
            status: flexScore >= 15 ? 'excellent' : flexScore >= 10 ? 'good' : flexScore >= 5 ? 'fair' : 'tight',
            note: s.cashRemaining >= 5000 ? 'Room for unexpected costs' : 'Limited cushion',
          });

          // Equity start factor (0-15 points)
          const equityScore = Math.min(15, s.pct * 100);
          suitabilityScore += equityScore;
          factors.push({
            name: 'Starting Equity',
            score: Math.round(equityScore),
            max: 15,
            status: s.pct >= 0.10 ? 'excellent' : s.pct >= 0.05 ? 'good' : 'fair',
            note: `${(s.pct * 100).toFixed(0)}% equity on day 1`,
          });

          // Determine fit level
          let fitLevel, fitDescription;
          if (suitabilityScore >= 80) {
            fitLevel = 'perfect';
            fitDescription = 'Tailored Fit';
          } else if (suitabilityScore >= 60) {
            fitLevel = 'good';
            fitDescription = 'Good Fit';
          } else if (suitabilityScore >= 40) {
            fitLevel = 'acceptable';
            fitDescription = 'Acceptable';
          } else {
            fitLevel = 'poor';
            fitDescription = 'Poor Fit';
          }

          return {
            ...s,
            label: s.label,
            downPayment: s.downPayment,
            closingCosts: s.closingCosts,
            cashRemaining: s.cashRemaining,
            monthsReserve,
            suitabilityScore: Math.round(suitabilityScore),
            factors,
            fitLevel,
            fitDescription,
          };
        });

        // Find the optimal (custom tailored) down payment
        // Target: Leave exactly 3 months expenses after closing
        const targetReserve = emergencyFundTarget;
        const baseClosingCosts = CalculatorService.calculateClosingCosts(
          homePrices.baseline * 0.95,
          homePrices.baseline
        ).total;

        // Solve: savings - downPayment - closingCosts = targetReserve
        // closingCosts varies slightly with loan amount, but use approximation
        const optimalDownPayment = Math.max(
          homePrices.baseline * 0.03, // minimum 3%
          Math.min(
            profile.savings - targetReserve - baseClosingCosts,
            homePrices.baseline * 0.20 // max 20%
          )
        );
        const optimalPct = optimalDownPayment / homePrices.baseline;
        const optimalLoanAmount = homePrices.baseline - optimalDownPayment;
        const optimalClosingCosts = CalculatorService.calculateClosingCosts(optimalLoanAmount, homePrices.baseline).total;
        const optimalCashRemaining = profile.savings - optimalDownPayment - optimalClosingCosts;
        const optimalPiti = CalculatorService.calculatePITI({
          loanAmount: optimalLoanAmount,
          interestRate: market.interestRate,
          homePrice: homePrices.baseline,
          creditScore: profile.creditScore,
        });

        const tailoredOption = {
          label: 'Tailored Fit',
          pct: optimalPct,
          downPayment: optimalDownPayment,
          loanAmount: optimalLoanAmount,
          closingCosts: optimalClosingCosts,
          cashRemaining: optimalCashRemaining,
          monthsReserve: optimalCashRemaining / monthlyExpenses,
          piti: optimalPiti,
          ltv: (optimalLoanAmount / homePrices.baseline) * 100,
          isCustom: true,
        };

        // Find best standard option
        const bestStandard = scoredScenarios.reduce((best, s) =>
          s.suitabilityScore > best.suitabilityScore ? s : best
        );

        return {
          savings: profile.savings,
          homePrice: homePrices.baseline,
          monthlyExpenses,
          emergencyFundTarget,
          comfortFundTarget,
          scenarios: scoredScenarios,
          tailoredOption,
          bestStandard,
          monthlyIncome,
        };
      })(),
    },
    {
      id: 'closing-costs',
      name: 'Closing Costs',
      color: '#64748b',
      shortDescription: 'Itemized costs to close your loan',
      data: (() => {
        const loanAmount = homePrices.baseline * 0.95;
        const closingCosts = CalculatorService.calculateClosingCosts(
          loanAmount,
          homePrices.baseline,
          'CA',
          market.interestRate
        );
        return {
          homePrice: homePrices.baseline,
          loanAmount,
          downPayment: homePrices.baseline * 0.05,
          closingCosts,
          totalCashNeeded: (homePrices.baseline * 0.05) + closingCosts.total,
          savings: profile.savings,
        };
      })(),
    },
    {
      id: 'repayment-strategy',
      name: 'Repayment Strategy',
      color: '#10b981',
      shortDescription: 'Payoff options & wealth building',
      data: (() => {
        const loanAmount = homePrices.baseline * 0.95;
        const monthlyRate = market.interestRate / 100 / 12;
        const basePayment = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate, 30);

        // Standard 30-year scenario
        const standard30 = {
          term: 30,
          payment: basePayment,
          totalPaid: basePayment * 360,
          totalInterest: (basePayment * 360) - loanAmount,
        };

        // Extra $200/month scenario
        const extra200Payment = basePayment + 200;
        let balance = loanAmount;
        let months = 0;
        let totalInterestExtra200 = 0;
        while (balance > 0 && months < 360) {
          const interestPayment = balance * monthlyRate;
          const principalPayment = Math.min(extra200Payment - interestPayment, balance);
          totalInterestExtra200 += interestPayment;
          balance -= principalPayment;
          months++;
        }
        const extra200 = {
          extraMonthly: 200,
          payment: extra200Payment,
          months,
          years: (months / 12).toFixed(1),
          totalInterest: totalInterestExtra200,
          interestSaved: standard30.totalInterest - totalInterestExtra200,
          yearsSaved: 30 - (months / 12),
        };

        // Extra $500/month scenario
        const extra500Payment = basePayment + 500;
        balance = loanAmount;
        months = 0;
        let totalInterestExtra500 = 0;
        while (balance > 0 && months < 360) {
          const interestPayment = balance * monthlyRate;
          const principalPayment = Math.min(extra500Payment - interestPayment, balance);
          totalInterestExtra500 += interestPayment;
          balance -= principalPayment;
          months++;
        }
        const extra500 = {
          extraMonthly: 500,
          payment: extra500Payment,
          months,
          years: (months / 12).toFixed(1),
          totalInterest: totalInterestExtra500,
          interestSaved: standard30.totalInterest - totalInterestExtra500,
          yearsSaved: 30 - (months / 12),
        };

        // Biweekly payment scenario (26 half payments = 13 monthly payments/year)
        const biweeklyPayment = basePayment / 2;
        balance = loanAmount;
        let biweeklyPeriods = 0;
        let totalInterestBiweekly = 0;
        const biweeklyRate = market.interestRate / 100 / 26;
        while (balance > 0 && biweeklyPeriods < 780) { // 30 years * 26
          const interestPayment = balance * biweeklyRate;
          const principalPayment = Math.min(biweeklyPayment - interestPayment, balance);
          totalInterestBiweekly += interestPayment;
          balance -= principalPayment;
          biweeklyPeriods++;
        }
        const biweekly = {
          payment: biweeklyPayment,
          frequency: 'Every 2 weeks',
          months: Math.round(biweeklyPeriods / 2.17),
          years: (biweeklyPeriods / 26).toFixed(1),
          totalInterest: totalInterestBiweekly,
          interestSaved: standard30.totalInterest - totalInterestBiweekly,
          yearsSaved: 30 - (biweeklyPeriods / 26),
        };

        // 15-year loan comparison
        const payment15 = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate - 0.5, 15);
        const fifteenYear = {
          term: 15,
          rate: market.interestRate - 0.5,
          payment: payment15,
          totalPaid: payment15 * 180,
          totalInterest: (payment15 * 180) - loanAmount,
          interestSaved: standard30.totalInterest - ((payment15 * 180) - loanAmount),
          extraMonthlyNeeded: payment15 - basePayment,
        };

        return {
          loanAmount,
          interestRate: market.interestRate,
          standard30,
          extra200,
          extra500,
          biweekly,
          fifteenYear,
          monthlyIncome,
        };
      })(),
    },
    {
      id: 'exit-strategy',
      name: 'Exit Strategy',
      color: '#8b5cf6',
      shortDescription: 'Future scenarios & flexibility',
      data: (() => {
        const loanAmount = homePrices.baseline * 0.95;
        const downPayment = homePrices.baseline * 0.05;
        const closingCostsBuy = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;
        const monthlyRate = market.interestRate / 100 / 12;

        // Calculate equity position at different years
        const equityTimeline = [1, 2, 3, 5, 7, 10].map(year => {
          // Home appreciation (3% annual)
          const futureHomeValue = homePrices.baseline * Math.pow(1.03, year);

          // Remaining loan balance
          let balance = loanAmount;
          const payment = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate, 30);
          for (let m = 0; m < year * 12; m++) {
            const interest = balance * monthlyRate;
            balance -= (payment - interest);
          }

          // Equity
          const equity = futureHomeValue - balance;
          const equityPercent = (equity / futureHomeValue) * 100;

          // Sale scenario (6% realtor fees, ~1% other closing costs)
          const sellingCosts = futureHomeValue * 0.07;
          const netProceeds = futureHomeValue - balance - sellingCosts;

          // ROI calculation
          const totalInvested = downPayment + closingCostsBuy;
          const roi = ((netProceeds - totalInvested) / totalInvested) * 100;

          return {
            year,
            homeValue: futureHomeValue,
            remainingLoan: balance,
            equity,
            equityPercent,
            sellingCosts,
            netProceeds,
            roi,
            canSellProfitably: netProceeds > totalInvested,
          };
        });

        // Refinance scenarios
        const refinanceScenarios = [
          { name: 'Rate drops 1%', newRate: market.interestRate - 1 },
          { name: 'Rate drops 2%', newRate: market.interestRate - 2 },
        ].map(scenario => {
          const currentPayment = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate, 30);
          const newPayment = CalculatorService.calculateMonthlyPI(loanAmount, scenario.newRate, 30);
          const monthlySavings = currentPayment - newPayment;
          const refinanceCosts = loanAmount * 0.02; // ~2% closing costs
          const breakEvenMonths = refinanceCosts / monthlySavings;

          return {
            ...scenario,
            currentPayment,
            newPayment,
            monthlySavings,
            refinanceCosts,
            breakEvenMonths: Math.round(breakEvenMonths),
            worthIt: breakEvenMonths < 36, // Less than 3 years to break even
          };
        });

        // Rental potential
        const estimatedRent = homePrices.baseline * 0.006; // 0.6% of home value monthly
        const monthlyMortgage = baselinePiti.total;
        const cashFlow = estimatedRent - monthlyMortgage;
        const rentalScenario = {
          estimatedRent,
          monthlyMortgage,
          cashFlow,
          isPositive: cashFlow > 0,
          capRate: ((estimatedRent * 12 - (baselinePiti.propertyTax + baselinePiti.insurance) * 12) / homePrices.baseline) * 100,
        };

        return {
          homePrice: homePrices.baseline,
          loanAmount,
          downPayment,
          closingCostsBuy,
          interestRate: market.interestRate,
          equityTimeline,
          refinanceScenarios,
          rentalScenario,
          currentPayment: baselinePiti.total,
        };
      })(),
    },
    {
      id: 'program-options',
      name: 'Program Options',
      color: '#6366f1',
      shortDescription: 'Compare loan programs for you',
      data: (() => {
        const loanAmount = homePrices.baseline * 0.95;
        const downPayment5 = homePrices.baseline * 0.05;
        const downPayment3 = homePrices.baseline * 0.03;
        const downPayment35 = homePrices.baseline * 0.035;

        // Calculate payments for different programs
        const conventionalPiti = CalculatorService.calculatePITI({
          loanAmount: homePrices.baseline * 0.95,
          interestRate: market.interestRate,
          homePrice: homePrices.baseline,
          creditScore: profile.creditScore,
        });

        const fhaPiti = CalculatorService.calculatePITI({
          loanAmount: homePrices.baseline * 0.965,
          interestRate: market.interestRate + 0.125,
          homePrice: homePrices.baseline,
          creditScore: profile.creditScore,
        });
        // FHA MIP is different from conventional PMI
        const fhaMipUpfront = homePrices.baseline * 0.965 * 0.0175;
        const fhaMipMonthly = (homePrices.baseline * 0.965 * 0.0055) / 12;

        // Conventional 3% down
        const conventional3Piti = CalculatorService.calculatePITI({
          loanAmount: homePrices.baseline * 0.97,
          interestRate: market.interestRate,
          homePrice: homePrices.baseline,
          creditScore: profile.creditScore,
        });

        // Build program details
        const programs = [
          {
            id: 'conventional-5',
            name: 'Conventional 5% Down',
            lender: 'Fannie Mae / Freddie Mac',
            category: 'conventional',
            downPaymentPct: 5,
            downPayment: downPayment5,
            loanAmount: homePrices.baseline * 0.95,
            interestRate: market.interestRate,
            monthlyPayment: conventionalPiti.total,
            pmi: conventionalPiti.pmi,
            pmiRemovable: true,
            closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total,
            totalCashNeeded: downPayment5 + CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total,
            creditScoreMin: 620,
            dtiMax: 45,
            pros: [
              'PMI cancels automatically at 78% LTV',
              'No upfront mortgage insurance fee',
              'More competitive rates with good credit',
              'Flexible property types allowed',
              'No income limits in most areas',
            ],
            cons: [
              'Higher credit score requirements',
              'Higher PMI rates if credit is lower',
              'Stricter debt-to-income requirements',
            ],
            bestFor: 'Buyers with good credit who want PMI to go away',
            aiInsight: `With your ${profile.creditScore} credit score, you qualify for competitive conventional rates. Your PMI of ${formatCurrencyFull(conventionalPiti.pmi)}/month will automatically cancel once you reach 22% equity (roughly 7-8 years), or you can request removal at 20% equity.`,
            suitabilityScore: profile.creditScore >= 700 ? 92 : profile.creditScore >= 680 ? 78 : 65,
          },
          {
            id: 'conventional-3',
            name: 'Conventional 3% Down',
            lender: 'Fannie Mae HomeReady / Freddie Mac Home Possible',
            category: 'conventional',
            downPaymentPct: 3,
            downPayment: downPayment3,
            loanAmount: homePrices.baseline * 0.97,
            interestRate: market.interestRate,
            monthlyPayment: conventional3Piti.total,
            pmi: conventional3Piti.pmi,
            pmiRemovable: true,
            closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline * 0.97, homePrices.baseline).total,
            totalCashNeeded: downPayment3 + CalculatorService.calculateClosingCosts(homePrices.baseline * 0.97, homePrices.baseline).total,
            creditScoreMin: 620,
            dtiMax: 45,
            pros: [
              'Only 3% down payment required',
              'PMI still cancellable at 20% equity',
              'Income limits may provide rate discounts',
              'Homebuyer education may reduce PMI',
              'Gift funds allowed for entire down payment',
            ],
            cons: [
              'Higher monthly payment due to larger loan',
              'Higher PMI due to higher LTV',
              'May have income limits in some areas',
              'Takes longer to build equity',
            ],
            bestFor: 'First-time buyers who want to preserve cash',
            aiInsight: `This program maximizes your cash reserves. With only ${formatCurrency(downPayment3)} down, you'd keep ${formatCurrency(profile.savings - downPayment3 - CalculatorService.calculateClosingCosts(homePrices.baseline * 0.97, homePrices.baseline).total)} in savings for emergencies. The higher PMI is a trade-off for financial flexibility.`,
            suitabilityScore: profile.savings < 30000 ? 88 : 72,
          },
          {
            id: 'fha',
            name: 'FHA Loan',
            lender: 'Federal Housing Administration',
            category: 'government',
            downPaymentPct: 3.5,
            downPayment: downPayment35,
            loanAmount: homePrices.baseline * 0.965,
            interestRate: market.interestRate + 0.125,
            monthlyPayment: fhaPiti.total + fhaMipMonthly - fhaPiti.pmi, // Replace PMI with MIP
            pmi: fhaMipMonthly,
            pmiRemovable: false,
            mipUpfront: fhaMipUpfront,
            closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline * 0.965, homePrices.baseline).total + fhaMipUpfront,
            totalCashNeeded: downPayment35 + CalculatorService.calculateClosingCosts(homePrices.baseline * 0.965, homePrices.baseline).total,
            creditScoreMin: 580,
            dtiMax: 50,
            pros: [
              'Lower credit score requirements (580+)',
              'Only 3.5% down payment',
              'More lenient DTI limits (up to 50%)',
              'Seller can contribute up to 6% toward closing',
              'Accepts non-traditional credit history',
            ],
            cons: [
              'MIP required for life of loan (if <10% down)',
              '1.75% upfront MIP added to loan balance',
              'Property must meet FHA standards',
              'Loan limits apply (varies by county)',
              'Must refinance to remove mortgage insurance',
            ],
            bestFor: 'Buyers with lower credit scores or limited savings',
            aiInsight: `FHA could work for you, but with your ${profile.creditScore} credit score, conventional may be better. The FHA upfront MIP of ${formatCurrency(fhaMipUpfront)} gets added to your loan, and unlike conventional PMI, FHA mortgage insurance never goes away unless you refinance.`,
            suitabilityScore: profile.creditScore < 680 ? 85 : 58,
          },
          {
            id: 'va',
            name: 'VA Loan',
            lender: 'Department of Veterans Affairs',
            category: 'government',
            downPaymentPct: 0,
            downPayment: 0,
            loanAmount: homePrices.baseline,
            interestRate: market.interestRate - 0.25,
            monthlyPayment: CalculatorService.calculatePITI({
              loanAmount: homePrices.baseline,
              interestRate: market.interestRate - 0.25,
              homePrice: homePrices.baseline,
              creditScore: profile.creditScore,
            }).total - CalculatorService.calculatePITI({
              loanAmount: homePrices.baseline,
              interestRate: market.interestRate - 0.25,
              homePrice: homePrices.baseline,
              creditScore: profile.creditScore,
            }).pmi,
            pmi: 0,
            pmiRemovable: null,
            fundingFee: homePrices.baseline * 0.023,
            closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
            totalCashNeeded: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
            creditScoreMin: 620,
            dtiMax: 60,
            pros: [
              'No down payment required',
              'No monthly mortgage insurance',
              'Lower interest rates than conventional',
              'More flexible DTI requirements',
              'No prepayment penalties',
              'Seller can pay all closing costs',
            ],
            cons: [
              'Must be veteran, active duty, or eligible spouse',
              'VA funding fee (2.3% first use, can be financed)',
              'Property must meet VA minimum standards',
              'Primary residence only',
            ],
            bestFor: 'Veterans and active military wanting best terms',
            aiInsight: `If you have VA eligibility, this is likely your best option. Zero down payment, no PMI, and typically the lowest rates available. The 2.3% funding fee (${formatCurrency(homePrices.baseline * 0.023)}) can be rolled into the loan if you prefer to preserve cash.`,
            suitabilityScore: 0, // 0 means "check eligibility"
            requiresEligibility: true,
            eligibilityNote: 'Requires military service or eligible spouse status',
          },
          {
            id: 'usda',
            name: 'USDA Loan',
            lender: 'US Department of Agriculture',
            category: 'government',
            downPaymentPct: 0,
            downPayment: 0,
            loanAmount: homePrices.baseline,
            interestRate: market.interestRate - 0.125,
            monthlyPayment: CalculatorService.calculatePITI({
              loanAmount: homePrices.baseline,
              interestRate: market.interestRate - 0.125,
              homePrice: homePrices.baseline,
              creditScore: profile.creditScore,
            }).total - CalculatorService.calculatePITI({
              loanAmount: homePrices.baseline,
              interestRate: market.interestRate - 0.125,
              homePrice: homePrices.baseline,
              creditScore: profile.creditScore,
            }).pmi + (homePrices.baseline * 0.0035 / 12),
            pmi: homePrices.baseline * 0.0035 / 12,
            pmiRemovable: false,
            guaranteeFee: homePrices.baseline * 0.01,
            closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
            totalCashNeeded: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
            creditScoreMin: 640,
            dtiMax: 41,
            pros: [
              'No down payment required',
              'Lower guarantee fee than FHA MIP',
              'Competitive interest rates',
              'Low monthly guarantee fee (0.35%)',
              'Seller can contribute toward closing costs',
            ],
            cons: [
              'Property must be in eligible rural area',
              'Income limits apply (115% of area median)',
              'Primary residence only',
              'Upfront guarantee fee (1%)',
              'Geographic restrictions',
            ],
            bestFor: 'Buyers in rural/suburban areas under income limits',
            aiInsight: `USDA loans offer zero down, but the property must be in an eligible area (many suburbs qualify). With your income of ${formatCurrency(profile.annualIncome)}, you'd need to verify you're under the area income limit for your county.`,
            suitabilityScore: 0,
            requiresEligibility: true,
            eligibilityNote: 'Requires eligible rural location and income under area limit',
          },
        ];

        // Calculate best match
        const eligiblePrograms = programs.filter(p => !p.requiresEligibility);
        const bestMatch = eligiblePrograms.reduce((best, p) =>
          p.suitabilityScore > best.suitabilityScore ? p : best
        , eligiblePrograms[0]);

        return {
          homePrice: homePrices.baseline,
          programs,
          bestMatch,
          profile: {
            creditScore: profile.creditScore,
            income: profile.annualIncome,
            savings: profile.savings,
            monthlyDebts: profile.monthlyDebts,
            isFirstTimeBuyer: true,
          },
        };
      })(),
    },
    {
      id: 'cost-to-waiting',
      name: 'Cost of Waiting',
      color: '#f97316',
      shortDescription: 'What delay really costs you',
      data: {
        homePrice: homePrices.baseline,
        currentRent: profile.currentRent,
        interestRate: market.interestRate,
        downPaymentPct: 5,
        savings: profile.savings,
        monthlyIncome: monthlyIncome,
        // Default assumptions for waiting scenarios
        homeAppreciationRate: 4.0, // Annual home price growth
        rateIncreasePerYear: 0.5, // Rate increase per year of waiting
        rentIncreaseRate: 3.0, // Annual rent increase
      },
    },
    {
      id: 'prepay-or-invest',
      name: 'Prepay or Invest',
      color: '#14b8a6',
      shortDescription: 'Extra payments vs market returns',
      data: {
        loanAmount: homePrices.baseline * 0.95,
        interestRate: market.interestRate,
        termYears: market.termYears,
        // Default values for calculator
        monthlyExtraCash: 500,
        estimatedMarketReturn: 7.0, // After-tax market return assumption
        currentEquity: homePrices.baseline * 0.05, // Down payment as starting equity
        homePrice: homePrices.baseline,
      },
    },
    // ========================================================================
    // NEW CALCULATORS - Phase 1: Can I Buy?
    // ========================================================================
    {
      id: 'emergency-runway',
      name: 'Emergency Runway',
      color: '#0891b2',
      shortDescription: 'Months of survival after closing',
      data: (() => {
        const downPayment = homePrices.baseline * 0.05;
        const closingCosts = CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total;
        const postCloseSavings = profile.savings - downPayment - closingCosts;
        const monthlyExpenses = monthlyIncome * 0.5; // Non-housing expenses
        const totalMonthlyBurn = baselinePiti.total + monthlyExpenses;

        // Scenarios
        const scenarios = [
          {
            name: 'Full Income',
            monthlyBurn: totalMonthlyBurn - monthlyIncome,
            months: postCloseSavings > 0 ? Infinity : 0,
            status: 'safe'
          },
          {
            name: 'Job Loss (0% income)',
            monthlyBurn: totalMonthlyBurn,
            months: postCloseSavings / totalMonthlyBurn,
            status: postCloseSavings / totalMonthlyBurn >= 6 ? 'safe' : postCloseSavings / totalMonthlyBurn >= 3 ? 'caution' : 'danger'
          },
          {
            name: 'Reduced Income (50%)',
            monthlyBurn: totalMonthlyBurn - (monthlyIncome * 0.5),
            months: postCloseSavings / (totalMonthlyBurn - (monthlyIncome * 0.5)),
            status: 'caution'
          },
          {
            name: 'After Major Repair ($10k)',
            monthlyBurn: totalMonthlyBurn,
            months: (postCloseSavings - 10000) / totalMonthlyBurn,
            status: (postCloseSavings - 10000) / totalMonthlyBurn >= 3 ? 'caution' : 'danger'
          }
        ];

        return {
          savings: profile.savings,
          downPayment,
          closingCosts,
          postCloseSavings,
          monthlyExpenses,
          piti: baselinePiti.total,
          totalMonthlyBurn,
          scenarios,
          recommendedReserve: monthlyExpenses * 6,
          riskLevel: postCloseSavings >= monthlyExpenses * 6 ? 'low' :
                     postCloseSavings >= monthlyExpenses * 3 ? 'moderate' : 'high'
        };
      })(),
    },
    {
      id: 'stress-test',
      name: 'Life Happens Stress Test',
      color: '#dc2626',
      shortDescription: 'Survive income drops & expense spikes',
      data: (() => {
        const scenarios = [
          {
            name: 'Rate Increase +2%',
            trigger: 'ARM adjustment or refinance',
            newPayment: CalculatorService.calculatePITI({
              loanAmount: homePrices.baseline * 0.95,
              interestRate: market.interestRate + 2,
              homePrice: homePrices.baseline,
              creditScore: profile.creditScore,
            }).total,
            currentPayment: baselinePiti.total,
            impact: 0,
            newDti: 0,
            survivable: true
          },
          {
            name: 'Property Tax +20%',
            trigger: 'Reassessment',
            newPayment: baselinePiti.total + (baselinePiti.propertyTax * 0.2),
            currentPayment: baselinePiti.total,
            impact: baselinePiti.propertyTax * 0.2,
            newDti: 0,
            survivable: true
          },
          {
            name: 'Insurance Spike +30%',
            trigger: 'Market conditions',
            newPayment: baselinePiti.total + (baselinePiti.insurance * 0.3),
            currentPayment: baselinePiti.total,
            impact: baselinePiti.insurance * 0.3,
            newDti: 0,
            survivable: true
          },
          {
            name: 'Income Reduction -20%',
            trigger: 'Job change, reduced hours',
            newPayment: baselinePiti.total,
            currentPayment: baselinePiti.total,
            impact: monthlyIncome * 0.2,
            newDti: 0,
            survivable: true
          },
          {
            name: 'Combined Stress',
            trigger: 'Multiple events',
            newPayment: baselinePiti.total + (baselinePiti.propertyTax * 0.1) + (baselinePiti.insurance * 0.15),
            currentPayment: baselinePiti.total,
            impact: 0,
            newDti: 0,
            survivable: true
          }
        ];

        // Calculate DTI and survivability for each
        scenarios.forEach(s => {
          const effectiveIncome = s.name.includes('Income') ? monthlyIncome * 0.8 : monthlyIncome;
          s.newDti = ((s.newPayment + profile.monthlyDebts) / effectiveIncome) * 100;
          s.survivable = s.newDti <= 50;
          s.impact = s.newPayment - s.currentPayment;
        });

        const passCount = scenarios.filter(s => s.survivable).length;

        return {
          baseline: { piti: baselinePiti.total, dti: dti.backEnd },
          scenarios,
          monthlyIncome,
          monthlyDebts: profile.monthlyDebts,
          resilienceScore: (passCount / scenarios.length) * 100,
          passCount,
          totalScenarios: scenarios.length
        };
      })(),
    },
    // ========================================================================
    // NEW CALCULATORS - Phase 2: What Does This Really Cost?
    // ========================================================================
    {
      id: 'payment-shock',
      name: 'Payment Shock Forecast',
      color: '#ea580c',
      shortDescription: 'Future payment increases',
      data: (() => {
        const projections = Array.from({ length: 10 }, (_, year) => {
          const taxMultiplier = Math.pow(1.03, year); // 3% annual increase
          const insuranceMultiplier = Math.pow(1.04, year); // 4% annual increase
          const hoaMultiplier = Math.pow(1.05, year); // 5% annual increase

          const projectedTax = baselinePiti.propertyTax * taxMultiplier;
          const projectedInsurance = baselinePiti.insurance * insuranceMultiplier;
          const projectedHoa = (propertyData.hoaMonthly || 0) * hoaMultiplier;
          // PMI drops off around year 7 typically
          const projectedPmi = year >= 7 ? 0 : baselinePiti.pmi;

          const total = baselinePiti.principalInterest + projectedTax + projectedInsurance + projectedHoa + projectedPmi;

          return {
            year: year + 1,
            principalInterest: baselinePiti.principalInterest,
            propertyTax: projectedTax,
            insurance: projectedInsurance,
            hoa: projectedHoa,
            pmi: projectedPmi,
            total,
            increase: total - baselinePiti.total,
            percentIncrease: ((total - baselinePiti.total) / baselinePiti.total) * 100
          };
        });

        const maxPayment = Math.max(...projections.map(p => p.total));
        const shockIndex = ((maxPayment - baselinePiti.total) / baselinePiti.total) * 100;

        return {
          current: baselinePiti,
          projections,
          maxPayment,
          shockIndex,
          peakYear: projections.findIndex(p => p.total === maxPayment) + 1
        };
      })(),
    },
    {
      id: 'lifestyle-fit',
      name: 'Lifestyle Fit Index',
      color: '#7c3aed',
      shortDescription: 'Post-purchase spending power',
      data: (() => {
        // Current budget as renter
        const currentBudget = {
          housing: profile.currentRent,
          utilities: profile.budget?.utilities || 200,
          food: profile.budget?.food || 500,
          transportation: profile.budget?.transportation || 350,
          healthcare: profile.budget?.healthcare || 100,
          entertainment: profile.budget?.entertainment || 200,
          savings: profile.budget?.savings || 400,
          other: profile.budget?.other || 250,
          debts: profile.monthlyDebts
        };
        currentBudget.total = Object.values(currentBudget).reduce((a, b) => a + b, 0);

        // Homeowner budget
        const maintenanceReserve = (homePrices.baseline * 0.01) / 12; // 1% rule
        const homeownerBudget = {
          housing: baselinePiti.total,
          utilities: (profile.budget?.utilities || 200) * 1.4, // Higher for homeowner
          maintenance: maintenanceReserve,
          food: profile.budget?.food || 500,
          transportation: profile.budget?.transportation || 350,
          healthcare: profile.budget?.healthcare || 100,
          entertainment: (profile.budget?.entertainment || 200) * 0.8, // May need to reduce
          savings: Math.max(0, (profile.budget?.savings || 400) - 150),
          other: profile.budget?.other || 250,
          debts: profile.monthlyDebts
        };
        homeownerBudget.total = Object.values(homeownerBudget).reduce((a, b) => a + b, 0);

        const discretionaryIncome = monthlyIncome - homeownerBudget.total;
        const fitScore = (discretionaryIncome / monthlyIncome) * 100;

        let fitLevel;
        if (fitScore >= 25) fitLevel = 'comfortable';
        else if (fitScore >= 15) fitLevel = 'adequate';
        else if (fitScore >= 5) fitLevel = 'tight';
        else fitLevel = 'strained';

        return {
          monthlyIncome,
          currentBudget,
          homeownerBudget,
          monthlySqueeze: homeownerBudget.total - currentBudget.total,
          discretionaryIncome,
          fitScore,
          fitLevel,
          adjustments: [
            { category: 'Housing', change: baselinePiti.total - profile.currentRent },
            { category: 'Utilities', change: homeownerBudget.utilities - currentBudget.utilities },
            { category: 'Maintenance', change: maintenanceReserve },
            { category: 'Entertainment', change: homeownerBudget.entertainment - currentBudget.entertainment },
            { category: 'Savings', change: homeownerBudget.savings - currentBudget.savings }
          ]
        };
      })(),
    },
    // ========================================================================
    // NEW CALCULATORS - Phase 3: Is This Smart Long-Term?
    // ========================================================================
    {
      id: 'break-even-horizon',
      name: 'Break-Even Horizon',
      color: '#0d9488',
      shortDescription: 'Years to beat renting',
      data: (() => {
        const downPayment = homePrices.baseline * 0.05;
        const loanAmount = homePrices.baseline * 0.95;
        const closingCosts = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;
        const initialInvestment = downPayment + closingCosts;

        const comparison = [];
        let breakEvenYear = null;
        let cumulativeRenterCost = 0;
        let cumulativeBuyerCost = initialInvestment;
        let currentRent = profile.currentRent;
        let homeValue = homePrices.baseline;
        let balance = loanAmount;

        for (let year = 1; year <= 10; year++) {
          // Renter path
          const yearlyRent = currentRent * 12;
          cumulativeRenterCost += yearlyRent;
          const renterInvestment = initialInvestment * Math.pow(1.07, year);

          // Buyer path
          homeValue = homePrices.baseline * Math.pow(1.03, year);
          const yearlyPiti = baselinePiti.total * 12;
          const maintenance = homeValue * 0.01;
          cumulativeBuyerCost += yearlyPiti + maintenance;

          // Principal paid this year (simplified)
          const yearlyPrincipal = loanAmount * (year <= 5 ? 0.018 : year <= 10 ? 0.022 : 0.028);
          balance = Math.max(0, balance - yearlyPrincipal);
          const equity = homeValue - balance;

          // Net positions
          const netRenter = renterInvestment - cumulativeRenterCost;
          const netBuyer = equity - cumulativeBuyerCost + initialInvestment;
          const buyerAdvantage = netBuyer - netRenter;

          comparison.push({
            year,
            renterCost: cumulativeRenterCost,
            renterInvestment,
            netRenter,
            buyerCost: cumulativeBuyerCost,
            homeValue,
            equity,
            netBuyer,
            buyerAdvantage
          });

          if (!breakEvenYear && buyerAdvantage > 0) {
            breakEvenYear = year;
          }

          currentRent *= 1.03; // 3% rent increase
        }

        return {
          initialInvestment,
          comparison,
          breakEvenYear: breakEvenYear || '>10',
          assumptions: {
            homeAppreciation: 3,
            rentIncrease: 3,
            investmentReturn: 7,
            maintenance: 1
          }
        };
      })(),
    },
    {
      id: 'equity-velocity',
      name: 'Equity Velocity',
      color: '#059669',
      shortDescription: 'Wealth accumulation speed',
      data: (() => {
        const downPayment = homePrices.baseline * 0.05;
        const loanAmount = homePrices.baseline * 0.95;
        const timeline = [];

        let balance = loanAmount;
        let homeValue = homePrices.baseline;

        for (let year = 1; year <= 15; year++) {
          homeValue = homePrices.baseline * Math.pow(1.03, year);

          // Principal paid (increases over time due to amortization)
          const principalRate = year <= 5 ? 0.018 : year <= 10 ? 0.022 : 0.028;
          const yearlyPrincipal = loanAmount * principalRate;
          balance = Math.max(0, balance - yearlyPrincipal);

          const equityFromPrincipal = loanAmount - balance;
          const equityFromAppreciation = homeValue - homePrices.baseline;
          const totalEquity = downPayment + equityFromPrincipal + equityFromAppreciation;

          const prevEquity = year > 1 ? timeline[year - 2].totalEquity : downPayment;
          const velocityThisYear = totalEquity - prevEquity;
          const roi = ((totalEquity - downPayment) / downPayment) * 100;

          timeline.push({
            year,
            homeValue,
            loanBalance: balance,
            equityFromDownPayment: downPayment,
            equityFromPrincipal,
            equityFromAppreciation,
            totalEquity,
            velocityThisYear,
            roi
          });
        }

        const peakVelocityYear = timeline.reduce((max, t) =>
          t.velocityThisYear > (max?.velocityThisYear || 0) ? t : max, timeline[0]);

        return {
          initialEquity: downPayment,
          timeline,
          year5Equity: timeline[4].totalEquity,
          year10Equity: timeline[9].totalEquity,
          peakVelocityYear: peakVelocityYear.year,
          peakVelocity: peakVelocityYear.velocityThisYear
        };
      })(),
    },
    {
      id: 'tax-benefit',
      name: 'Tax Benefit Realization',
      color: '#16a34a',
      shortDescription: 'After-tax payment savings',
      data: (() => {
        const loanAmount = homePrices.baseline * 0.95;
        const annualPropertyTax = homePrices.baseline * (market.taxRate || 0.0107);
        const marginalRate = profile.annualIncome >= 100525 ? 0.24 :
                           profile.annualIncome >= 47150 ? 0.22 :
                           profile.annualIncome >= 11600 ? 0.12 : 0.10;
        const standardDeduction = 14600; // Single filer 2024

        const yearlyBenefits = Array.from({ length: 10 }, (_, year) => {
          // Interest decreases over time
          const interestRate = (10 - year) / 10; // Simplified decay
          const yearlyInterest = loanAmount * (market.interestRate / 100) * interestRate;
          const propertyTaxDeduction = Math.min(annualPropertyTax, 10000); // SALT cap
          const totalDeductions = yearlyInterest + propertyTaxDeduction;
          const aboveStandard = Math.max(0, totalDeductions - standardDeduction);
          const taxSavings = aboveStandard * marginalRate;

          return {
            year: year + 1,
            mortgageInterest: yearlyInterest,
            propertyTax: annualPropertyTax,
            totalDeductions,
            standardDeduction,
            aboveStandard,
            taxSavings,
            monthlyBenefit: taxSavings / 12,
            effectivePayment: baselinePiti.total - (taxSavings / 12)
          };
        });

        const totalTenYearSavings = yearlyBenefits.reduce((sum, y) => sum + y.taxSavings, 0);
        const itemizingBeneficial = yearlyBenefits[0].totalDeductions > standardDeduction;

        return {
          marginalTaxRate: marginalRate,
          standardDeduction,
          yearlyBenefits,
          totalTenYearSavings,
          itemizingBeneficial,
          year1Savings: yearlyBenefits[0].taxSavings,
          year1MonthlyBenefit: yearlyBenefits[0].monthlyBenefit,
          effectiveYear1Payment: yearlyBenefits[0].effectivePayment
        };
      })(),
    },
    {
      id: 'inflation-hedge',
      name: 'Inflation Hedge Index',
      color: '#ca8a04',
      shortDescription: 'Protection from rising costs',
      data: (() => {
        const scenarios = [
          { name: 'Low Inflation (2%)', inflation: 0.02, appreciation: 0.025 },
          { name: 'Normal Inflation (3%)', inflation: 0.03, appreciation: 0.04 },
          { name: 'High Inflation (5%)', inflation: 0.05, appreciation: 0.06 }
        ];

        const analysis = scenarios.map(scenario => {
          const projections = Array.from({ length: 10 }, (_, year) => {
            const futureRent = profile.currentRent * Math.pow(1 + scenario.inflation, year + 1);
            const homeValue = homePrices.baseline * Math.pow(1 + scenario.appreciation, year + 1);
            // P&I is fixed, but T&I increase with inflation
            const taxInsIncrease = (baselinePiti.propertyTax + baselinePiti.insurance) *
                                  (Math.pow(1 + scenario.inflation, year + 1) - 1);
            const adjustedPiti = baselinePiti.total + taxInsIncrease;

            return {
              year: year + 1,
              rent: futureRent,
              homeValue,
              fixedPortion: baselinePiti.principalInterest,
              adjustedPiti,
              renterAnnualCost: futureRent * 12,
              buyerAnnualCost: adjustedPiti * 12,
              annualSavings: (futureRent - adjustedPiti) * 12
            };
          });

          const totalHedgeValue = projections.reduce((sum, p) => sum + p.annualSavings, 0);

          return {
            scenario: scenario.name,
            inflationRate: scenario.inflation * 100,
            projections,
            totalHedgeValue,
            year10Rent: projections[9].rent,
            year10Piti: projections[9].adjustedPiti
          };
        });

        const normalScenario = analysis[1]; // Normal inflation
        const hedgeScore = (normalScenario.totalHedgeValue / (baselinePiti.total * 120)) * 100;

        return {
          currentRent: profile.currentRent,
          currentPiti: baselinePiti.total,
          analysis,
          hedgeScore: Math.max(0, hedgeScore),
          recommendation: hedgeScore > 20 ? 'strong' : hedgeScore > 0 ? 'moderate' : 'weak'
        };
      })(),
    },
    {
      id: 'job-mobility',
      name: 'Job Mobility Impact',
      color: '#0369a1',
      shortDescription: 'Cost if you need to move',
      data: (() => {
        const downPayment = homePrices.baseline * 0.05;
        const loanAmount = homePrices.baseline * 0.95;
        const closingCosts = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;
        const initialInvestment = downPayment + closingCosts;

        const relocateScenarios = [1, 2, 3, 5, 7].map(year => {
          const homeValue = homePrices.baseline * Math.pow(1.03, year);
          // Simplified balance calculation
          const principalPaid = loanAmount * (year <= 3 ? 0.018 * year : 0.018 * 3 + 0.022 * (year - 3));
          const loanBalance = loanAmount - principalPaid;
          const sellingCosts = homeValue * 0.08; // 6% realtor + 2% closing
          const netProceeds = homeValue - loanBalance - sellingCosts;
          const totalPiti = baselinePiti.total * 12 * year;

          // Compare to renting
          let rentPaid = 0;
          let currentRent = profile.currentRent;
          for (let y = 0; y < year; y++) {
            rentPaid += currentRent * 12;
            currentRent *= 1.03;
          }

          const totalBuyingCost = initialInvestment + totalPiti - netProceeds;
          const betterThanRenting = totalBuyingCost < rentPaid;

          return {
            year,
            homeValue,
            loanBalance,
            sellingCosts,
            netProceeds,
            totalPiti,
            rentEquivalent: rentPaid,
            totalBuyingCost,
            costPerMonth: totalBuyingCost / (year * 12),
            profitOrLoss: netProceeds - initialInvestment,
            betterThanRenting
          };
        });

        const breakEvenYear = relocateScenarios.find(s => s.profitOrLoss > 0)?.year || '>7';

        return {
          initialInvestment,
          currentRent: profile.currentRent,
          scenarios: relocateScenarios,
          breakEvenYear,
          minimumStay: breakEvenYear,
          flexibilityScore: relocateScenarios[1].betterThanRenting ? 'good' :
                          relocateScenarios[2].betterThanRenting ? 'moderate' : 'poor'
        };
      })(),
    },
  ];
};

// ============================================================================
// CALCULATOR DETAIL VIEWS
// ============================================================================

const RepaymentStrategyView = ({ data }) => {
  const { standard30, extra200, extra500, biweekly, fifteenYear, loanAmount, interestRate } = data;
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Current Loan', step: 1 },
    { id: 'strategies', label: 'Payoff Strategies', step: 2 },
    { id: 'fifteen', label: '15-Year Option', step: 3 },
    { id: 'recommendation', label: 'Recommendation', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Repayment Strategy</h2>
        <p className="detail-subtitle">
          How to pay off your mortgage faster and build wealth
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Your Current Loan Details</h3>
              <p>Understanding your baseline before exploring strategies</p>
            </div>
            <div className="repay-summary">
              <div className="repay-summary-item">
                <div className="summary-label">Loan Amount</div>
                <div className="summary-value">{formatCurrency(loanAmount)}</div>
              </div>
              <div className="repay-summary-item">
                <div className="summary-label">Interest Rate</div>
                <div className="summary-value">{interestRate}%</div>
              </div>
              <div className="repay-summary-item">
                <div className="summary-label">Standard Payment</div>
                <div className="summary-value">{formatCurrencyFull(standard30.payment)}</div>
              </div>
              <div className="repay-summary-item highlight">
                <div className="summary-label">Total Interest (30yr)</div>
                <div className="summary-value negative">{formatCurrency(standard30.totalInterest)}</div>
              </div>
            </div>
            <div className="panel-insight">
              <strong>Did you know?</strong> Over 30 years, you'll pay {formatCurrency(standard30.totalInterest)} in interest —
              that's {formatPercent((standard30.totalInterest / loanAmount) * 100)} of your original loan amount!
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('strategies')}>
              Explore Payoff Strategies →
            </button>
          </div>
        )}

        {activeTab === 'strategies' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Accelerated Payoff Strategies</h3>
              <p>Compare different ways to pay off your mortgage faster</p>
            </div>
            <div className="strategy-cards">
              <div className="strategy-card baseline">
                <div className="strategy-header">
                  <div className="strategy-name">Standard 30-Year</div>
                  <div className="strategy-badge baseline">Baseline</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(standard30.payment)}</span>
                  <span className="payment-freq">/month</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span>30 years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span className="negative">{formatCurrency(standard30.totalInterest)}</span></div>
                  <div className="detail-row"><span>Interest Saved</span><span>—</span></div>
                </div>
              </div>

              <div className="strategy-card">
                <div className="strategy-header">
                  <div className="strategy-name">+$200/month Extra</div>
                  <div className="strategy-badge good">Popular</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(extra200.payment)}</span>
                  <span className="payment-freq">/month</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span className="positive">{extra200.years} years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span>{formatCurrency(extra200.totalInterest)}</span></div>
                  <div className="detail-row highlight"><span>Interest Saved</span><span className="positive">{formatCurrency(extra200.interestSaved)}</span></div>
                </div>
                <div className="strategy-impact">Save {extra200.yearsSaved.toFixed(1)} years & {formatCurrency(extra200.interestSaved)}</div>
              </div>

              <div className="strategy-card recommended">
                <div className="strategy-header">
                  <div className="strategy-name">+$500/month Extra</div>
                  <div className="strategy-badge best">Best Value</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(extra500.payment)}</span>
                  <span className="payment-freq">/month</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span className="positive">{extra500.years} years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span>{formatCurrency(extra500.totalInterest)}</span></div>
                  <div className="detail-row highlight"><span>Interest Saved</span><span className="positive">{formatCurrency(extra500.interestSaved)}</span></div>
                </div>
                <div className="strategy-impact">Save {extra500.yearsSaved.toFixed(1)} years & {formatCurrency(extra500.interestSaved)}</div>
              </div>

              <div className="strategy-card">
                <div className="strategy-header">
                  <div className="strategy-name">Biweekly Payments</div>
                  <div className="strategy-badge">Easy</div>
                </div>
                <div className="strategy-payment">
                  <span className="payment-amount">{formatCurrencyFull(biweekly.payment)}</span>
                  <span className="payment-freq">/2 weeks</span>
                </div>
                <div className="strategy-details">
                  <div className="detail-row"><span>Payoff Time</span><span className="positive">{biweekly.years} years</span></div>
                  <div className="detail-row"><span>Total Interest</span><span>{formatCurrency(biweekly.totalInterest)}</span></div>
                  <div className="detail-row highlight"><span>Interest Saved</span><span className="positive">{formatCurrency(biweekly.interestSaved)}</span></div>
                </div>
                <div className="strategy-impact">Same budget, {biweekly.yearsSaved.toFixed(1)} years faster</div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('fifteen')}>
              See 15-Year Option →
            </button>
          </div>
        )}

        {activeTab === 'fifteen' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>15-Year Loan Alternative</h3>
              <p>A shorter term means higher payments but massive interest savings</p>
            </div>
            <div className="fifteen-year-card">
              <div className="fifteen-comparison">
                <div className="fifteen-side">
                  <div className="fifteen-label">30-Year Loan</div>
                  <div className="fifteen-payment">{formatCurrencyFull(standard30.payment)}/mo</div>
                  <div className="fifteen-interest">Total Interest: {formatCurrency(standard30.totalInterest)}</div>
                </div>
                <div className="fifteen-vs">vs</div>
                <div className="fifteen-side highlight">
                  <div className="fifteen-label">15-Year Loan ({fifteenYear.rate}%)</div>
                  <div className="fifteen-payment">{formatCurrencyFull(fifteenYear.payment)}/mo</div>
                  <div className="fifteen-interest">Total Interest: {formatCurrency(fifteenYear.totalInterest)}</div>
                </div>
              </div>
              <div className="fifteen-summary">
                <div className="summary-item">
                  <span>Extra Monthly Cost</span>
                  <span>+{formatCurrencyFull(fifteenYear.extraMonthlyNeeded)}</span>
                </div>
                <div className="summary-item highlight">
                  <span>Total Interest Saved</span>
                  <span className="positive">{formatCurrency(fifteenYear.interestSaved)}</span>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('recommendation')}>
              See Recommendation →
            </button>
          </div>
        )}

        {activeTab === 'recommendation' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Our Recommendation</h3>
              <p>The best strategy based on your situation</p>
            </div>
            <div className="recommendation-box">
              <div className="rec-badge">Best Strategy</div>
              <h4>Biweekly Payments</h4>
              <p>
                The biweekly payment strategy is the easiest win — same monthly budget but you make
                13 payments per year instead of 12, saving <strong>{formatCurrency(biweekly.interestSaved)}</strong> and
                <strong> {biweekly.yearsSaved.toFixed(1)} years</strong>.
              </p>
              <div className="rec-comparison">
                <div className="rec-item">
                  <span className="rec-label">Interest Saved</span>
                  <span className="rec-value positive">{formatCurrency(biweekly.interestSaved)}</span>
                </div>
                <div className="rec-item">
                  <span className="rec-label">Years Saved</span>
                  <span className="rec-value positive">{biweekly.yearsSaved.toFixed(1)} years</span>
                </div>
                <div className="rec-item">
                  <span className="rec-label">Effort Level</span>
                  <span className="rec-value">Easy - Just switch payment schedule</span>
                </div>
              </div>
            </div>
            <div className="alternative-strategies">
              <h5>If you have extra cash flow:</h5>
              <ul>
                <li>+$200/month saves {formatCurrency(extra200.interestSaved)} and {extra200.yearsSaved.toFixed(1)} years</li>
                <li>+$500/month saves {formatCurrency(extra500.interestSaved)} and {extra500.yearsSaved.toFixed(1)} years</li>
                <li>15-year loan saves {formatCurrency(fifteenYear.interestSaved)} (but requires {formatCurrencyFull(fifteenYear.extraMonthlyNeeded)} more/month)</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ExitStrategyView = ({ data }) => {
  const { equityTimeline, refinanceScenarios, rentalScenario, homePrice, currentPayment } = data;
  const [activeTab, setActiveTab] = useState('equity');

  const tabs = [
    { id: 'equity', label: 'Equity Timeline', step: 1 },
    { id: 'refinance', label: 'Refinance Options', step: 2 },
    { id: 'rental', label: 'Rental Potential', step: 3 },
    { id: 'summary', label: 'Summary', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Exit Strategy</h2>
        <p className="detail-subtitle">
          Understanding your options: sell, refinance, or rent
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'equity' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Equity Position Over Time</h3>
              <p>When can you sell profitably? (Assumes 3% annual appreciation)</p>
            </div>
            <div className="equity-timeline">
              <div className="timeline-header">
                <div>Year</div>
                <div>Home Value</div>
                <div>Equity</div>
                <div>Net if Sold</div>
                <div>ROI</div>
              </div>
              {equityTimeline.map((year) => (
                <div key={year.year} className={`timeline-row ${year.canSellProfitably ? 'profitable' : 'underwater'}`}>
                  <div className="year-cell">Year {year.year}</div>
                  <div>{formatCurrency(year.homeValue)}</div>
                  <div>
                    <span className="equity-amount">{formatCurrency(year.equity)}</span>
                    <span className="equity-pct">({formatPercent(year.equityPercent)})</span>
                  </div>
                  <div className={year.netProceeds > 0 ? 'positive' : 'negative'}>
                    {formatCurrency(year.netProceeds)}
                  </div>
                  <div className={year.roi > 0 ? 'positive' : 'negative'}>
                    {year.roi > 0 ? '+' : ''}{formatPercent(year.roi)}
                  </div>
                </div>
              ))}
            </div>
            <div className="timeline-note">
              * Net if Sold accounts for 7% selling costs (realtor fees + closing)
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('refinance')}>
              Explore Refinance Options →
            </button>
          </div>
        )}

        {activeTab === 'refinance' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Refinance Opportunities</h3>
              <p>If interest rates drop, here's what you could save</p>
            </div>
            <div className="refi-cards">
              {refinanceScenarios.map((scenario) => (
                <div key={scenario.name} className={`refi-card ${scenario.worthIt ? 'worth-it' : ''}`}>
                  <div className="refi-header">
                    <div className="refi-name">{scenario.name}</div>
                    <div className={`refi-badge ${scenario.worthIt ? 'yes' : 'maybe'}`}>
                      {scenario.worthIt ? 'Worth It' : 'Maybe'}
                    </div>
                  </div>
                  <div className="refi-rates">
                    <span>{data.interestRate}%</span>
                    <span className="arrow">→</span>
                    <span className="new-rate">{scenario.newRate}%</span>
                  </div>
                  <div className="refi-details">
                    <div className="refi-row"><span>New Payment</span><span>{formatCurrencyFull(scenario.newPayment)}</span></div>
                    <div className="refi-row highlight"><span>Monthly Savings</span><span className="positive">{formatCurrencyFull(scenario.monthlySavings)}</span></div>
                    <div className="refi-row"><span>Refi Costs (~2%)</span><span>{formatCurrency(scenario.refinanceCosts)}</span></div>
                    <div className="refi-row"><span>Break-Even</span><span>{scenario.breakEvenMonths} months</span></div>
                  </div>
                </div>
              ))}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('rental')}>
              See Rental Potential →
            </button>
          </div>
        )}

        {activeTab === 'rental' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Convert to Rental Property</h3>
              <p>What if you keep it and rent it out?</p>
            </div>
            <div className="rental-card">
              <div className="rental-calc">
                <div className="rental-row">
                  <span>Estimated Monthly Rent</span>
                  <span className="positive">{formatCurrencyFull(rentalScenario.estimatedRent)}</span>
                </div>
                <div className="rental-row">
                  <span>Monthly Mortgage (PITI)</span>
                  <span className="negative">-{formatCurrencyFull(rentalScenario.monthlyMortgage)}</span>
                </div>
                <div className={`rental-row total ${rentalScenario.isPositive ? 'positive' : 'negative'}`}>
                  <span>Monthly Cash Flow</span>
                  <span>{rentalScenario.cashFlow >= 0 ? '+' : ''}{formatCurrencyFull(rentalScenario.cashFlow)}</span>
                </div>
              </div>
              <div className="rental-metrics">
                <div className="metric">
                  <div className="metric-label">Cap Rate</div>
                  <div className="metric-value">{formatPercent(rentalScenario.capRate)}</div>
                </div>
                <div className="metric">
                  <div className="metric-label">Cash Flow Status</div>
                  <div className={`metric-value ${rentalScenario.isPositive ? 'positive' : 'negative'}`}>
                    {rentalScenario.isPositive ? 'Positive' : 'Negative'}
                  </div>
                </div>
              </div>
              <div className="rental-note">
                {rentalScenario.isPositive ? (
                  <>This property could generate passive income if you move and rent it out</>
                ) : (
                  <>You'd need to cover {formatCurrencyFull(Math.abs(rentalScenario.cashFlow))}/month if renting it out</>
                )}
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('summary')}>
              View Summary →
            </button>
          </div>
        )}

        {activeTab === 'summary' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Flexibility Summary</h3>
              <p>Your exit options at a glance</p>
            </div>
            <div className="exit-summary-grid">
              <div className="exit-option-card">
                <div className="option-icon">🏠</div>
                <h4>Sell</h4>
                <p>You'll have positive equity by Year 2, making selling viable.</p>
                <div className="option-status positive">Available after Year 2</div>
              </div>
              <div className="exit-option-card">
                <div className="option-icon">📉</div>
                <h4>Refinance</h4>
                <p>If rates drop 1%+, refinancing makes sense.</p>
                <div className="option-status">Monitor rate environment</div>
              </div>
              <div className="exit-option-card">
                <div className="option-icon">🏘️</div>
                <h4>Rent Out</h4>
                <p>The property {rentalScenario.isPositive ? 'could generate income' : 'would need subsidy'}.</p>
                <div className={`option-status ${rentalScenario.isPositive ? 'positive' : 'warning'}`}>
                  {rentalScenario.isPositive ? 'Cash flow positive' : 'Needs monthly subsidy'}
                </div>
              </div>
            </div>
            <div className="key-insight">
              <strong>Bottom Line:</strong> You have multiple exit options. This property provides financial flexibility
              whether you need to sell, refinance for better terms, or convert to an investment property.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const DownPaymentView = ({ data, profile }) => (
  <div className="calculator-detail">
    <div className="detail-header">
      <h2>Down Payment Options</h2>
      <p className="detail-subtitle">
        For a <strong>{formatCurrency(data.homePrice)}</strong> home
      </p>
    </div>

    <div className="savings-display">
      <div className="savings-label">Your Available Savings</div>
      <div className="savings-amount">{formatCurrency(data.savings)}</div>
    </div>

    <div className="scenarios-table">
      <div className="table-header">
        <div>Scenario</div>
        <div>Down Payment</div>
        <div>Monthly Payment</div>
        <div>PMI</div>
        <div>Cash Left</div>
      </div>
      {data.scenarios.map((scenario, idx) => (
        <div
          key={scenario.label}
          className={`table-row ${idx === 0 ? 'recommended' : ''} ${scenario.cashRemaining < 0 ? 'warning' : ''}`}
        >
          <div className="scenario-name">
            {scenario.label}
            {idx === 0 && <span className="rec-badge">Best for You</span>}
          </div>
          <div>{formatCurrency(scenario.downPayment)}</div>
          <div>{formatCurrencyFull(scenario.piti.total)}</div>
          <div>{formatCurrencyFull(scenario.piti.pmi)}/mo</div>
          <div className={scenario.cashRemaining < 0 ? 'negative' : scenario.cashRemaining < 5000 ? 'tight' : 'good'}>
            {formatCurrency(scenario.cashRemaining)}
            {scenario.cashRemaining < 0 && <span className="status-tag danger">SHORT</span>}
            {scenario.cashRemaining >= 0 && scenario.cashRemaining < 5000 && <span className="status-tag warning">TIGHT</span>}
            {scenario.cashRemaining >= 5000 && <span className="status-tag success">OK</span>}
          </div>
        </div>
      ))}
    </div>

    <div className="pmi-info">
      <h4>About PMI (Private Mortgage Insurance)</h4>
      <ul>
        <li>Required when down payment is less than 20%</li>
        <li>Automatically cancels when you reach 78% LTV</li>
        <li>Can request removal at 80% LTV with good payment history</li>
      </ul>
      <div className="pmi-timeline">
        {data.scenarios.filter(s => s.piti.pmi > 0).map((s) => (
          <div key={s.label} className="pmi-item">
            <strong>{s.label}:</strong> PMI of {formatCurrencyFull(s.piti.pmi)}/mo
            for ~{(s.pmiMonths / 12).toFixed(1)} years
          </div>
        ))}
      </div>
    </div>
  </div>
);

const MonthlyPaymentView = ({ data }) => {
  const [purchasePrice, setPurchasePrice] = useState(data.homePrice || 285000);

  const colors = {
    principalInterest: '#3b82f6',
    propertyTax: '#22c55e',
    insurance: '#f59e0b',
    pmi: '#ef4444',
    mip: '#8b5cf6', // Purple for FHA MIP
  };

  // Loan calculation helper
  const calculateMonthlyPI = (principal, annualRate, termYears = 30) => {
    const monthlyRate = annualRate / 100 / 12;
    const numPayments = termYears * 12;
    if (monthlyRate === 0) return principal / numPayments;
    return principal * (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) / (Math.pow(1 + monthlyRate, numPayments) - 1);
  };

  // Generate loan scenarios
  const generateScenarios = useMemo(() => {
    const taxRate = 0.0125; // 1.25% annual
    const insuranceRate = 0.0035; // 0.35% annual
    const convRate = data.rate || 6.875;
    const fhaRate = (data.rate || 6.875) - 0.25; // FHA typically 0.25% lower

    const scenarios = [
      {
        id: 'conv-3',
        label: '3% Down',
        type: 'Conventional',
        downPct: 3,
        rate: convRate,
        color: '#3b82f6',
      },
      {
        id: 'fha-3.5',
        label: '3.5% Down',
        type: 'FHA',
        downPct: 3.5,
        rate: fhaRate,
        color: '#8b5cf6',
      },
      {
        id: 'conv-5',
        label: '5% Down',
        type: 'Conventional',
        downPct: 5,
        rate: convRate,
        color: '#3b82f6',
        recommended: true,
      },
      {
        id: 'fha-5',
        label: '5% Down',
        type: 'FHA',
        downPct: 5,
        rate: fhaRate,
        color: '#8b5cf6',
      },
    ];

    return scenarios.map(scenario => {
      const downPayment = purchasePrice * (scenario.downPct / 100);
      let loanAmount = purchasePrice - downPayment;
      const ltv = (loanAmount / purchasePrice) * 100;

      // FHA calculations
      let upfrontMIP = 0;
      let monthlyMIP = 0;
      let monthlyPMI = 0;

      if (scenario.type === 'FHA') {
        // FHA Upfront MIP: 1.75% of loan amount (typically financed)
        upfrontMIP = loanAmount * 0.0175;
        loanAmount += upfrontMIP; // Finance the upfront MIP

        // FHA Annual MIP: 0.55% for 30-year loans with LTV > 95%, 0.50% for LTV <= 95%
        const annualMIPRate = ltv > 95 ? 0.0055 : 0.0050;
        monthlyMIP = (loanAmount * annualMIPRate) / 12;
      } else {
        // Conventional PMI: ~0.5-1% based on LTV and credit
        const pmiRate = ltv > 95 ? 0.0095 : ltv > 90 ? 0.0075 : 0.0055;
        monthlyPMI = (loanAmount * pmiRate) / 12;
      }

      const monthlyPI = calculateMonthlyPI(loanAmount, scenario.rate);
      const monthlyTax = (purchasePrice * taxRate) / 12;
      const monthlyInsurance = (purchasePrice * insuranceRate) / 12;

      const totalPayment = monthlyPI + monthlyTax + monthlyInsurance + monthlyPMI + monthlyMIP;

      // PMI/MIP duration estimate
      const yearsToRemovePMI = scenario.type === 'FHA'
        ? (ltv > 90 ? 'Life of loan' : '11 years')
        : `~${Math.ceil((ltv - 78) / 2)} years`;

      return {
        ...scenario,
        downPayment,
        loanAmount,
        ltv,
        upfrontMIP,
        piti: {
          principalInterest: monthlyPI,
          propertyTax: monthlyTax,
          insurance: monthlyInsurance,
          pmi: monthlyPMI,
          mip: monthlyMIP,
          total: totalPayment,
        },
        pmiDuration: yearsToRemovePMI,
      };
    });
  }, [purchasePrice, data.rate]);

  const getComponents = (scenario) => {
    const { piti } = scenario;
    const components = [
      { key: 'principalInterest', label: 'Principal & Interest', value: piti.principalInterest, color: colors.principalInterest },
      { key: 'propertyTax', label: 'Property Tax', value: piti.propertyTax, color: colors.propertyTax },
      { key: 'insurance', label: 'Insurance', value: piti.insurance, color: colors.insurance },
    ];

    if (scenario.type === 'FHA' && piti.mip > 0) {
      components.push({ key: 'mip', label: 'MIP (FHA)', value: piti.mip, color: colors.mip });
    } else if (piti.pmi > 0) {
      components.push({ key: 'pmi', label: 'PMI', value: piti.pmi, color: colors.pmi });
    }

    return components;
  };

  // Find lowest payment
  const lowestPayment = Math.min(...generateScenarios.map(s => s.piti.total));
  const lowestCashNeeded = Math.min(...generateScenarios.map(s => s.downPayment));

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Monthly Payment Comparison</h2>
        <p className="detail-subtitle">
          Compare Conventional vs FHA loans at different down payments
        </p>
      </div>

      {/* Purchase Price Slider */}
      <div className="price-slider-section">
        <div className="slider-header">
          <label>Purchase Price</label>
          <div className="slider-value">{formatCurrency(purchasePrice)}</div>
        </div>
        <input
          type="range"
          min="150000"
          max="750000"
          step="5000"
          value={purchasePrice}
          onChange={(e) => setPurchasePrice(Number(e.target.value))}
          className="price-slider"
        />
        <div className="slider-range">
          <span>$150,000</span>
          <span>$750,000</span>
        </div>
      </div>

      {/* Loan Type Headers */}
      <div className="loan-type-headers">
        <div className="loan-type-header conv">
          <span className="type-badge conv">Conventional</span>
          <span className="type-rate">{data.rate || 6.875}% rate</span>
        </div>
        <div className="loan-type-header fha">
          <span className="type-badge fha">FHA</span>
          <span className="type-rate">{((data.rate || 6.875) - 0.25).toFixed(3)}% rate</span>
        </div>
      </div>

      <div className="payment-comparison-grid four-col">
        {generateScenarios.map((scenario) => {
          const components = getComponents(scenario);
          const isLowest = scenario.piti.total === lowestPayment;
          const isLowestCash = scenario.downPayment === lowestCashNeeded;

          return (
            <div key={scenario.id} className={`payment-card ${scenario.type.toLowerCase()} ${scenario.recommended ? 'recommended' : ''}`}>
              <div className="payment-card-header">
                <div className="payment-card-title">
                  {scenario.label}
                  {scenario.recommended && <span className="rec-tag">Recommended</span>}
                </div>
                <div className="payment-card-type">{scenario.type}</div>
                <div className="payment-card-subtitle">
                  {formatCurrency(scenario.downPayment)} down
                </div>
              </div>

              <div className="payment-total">
                <div className="payment-total-label">Monthly Payment</div>
                <div className="payment-total-amount">
                  {formatCurrencyFull(scenario.piti.total)}
                  {isLowest && <span className="lowest-tag">Lowest</span>}
                </div>
              </div>

              <div className="payment-bar">
                {components.map((comp) => (
                  <div
                    key={comp.key}
                    className="payment-bar-segment"
                    style={{
                      width: `${(comp.value / scenario.piti.total) * 100}%`,
                      backgroundColor: comp.color,
                    }}
                    title={`${comp.label}: ${formatCurrencyFull(comp.value)}`}
                  />
                ))}
              </div>

              <div className="payment-breakdown">
                {components.map((comp) => (
                  <div key={comp.key} className="payment-line">
                    <div className="payment-line-indicator" style={{ backgroundColor: comp.color }} />
                    <div className="payment-line-label">{comp.label}</div>
                    <div className="payment-line-value">{formatCurrencyFull(comp.value)}</div>
                  </div>
                ))}
              </div>

              <div className="payment-card-footer">
                <div className="footer-row">
                  <span>Loan Amount</span>
                  <span>{formatCurrency(scenario.loanAmount)}</span>
                </div>
                <div className="footer-row">
                  <span>LTV</span>
                  <span>{scenario.ltv.toFixed(1)}%</span>
                </div>
                {scenario.type === 'FHA' && scenario.upfrontMIP > 0 && (
                  <div className="footer-row mip-note">
                    <span>Upfront MIP</span>
                    <span>{formatCurrency(scenario.upfrontMIP)}</span>
                  </div>
                )}
                <div className="footer-row pmi-note">
                  <span>{scenario.type === 'FHA' ? 'MIP Duration' : 'PMI Duration'}</span>
                  <span>{scenario.pmiDuration}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="payment-legend">
        <h4>Payment Components</h4>
        <div className="legend-items">
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: colors.principalInterest }} />
            <span>Principal & Interest — Goes toward loan balance</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: colors.propertyTax }} />
            <span>Property Tax — Held in escrow, paid annually</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: colors.insurance }} />
            <span>Homeowners Insurance — Required by lender</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: colors.pmi }} />
            <span>PMI (Conventional) — Removable at 78% LTV</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: colors.mip }} />
            <span>MIP (FHA) — 1.75% upfront + annual premium</span>
          </div>
        </div>
      </div>

      <div className="comparison-insights">
        <div className="insight-card">
          <div className="insight-icon">💰</div>
          <div className="insight-content">
            <strong>Conventional Pros:</strong> PMI can be removed once you reach 78% LTV. No upfront mortgage insurance. Better for higher credit scores (740+).
          </div>
        </div>
        <div className="insight-card">
          <div className="insight-icon">🏠</div>
          <div className="insight-content">
            <strong>FHA Pros:</strong> Lower credit score requirements (580+). Lower rates. Easier qualification. Great for first-time buyers.
          </div>
        </div>
      </div>

      {/* All In One Loan Comparison */}
      <AllInOneComparison
        purchasePrice={purchasePrice}
        conventionalRate={data.rate || 6.875}
      />
    </div>
  );
};

// All In One Loan Comparison Component
const AllInOneComparison = ({ purchasePrice, conventionalRate }) => {
  const [monthlyIncome, setMonthlyIncome] = useState(8000);
  const [monthlyExpenses, setMonthlyExpenses] = useState(4000);
  const [aioRate, setAioRate] = useState(7.5); // HELOC rates typically higher

  const downPaymentPct = 20; // All In One requires 20% down typically
  const downPayment = purchasePrice * (downPaymentPct / 100);
  const loanAmount = purchasePrice - downPayment;

  // Calculate traditional mortgage
  const calcTraditionalMonthly = (principal, rate, years = 30) => {
    const monthlyRate = rate / 100 / 12;
    const numPayments = years * 12;
    if (monthlyRate === 0) return principal / numPayments;
    return principal * (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) / (Math.pow(1 + monthlyRate, numPayments) - 1);
  };

  const traditionalMonthly = calcTraditionalMonthly(loanAmount, conventionalRate);
  const traditionalTotal30Yr = traditionalMonthly * 360;
  const traditionalInterest = traditionalTotal30Yr - loanAmount;

  // Calculate All In One (First-Lien HELOC with velocity banking)
  // In velocity banking, all income flows into the HELOC, reducing interest daily
  // Then expenses are paid out as needed
  const monthlyNetCashflow = monthlyIncome - monthlyExpenses;
  const avgDailyBalance = loanAmount - (monthlyNetCashflow / 2); // Simplified average

  // Interest only payment for comparison
  const aioInterestOnlyMonthly = (loanAmount * (aioRate / 100)) / 12;

  // With velocity banking, extra cashflow goes to principal
  // Simulating accelerated payoff
  const simulateAIOPayoff = () => {
    let balance = loanAmount;
    let months = 0;
    let totalInterestPaid = 0;
    const maxMonths = 360;

    while (balance > 0 && months < maxMonths) {
      // Daily interest calculation based on average balance
      const monthlyInterest = (balance * (aioRate / 100)) / 12;
      totalInterestPaid += monthlyInterest;

      // Net reduction = income - expenses - interest
      const netReduction = monthlyNetCashflow - monthlyInterest;

      if (netReduction > 0) {
        balance -= netReduction;
      } else {
        // If expenses + interest > income, balance increases
        balance -= netReduction; // Will be negative, so balance increases
      }

      months++;

      if (balance <= 0) break;
    }

    return {
      months: Math.min(months, maxMonths),
      years: Math.min(months / 12, 30),
      totalInterestPaid,
      paidOff: balance <= 0,
    };
  };

  const aioResult = simulateAIOPayoff();
  const interestSavings = traditionalInterest - aioResult.totalInterestPaid;
  const yearsSaved = 30 - aioResult.years;

  return (
    <div className="allinone-section">
      <div className="section-header-special">
        <div className="header-badge">
          <span className="badge-icon">🏦</span>
          <span>Alternative Strategy</span>
        </div>
        <h3>All In One Loan Comparison</h3>
        <p>First-Lien HELOC with Velocity Banking — Pay off your mortgage faster</p>
      </div>

      <div className="aio-inputs">
        <div className="aio-input-group">
          <label>Monthly Income</label>
          <div className="input-with-prefix">
            <span className="prefix">$</span>
            <input
              type="number"
              value={monthlyIncome}
              onChange={(e) => setMonthlyIncome(Number(e.target.value) || 0)}
            />
          </div>
        </div>
        <div className="aio-input-group">
          <label>Monthly Expenses</label>
          <div className="input-with-prefix">
            <span className="prefix">$</span>
            <input
              type="number"
              value={monthlyExpenses}
              onChange={(e) => setMonthlyExpenses(Number(e.target.value) || 0)}
            />
          </div>
        </div>
        <div className="aio-input-group">
          <label>HELOC Rate</label>
          <div className="input-with-suffix">
            <input
              type="number"
              step="0.125"
              value={aioRate}
              onChange={(e) => setAioRate(Number(e.target.value) || 0)}
            />
            <span className="suffix">%</span>
          </div>
        </div>
      </div>

      <div className="aio-comparison-grid">
        <div className="aio-card traditional">
          <div className="aio-card-header">
            <span className="aio-card-badge">Traditional</span>
            <h4>30-Year Fixed Mortgage</h4>
          </div>
          <div className="aio-card-body">
            <div className="aio-stat">
              <span className="stat-label">Loan Amount</span>
              <span className="stat-value">{formatCurrency(loanAmount)}</span>
            </div>
            <div className="aio-stat">
              <span className="stat-label">Interest Rate</span>
              <span className="stat-value">{conventionalRate}%</span>
            </div>
            <div className="aio-stat">
              <span className="stat-label">Monthly Payment</span>
              <span className="stat-value">{formatCurrency(traditionalMonthly)}</span>
            </div>
            <div className="aio-stat highlight">
              <span className="stat-label">Total Interest Paid</span>
              <span className="stat-value negative">{formatCurrency(traditionalInterest)}</span>
            </div>
            <div className="aio-stat">
              <span className="stat-label">Payoff Time</span>
              <span className="stat-value">30 years</span>
            </div>
          </div>
        </div>

        <div className="aio-card allinone featured">
          <div className="aio-card-header">
            <span className="aio-card-badge special">All In One</span>
            <h4>First-Lien HELOC</h4>
          </div>
          <div className="aio-card-body">
            <div className="aio-stat">
              <span className="stat-label">Credit Line</span>
              <span className="stat-value">{formatCurrency(loanAmount)}</span>
            </div>
            <div className="aio-stat">
              <span className="stat-label">HELOC Rate</span>
              <span className="stat-value">{aioRate}%</span>
            </div>
            <div className="aio-stat">
              <span className="stat-label">Interest-Only Min</span>
              <span className="stat-value">{formatCurrency(aioInterestOnlyMonthly)}</span>
            </div>
            <div className="aio-stat highlight">
              <span className="stat-label">Total Interest Paid</span>
              <span className="stat-value positive">{formatCurrency(aioResult.totalInterestPaid)}</span>
            </div>
            <div className="aio-stat">
              <span className="stat-label">Payoff Time</span>
              <span className="stat-value positive">{aioResult.years.toFixed(1)} years</span>
            </div>
          </div>
        </div>
      </div>

      {interestSavings > 0 && (
        <div className="aio-savings-banner">
          <div className="savings-highlight">
            <div className="savings-amount">{formatCurrency(interestSavings)}</div>
            <div className="savings-label">Potential Interest Savings</div>
          </div>
          <div className="savings-details">
            <div className="savings-detail">
              <span className="detail-icon">⏱️</span>
              <span>Pay off {yearsSaved.toFixed(1)} years faster</span>
            </div>
            <div className="savings-detail">
              <span className="detail-icon">💵</span>
              <span>Your monthly cashflow: {formatCurrency(monthlyNetCashflow)}</span>
            </div>
          </div>
        </div>
      )}

      <div className="aio-how-it-works">
        <h4>How All In One Works</h4>
        <div className="how-steps">
          <div className="how-step">
            <div className="step-number">1</div>
            <div className="step-content">
              <strong>Deposit All Income</strong>
              <p>Your paychecks go directly into the HELOC, immediately reducing your balance and interest.</p>
            </div>
          </div>
          <div className="how-step">
            <div className="step-number">2</div>
            <div className="step-content">
              <strong>Pay Expenses as Needed</strong>
              <p>Use the built-in checking account for bills. Only borrow what you spend.</p>
            </div>
          </div>
          <div className="how-step">
            <div className="step-number">3</div>
            <div className="step-content">
              <strong>Interest Calculated Daily</strong>
              <p>Unlike traditional mortgages, interest is based on your daily balance, not the original loan amount.</p>
            </div>
          </div>
          <div className="how-step">
            <div className="step-number">4</div>
            <div className="step-content">
              <strong>Accelerated Payoff</strong>
              <p>Your positive cashflow continuously reduces principal, potentially paying off your home in 5-10 years.</p>
            </div>
          </div>
        </div>
      </div>

      <div className="aio-requirements">
        <h4>Requirements</h4>
        <div className="req-grid">
          <div className="req-item">
            <span className="req-icon">📊</span>
            <span className="req-text">680+ Credit Score</span>
          </div>
          <div className="req-item">
            <span className="req-icon">💰</span>
            <span className="req-text">20% Down Payment</span>
          </div>
          <div className="req-item">
            <span className="req-icon">📈</span>
            <span className="req-text">Positive Monthly Cashflow</span>
          </div>
          <div className="req-item">
            <span className="req-icon">🏠</span>
            <span className="req-text">Primary Residence</span>
          </div>
        </div>
      </div>

      <div className="aio-disclaimer">
        <strong>Note:</strong> The All In One Loan has a variable rate that may change over time.
        Results shown are estimates based on consistent cashflow. Actual savings depend on your
        spending habits, income consistency, and market conditions. Consult a mortgage professional
        for personalized advice.
      </div>
    </div>
  );
};

const DTIView = ({ data, profile }) => {
  const { dti, monthlyIncome, housingPayment, otherDebts, remaining } = data;
  const totalDebt = housingPayment + otherDebts;

  const getStatusColor = (value) => {
    if (value <= 36) return '#22c55e';
    if (value <= 43) return '#f59e0b';
    return '#ef4444';
  };

  const getStatusLabel = (value) => {
    if (value <= 28) return 'Excellent';
    if (value <= 36) return 'Good';
    if (value <= 43) return 'Acceptable';
    return 'High';
  };

  // Calculate percentages for visual bar
  const housingPct = (housingPayment / monthlyIncome) * 100;
  const otherDebtPct = (otherDebts / monthlyIncome) * 100;
  const remainingPct = (remaining / monthlyIncome) * 100;

  return (
    <div className="calculator-detail dti-view">
      <div className="detail-header">
        <h2>Debt-to-Income Analysis</h2>
        <p className="detail-subtitle">
          How your mortgage fits into your total financial picture
        </p>
      </div>

      {/* Summary Cards */}
      <div className="dti-summary-cards">
        <div className="dti-summary-card">
          <div className="summary-icon">💰</div>
          <div className="summary-content">
            <div className="summary-label">Gross Monthly Income</div>
            <div className="summary-value income">{formatCurrencyFull(monthlyIncome)}</div>
          </div>
        </div>
        <div className="dti-summary-card">
          <div className="summary-icon">🏠</div>
          <div className="summary-content">
            <div className="summary-label">Housing Payment (PITI)</div>
            <div className="summary-value expense">{formatCurrencyFull(housingPayment)}</div>
          </div>
        </div>
        <div className="dti-summary-card">
          <div className="summary-icon">💳</div>
          <div className="summary-content">
            <div className="summary-label">Other Monthly Debts</div>
            <div className="summary-value expense">{formatCurrencyFull(otherDebts)}</div>
          </div>
        </div>
        <div className="dti-summary-card highlight">
          <div className="summary-icon">✨</div>
          <div className="summary-content">
            <div className="summary-label">Remaining for Living</div>
            <div className="summary-value remaining">{formatCurrencyFull(remaining)}</div>
            <div className="summary-subtext">{formatCurrencyFull(remaining / 4)}/week</div>
          </div>
        </div>
      </div>

      {/* DTI Gauges */}
      <div className="dti-gauges-section">
        <h3>Your DTI Ratios</h3>
        <div className="dti-gauges-row">
          <div className="dti-gauge-card">
            <div className="gauge-header">
              <span className="gauge-title">Front-End DTI</span>
              <span className="gauge-subtitle">Housing Only</span>
            </div>
            <div className="circular-gauge">
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" className="gauge-track" />
                <circle
                  cx="60" cy="60" r="50"
                  className="gauge-progress"
                  style={{
                    stroke: getStatusColor(dti.frontEnd),
                    strokeDasharray: `${Math.min(dti.frontEnd / 50 * 314, 314)} 314`
                  }}
                />
              </svg>
              <div className="gauge-center">
                <span className="gauge-percent" style={{ color: getStatusColor(dti.frontEnd) }}>
                  {dti.frontEnd.toFixed(1)}%
                </span>
                <span className="gauge-status">{getStatusLabel(dti.frontEnd)}</span>
              </div>
            </div>
            <div className="gauge-legend">
              <div className="legend-item">
                <span className="legend-marker target"></span>
                <span>Target: &lt;28%</span>
              </div>
              <div className="legend-item">
                <span className="legend-marker limit"></span>
                <span>Limit: 31%</span>
              </div>
            </div>
          </div>

          <div className="dti-gauge-card">
            <div className="gauge-header">
              <span className="gauge-title">Back-End DTI</span>
              <span className="gauge-subtitle">All Debts</span>
            </div>
            <div className="circular-gauge">
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" className="gauge-track" />
                <circle
                  cx="60" cy="60" r="50"
                  className="gauge-progress"
                  style={{
                    stroke: getStatusColor(dti.backEnd),
                    strokeDasharray: `${Math.min(dti.backEnd / 50 * 314, 314)} 314`
                  }}
                />
              </svg>
              <div className="gauge-center">
                <span className="gauge-percent" style={{ color: getStatusColor(dti.backEnd) }}>
                  {dti.backEnd.toFixed(1)}%
                </span>
                <span className="gauge-status">{getStatusLabel(dti.backEnd)}</span>
              </div>
            </div>
            <div className="gauge-legend">
              <div className="legend-item">
                <span className="legend-marker target"></span>
                <span>Target: &lt;36%</span>
              </div>
              <div className="legend-item">
                <span className="legend-marker limit"></span>
                <span>QM Limit: 43%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Income Allocation Visual */}
      <div className="dti-allocation-section">
        <h3>Monthly Income Allocation</h3>
        <div className="allocation-bar-container">
          <div className="allocation-bar">
            <div
              className="allocation-segment housing"
              style={{ width: `${housingPct}%` }}
              title={`Housing: ${housingPct.toFixed(1)}%`}
            />
            <div
              className="allocation-segment debts"
              style={{ width: `${otherDebtPct}%` }}
              title={`Other Debts: ${otherDebtPct.toFixed(1)}%`}
            />
            <div
              className="allocation-segment remaining"
              style={{ width: `${remainingPct}%` }}
              title={`Remaining: ${remainingPct.toFixed(1)}%`}
            />
          </div>
          <div className="allocation-labels">
            <div className="allocation-label">
              <span className="label-color housing"></span>
              <span className="label-text">Housing</span>
              <span className="label-value">{housingPct.toFixed(0)}%</span>
            </div>
            <div className="allocation-label">
              <span className="label-color debts"></span>
              <span className="label-text">Other Debts</span>
              <span className="label-value">{otherDebtPct.toFixed(0)}%</span>
            </div>
            <div className="allocation-label">
              <span className="label-color remaining"></span>
              <span className="label-text">Remaining</span>
              <span className="label-value">{remainingPct.toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Debt Breakdown Table */}
      <div className="dti-breakdown-section">
        <h3>Monthly Debt Breakdown</h3>
        <div className="breakdown-table">
          <div className="breakdown-row income-row">
            <span className="row-icon">💵</span>
            <span className="row-label">Gross Monthly Income</span>
            <span className="row-value positive">+{formatCurrencyFull(monthlyIncome)}</span>
          </div>
          <div className="breakdown-divider"></div>
          <div className="breakdown-row">
            <span className="row-icon">🏠</span>
            <span className="row-label">Proposed Mortgage (PITI)</span>
            <span className="row-value negative">-{formatCurrencyFull(housingPayment)}</span>
          </div>
          <div className="breakdown-row">
            <span className="row-icon">🎓</span>
            <span className="row-label">Student Loans</span>
            <span className="row-value negative">-{formatCurrencyFull(profile?.debts?.studentLoan || 450)}</span>
          </div>
          <div className="breakdown-row">
            <span className="row-icon">🚗</span>
            <span className="row-label">Auto Loan</span>
            <span className="row-value negative">-{formatCurrencyFull(profile?.debts?.autoLoan || 220)}</span>
          </div>
          {profile?.debts?.creditCards > 0 && (
            <div className="breakdown-row">
              <span className="row-icon">💳</span>
              <span className="row-label">Credit Card Minimums</span>
              <span className="row-value negative">-{formatCurrencyFull(profile.debts.creditCards)}</span>
            </div>
          )}
          <div className="breakdown-divider"></div>
          <div className="breakdown-row total-row">
            <span className="row-icon">📊</span>
            <span className="row-label">Total Monthly Debt</span>
            <span className="row-value negative">-{formatCurrencyFull(totalDebt)}</span>
          </div>
          <div className="breakdown-row remaining-row">
            <span className="row-icon">✨</span>
            <span className="row-label">Available for Living Expenses</span>
            <span className="row-value highlight">{formatCurrencyFull(remaining)}</span>
          </div>
        </div>
      </div>

      {/* Status Banner */}
      <div className={`dti-status-banner ${dti.status}`}>
        <div className="status-icon">
          {dti.status === 'excellent' && '✅'}
          {dti.status === 'acceptable' && '⚠️'}
          {dti.status === 'stretched' && '🚨'}
        </div>
        <div className="status-content">
          <div className="status-title">
            {dti.status === 'excellent' && 'Excellent Position'}
            {dti.status === 'acceptable' && 'Acceptable, But Tight'}
            {dti.status === 'stretched' && 'Stretched Budget'}
          </div>
          <div className="status-message">
            {dti.status === 'excellent' && 'Your debt-to-income ratio is well within guidelines. You have comfortable room in your budget.'}
            {dti.status === 'acceptable' && 'You qualify for this loan, but your budget will be tighter. Consider building emergency savings first.'}
            {dti.status === 'stretched' && 'Your DTI exceeds typical guidelines. Consider a lower price point or paying down existing debt first.'}
          </div>
        </div>
      </div>
    </div>
  );
};

const RentVsBuyView = ({ data }) => {
  const { taxBenefits, netWorthProjection } = data;
  const year5Renter = netWorthProjection.renterPath[4];
  const year5Buyer = netWorthProjection.buyerPath[4];
  const wealthDifference = year5Buyer.netWorth - year5Renter.netWorth;
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Monthly Costs', step: 1 },
    { id: 'taxes', label: 'Tax Benefits', step: 2 },
    { id: 'networth', label: 'Net Worth', step: 3 },
    { id: 'timeline', label: 'Timeline', step: 4 },
    { id: 'verdict', label: 'Verdict', step: 5 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Rent vs. Buy: True Cost Analysis</h2>
        <p className="detail-subtitle">
          Including tax benefits, net worth building, and true cost of ownership
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Monthly Payment Comparison</h3>
              <p>See the true cost of renting vs. buying</p>
            </div>
            <div className="cost-comparison-grid">
              <div className="cost-column rent">
                <div className="cost-column-header">Renting</div>
                <div className="cost-row main"><span>Monthly Rent</span><span>{formatCurrencyFull(data.currentRent)}</span></div>
                <div className="cost-row sub"><span>Wealth Building</span><span className="negative">$0</span></div>
                <div className="cost-row sub"><span>Tax Benefits</span><span>$0</span></div>
                <div className="cost-row total"><span>True Monthly Cost</span><span className="negative">{formatCurrencyFull(data.currentRent)}</span></div>
              </div>
              <div className="cost-column buy">
                <div className="cost-column-header">Buying</div>
                <div className="cost-row main"><span>PITI Payment</span><span>{formatCurrencyFull(data.mortgagePayment)}</span></div>
                <div className="cost-row sub positive-row"><span>Principal (Savings)</span><span className="positive">-{formatCurrencyFull(data.principalBuildup)}</span></div>
                <div className="cost-row sub positive-row"><span>Tax Savings</span><span className="positive">-{formatCurrencyFull(taxBenefits.monthlyTaxSavings)}</span></div>
                <div className="cost-row total"><span>True Monthly Cost</span><span className="highlight">{formatCurrencyFull(data.trueMonthlyCost)}</span></div>
              </div>
            </div>
            <div className="true-cost-insight">
              <strong>True Cost Difference:</strong> After accounting for equity building and tax benefits,
              your effective housing cost is only <strong>{formatCurrencyFull(data.trueMonthlyCost - data.currentRent)}</strong> more per month!
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('taxes')}>See Tax Benefits →</button>
          </div>
        )}

        {activeTab === 'taxes' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Tax Benefits Breakdown (Year 1)</h3>
              <p>How homeownership reduces your tax burden</p>
            </div>
            <div className="tax-grid">
              <div className="tax-item"><div className="tax-label">Mortgage Interest</div><div className="tax-value">{formatCurrency(taxBenefits.annualInterest)}</div></div>
              <div className="tax-item"><div className="tax-label">Property Tax</div><div className="tax-value">{formatCurrency(taxBenefits.annualPropertyTax)}</div></div>
              <div className="tax-item"><div className="tax-label">Total Deductions</div><div className="tax-value">{formatCurrency(taxBenefits.totalDeductions)}</div></div>
              <div className="tax-item highlight"><div className="tax-label">Annual Tax Savings</div><div className="tax-value positive">{formatCurrency(taxBenefits.annualTaxSavings)}</div></div>
            </div>
            <div className="tax-note">
              {taxBenefits.itemizingMakesSense ? (
                <>Itemizing deductions saves you <strong>{formatCurrency(taxBenefits.annualTaxSavings)}/year</strong> over standard deduction</>
              ) : (
                <>Note: Standard deduction ({formatCurrency(taxBenefits.standardDeduction)}) may be better — consult a tax professional</>
              )}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('networth')}>See Net Worth Impact →</button>
          </div>
        )}

        {activeTab === 'networth' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>5-Year Net Worth Projection</h3>
              <p>Compare your wealth building potential</p>
            </div>
            <div className="net-worth-comparison">
              <div className="net-worth-card renter">
                <div className="nw-header">If You Continue Renting</div>
                <div className="nw-amount">{formatCurrency(year5Renter.netWorth)}</div>
                <div className="nw-breakdown">
                  <div className="nw-item"><span>Starting savings invested</span><span>+{formatCurrency(data.downPayment + 9000)}</span></div>
                  <div className="nw-item negative"><span>Rent paid (gone forever)</span><span>-{formatCurrency(data.fiveYearRent)}</span></div>
                </div>
              </div>
              <div className="net-worth-card buyer highlighted">
                <div className="nw-header">If You Buy</div>
                <div className="nw-amount">{formatCurrency(year5Buyer.netWorth)}</div>
                <div className="nw-breakdown">
                  <div className="nw-item"><span>Home Value (Year 5)</span><span>{formatCurrency(year5Buyer.homeValue)}</span></div>
                  <div className="nw-item"><span>Remaining Mortgage</span><span>-{formatCurrency(year5Buyer.remainingLoan)}</span></div>
                  <div className="nw-item positive"><span>Home Equity Built</span><span className="positive">{formatCurrency(year5Buyer.homeEquity)}</span></div>
                </div>
              </div>
            </div>
            <div className="wealth-difference">
              <div className="wealth-diff-content">
                <div className="wealth-diff-label">Wealth Advantage of Buying (5 Years)</div>
                <div className="wealth-diff-amount">+{formatCurrency(wealthDifference)}</div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('timeline')}>See Year-by-Year →</button>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Year-by-Year Net Worth</h3>
              <p>Track how your wealth grows over time</p>
            </div>
            <div className="year-table">
              <div className="year-table-header">
                <div>Year</div>
                <div>Renter Net Worth</div>
                <div>Buyer Net Worth</div>
                <div>Buyer Advantage</div>
              </div>
              {netWorthProjection.renterPath.map((renter, idx) => {
                const buyer = netWorthProjection.buyerPath[idx];
                const advantage = buyer.netWorth - renter.netWorth;
                return (
                  <div key={renter.year} className="year-table-row">
                    <div>Year {renter.year}</div>
                    <div>{formatCurrency(renter.netWorth)}</div>
                    <div>{formatCurrency(buyer.netWorth)}</div>
                    <div className={advantage > 0 ? 'positive' : 'negative'}>
                      {advantage > 0 ? '+' : ''}{formatCurrency(advantage)}
                    </div>
                  </div>
                );
              })}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('verdict')}>See Final Verdict →</button>
          </div>
        )}

        {activeTab === 'verdict' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>The Verdict</h3>
              <p>Our recommendation based on your analysis</p>
            </div>
            <div className="verdict-box">
              <div className="verdict-content">
                <div className="verdict-title">Verdict: Buying Builds Significantly More Wealth</div>
                <ul className="verdict-reasons">
                  <li>True monthly cost is only {formatCurrencyFull(data.trueMonthlyCost - data.currentRent)} more than rent after tax benefits</li>
                  <li>You'll have <strong>{formatCurrency(wealthDifference)}</strong> more wealth in 5 years</li>
                  <li>Tax deductions save you <strong>{formatCurrency(taxBenefits.annualTaxSavings)}/year</strong></li>
                  <li>Your payment is locked while rent increases 3%+ annually</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const CashReservesView = ({ data }) => {
  const { scenarios, tailoredOption, emergencyFundTarget, comfortFundTarget, bestStandard } = data;
  const [activeTab, setActiveTab] = useState('profile');

  const tabs = [
    { id: 'profile', label: 'Your Profile', step: 1 },
    { id: 'tailored', label: 'Tailored Fit', step: 2 },
    { id: 'compare', label: 'Compare Options', step: 3 },
    { id: 'recommendation', label: 'Recommendation', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Suitability Analysis</h2>
        <p className="detail-subtitle">
          Finding your <strong>tailored fit</strong> — not just any suit, but one made for you
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'profile' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Your Financial Measurements</h3>
              <p>Understanding your current financial position</p>
            </div>
            <div className="suitability-intro">
              <div className="suit-analogy">
                <div className="analogy-side">
                  <div className="analogy-title">Off-the-Rack</div>
                  <div className="analogy-desc">Standard 3%, 5%, 10% options work for most people</div>
                </div>
                <div className="analogy-vs">vs</div>
                <div className="analogy-side highlighted">
                  <div className="analogy-title">Custom Tailored</div>
                  <div className="analogy-desc">A down payment sized exactly for your situation</div>
                </div>
              </div>
            </div>
            <div className="financial-profile">
              <div className="profile-grid">
                <div className="profile-item">
                  <div className="profile-label">Available Savings</div>
                  <div className="profile-value">{formatCurrency(data.savings)}</div>
                </div>
                <div className="profile-item">
                  <div className="profile-label">Monthly Expenses</div>
                  <div className="profile-value">{formatCurrency(data.monthlyExpenses)}</div>
                </div>
                <div className="profile-item">
                  <div className="profile-label">Minimum Reserve (3 mo)</div>
                  <div className="profile-value">{formatCurrency(emergencyFundTarget)}</div>
                </div>
                <div className="profile-item">
                  <div className="profile-label">Ideal Reserve (6 mo)</div>
                  <div className="profile-value">{formatCurrency(comfortFundTarget)}</div>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('tailored')}>See Your Tailored Fit →</button>
          </div>
        )}

        {activeTab === 'tailored' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Your Perfect Fit Down Payment</h3>
              <p>Custom calculated for your specific situation</p>
            </div>
            <div className="tailored-recommendation">
              <div className="tailored-header">
                <div className="tailored-badge">CUSTOM TAILORED FOR ALEX</div>
              </div>
              <div className="tailored-content">
                <div className="tailored-main">
                  <div className="tailored-amount">
                    <div className="amount-label">Optimal Down Payment</div>
                    <div className="amount-value">{formatCurrency(tailoredOption.downPayment)}</div>
                    <div className="amount-pct">{formatPercent(tailoredOption.pct * 100)} down</div>
                  </div>
                  <div className="tailored-result">
                    <div className="result-row"><span>Closing Costs</span><span>{formatCurrency(tailoredOption.closingCosts)}</span></div>
                    <div className="result-row highlight"><span>Cash Remaining</span><span>{formatCurrency(tailoredOption.cashRemaining)}</span></div>
                    <div className="result-row"><span>Emergency Reserve</span><span>{tailoredOption.monthsReserve.toFixed(1)} months</span></div>
                    <div className="result-row"><span>Monthly Payment</span><span>{formatCurrencyFull(tailoredOption.piti.total)}</span></div>
                  </div>
                </div>
                <div className="tailored-why">
                  <strong>Why this amount?</strong> This leaves you with exactly 3 months of expenses
                  ({formatCurrency(emergencyFundTarget)}) in reserve — the recommended minimum emergency fund
                  for new homeowners.
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare Standard Options →</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>How Standard Options Compare</h3>
              <p>See how preset down payment options stack up for you</p>
            </div>
            <div className="suitability-cards">
              {scenarios.map((s) => (
                <div key={s.label} className={`suitability-card ${s.fitLevel}`}>
                  <div className="suit-card-header">
                    <div className="suit-card-title">{s.label}</div>
                    <div className={`fit-badge ${s.fitLevel}`}>{s.fitDescription}</div>
                  </div>
                  <div className="suit-score-ring">
                    <svg viewBox="0 0 100 100" className="score-svg">
                      <circle cx="50" cy="50" r="45" className="score-bg" />
                      <circle cx="50" cy="50" r="45" className={`score-fill ${s.fitLevel}`}
                        strokeDasharray={`${s.suitabilityScore * 2.83} 283`} transform="rotate(-90 50 50)" />
                    </svg>
                    <div className="score-value">{s.suitabilityScore}</div>
                    <div className="score-label">Fit Score</div>
                  </div>
                  <div className="suit-card-details">
                    <div className="suit-detail"><span>Down Payment</span><span>{formatCurrency(s.downPayment)}</span></div>
                    <div className="suit-detail"><span>Cash Left</span><span className={s.cashRemaining < 0 ? 'negative' : ''}>{formatCurrency(s.cashRemaining)}</span></div>
                    <div className="suit-detail"><span>Reserve</span><span>{s.monthsReserve.toFixed(1)} months</span></div>
                  </div>
                  <div className="suit-factors">
                    {s.factors.map((f) => (
                      <div key={f.name} className={`factor-row ${f.status}`}>
                        <div className="factor-name">{f.name}</div>
                        <div className="factor-bar"><div className="factor-fill" style={{ width: `${(f.score / f.max) * 100}%` }} /></div>
                        <div className="factor-score">{f.score}/{f.max}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('recommendation')}>See Final Recommendation →</button>
          </div>
        )}

        {activeTab === 'recommendation' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Suitability Recommendation</h3>
              <p>Our final analysis for your situation</p>
            </div>
            <div className="suitability-verdict">
              <div className="verdict-content">
                <div className="verdict-title">Your Best Options</div>
                <div className="rec-options">
                  <div className="rec-option primary">
                    <div className="rec-badge">Custom Tailored</div>
                    <h4>{formatPercent(tailoredOption.pct * 100)} Down ({formatCurrency(tailoredOption.downPayment)})</h4>
                    <p>Leaves you with exactly 3 months of reserves — the recommended minimum for new homeowners.</p>
                  </div>
                  <div className="rec-option secondary">
                    <div className="rec-badge">Best Standard Option</div>
                    <h4>{bestStandard.label}</h4>
                    <p>Scores {bestStandard.suitabilityScore}/100, leaving {formatCurrency(bestStandard.cashRemaining)} ({bestStandard.monthsReserve.toFixed(1)} months) in reserve.</p>
                  </div>
                </div>
                <div className="rec-summary">
                  Based on your savings of <strong>{formatCurrency(data.savings)}</strong> and monthly expenses of
                  <strong> {formatCurrency(data.monthlyExpenses)}</strong>, either option provides adequate reserves
                  while maximizing your purchasing power.
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ClosingCostsView = ({ data }) => {
  const { closingCosts, homePrice, loanAmount, downPayment, totalCashNeeded, savings } = data;
  const shortfall = totalCashNeeded - savings;

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Closing Costs Breakdown</h2>
        <p className="detail-subtitle">
          Itemized costs for a <strong>{formatCurrency(homePrice)}</strong> home with 5% down
        </p>
      </div>

      <div className="closing-costs-summary">
        <div className="summary-card total">
          <div className="summary-label">Total Closing Costs</div>
          <div className="summary-value">{formatCurrency(closingCosts.total)}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Down Payment</div>
          <div className="summary-value">{formatCurrency(downPayment)}</div>
        </div>
        <div className="summary-card highlight">
          <div className="summary-label">Total Cash Needed</div>
          <div className="summary-value">{formatCurrency(totalCashNeeded)}</div>
        </div>
      </div>

      {shortfall > 0 && (
        <div className="shortfall-warning">
                    <div>
            <strong>Cash Shortfall:</strong> You need {formatCurrency(shortfall)} more than your current savings of {formatCurrency(savings)}.
            Consider a lower down payment or gift funds.
          </div>
        </div>
      )}

      <div className="costs-sections">
        {/* Lender Fees */}
        <div className="cost-section">
          <div className="section-header">
            <h4>Lender Fees</h4>
            <span className="section-total">{formatCurrency(closingCosts.lenderFees.total)}</span>
          </div>
          <div className="cost-items">
            <div className="cost-item">
              <span>Origination Fee (1%)</span>
              <span>{formatCurrency(closingCosts.lenderFees.originationFee)}</span>
            </div>
            <div className="cost-item">
              <span>Underwriting Fee</span>
              <span>{formatCurrency(closingCosts.lenderFees.underwritingFee)}</span>
            </div>
            <div className="cost-item">
              <span>Processing Fee</span>
              <span>{formatCurrency(closingCosts.lenderFees.processingFee)}</span>
            </div>
            <div className="cost-item">
              <span>Credit Report</span>
              <span>{formatCurrency(closingCosts.lenderFees.creditReport)}</span>
            </div>
            <div className="cost-item">
              <span>Flood Certification</span>
              <span>{formatCurrency(closingCosts.lenderFees.floodCert)}</span>
            </div>
          </div>
        </div>

        {/* Third Party Fees */}
        <div className="cost-section">
          <div className="section-header">
            <h4>Third Party Fees</h4>
            <span className="section-total">{formatCurrency(closingCosts.thirdPartyFees.total)}</span>
          </div>
          <div className="cost-items">
            <div className="cost-item">
              <span>Appraisal</span>
              <span>{formatCurrency(closingCosts.thirdPartyFees.appraisal)}</span>
            </div>
            <div className="cost-item">
              <span>Title Search</span>
              <span>{formatCurrency(closingCosts.thirdPartyFees.titleSearch)}</span>
            </div>
            <div className="cost-item">
              <span>Title Insurance</span>
              <span>{formatCurrency(closingCosts.thirdPartyFees.titleInsurance)}</span>
            </div>
            <div className="cost-item">
              <span>Settlement/Escrow Fee</span>
              <span>{formatCurrency(closingCosts.thirdPartyFees.settlementFee)}</span>
            </div>
            <div className="cost-item">
              <span>Recording Fees</span>
              <span>{formatCurrency(closingCosts.thirdPartyFees.recordingFees)}</span>
            </div>
            <div className="cost-item">
              <span>Survey</span>
              <span>{formatCurrency(closingCosts.thirdPartyFees.survey)}</span>
            </div>
          </div>
        </div>

        {/* Prepaids */}
        <div className="cost-section">
          <div className="section-header">
            <h4>Prepaid Items</h4>
            <span className="section-total">{formatCurrency(closingCosts.prepaids.total)}</span>
          </div>
          <div className="cost-items">
            <div className="cost-item">
              <span>Prepaid Interest (15 days)</span>
              <span>{formatCurrency(closingCosts.prepaids.prepaidInterest)}</span>
            </div>
            <div className="cost-item">
              <span>Homeowners Insurance (1 year)</span>
              <span>{formatCurrency(closingCosts.prepaids.prepaidInsurance)}</span>
            </div>
            <div className="cost-item">
              <span>Property Taxes (3 months)</span>
              <span>{formatCurrency(closingCosts.prepaids.prepaidTaxes)}</span>
            </div>
          </div>
        </div>

        {/* Escrow Reserves */}
        <div className="cost-section">
          <div className="section-header">
            <h4>Escrow Reserves</h4>
            <span className="section-total">{formatCurrency(closingCosts.escrows.total)}</span>
          </div>
          <div className="cost-items">
            <div className="cost-item">
              <span>Insurance Reserve (2 months)</span>
              <span>{formatCurrency(closingCosts.escrows.escrowInsurance)}</span>
            </div>
            <div className="cost-item">
              <span>Tax Reserve (2 months)</span>
              <span>{formatCurrency(closingCosts.escrows.escrowTaxes)}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="closing-costs-footer">
        <div className="footer-note">
                    <div>
            <strong>Good to know:</strong> Some of these costs may be negotiable or could be covered
            by seller concessions. Ask your loan officer about options to reduce out-of-pocket expenses.
          </div>
        </div>
      </div>
    </div>
  );
};

const CostToWaitingView = ({ data, onUpdateData }) => {
  const {
    homePrice: initialHomePrice,
    currentRent,
    interestRate: initialRate,
    downPaymentPct,
    savings,
    monthlyIncome,
  } = data;

  // Local state for interactive inputs
  const [waitMonths, setWaitMonths] = useState(12);
  const [homeAppreciation, setHomeAppreciation] = useState(data.homeAppreciationRate || 4.0);
  const [rateIncrease, setRateIncrease] = useState(data.rateIncreasePerYear || 0.5);
  const [rentIncrease, setRentIncrease] = useState(data.rentIncreaseRate || 3.0);

  // Calculate costs of waiting
  const calculations = useMemo(() => {
    const waitYears = waitMonths / 12;

    // Future home price
    const futureHomePrice = initialHomePrice * Math.pow(1 + homeAppreciation / 100, waitYears);
    const homePriceIncrease = futureHomePrice - initialHomePrice;

    // Future interest rate
    const futureRate = initialRate + (rateIncrease * waitYears);

    // Down payment difference
    const currentDownPayment = initialHomePrice * (downPaymentPct / 100);
    const futureDownPayment = futureHomePrice * (downPaymentPct / 100);
    const downPaymentIncrease = futureDownPayment - currentDownPayment;

    // Loan amounts
    const currentLoan = initialHomePrice - currentDownPayment;
    const futureLoan = futureHomePrice - futureDownPayment;

    // Monthly payments (P&I only for comparison)
    const calcMonthlyPI = (loan, rate, years = 30) => {
      const monthlyRate = (rate / 100) / 12;
      const numPayments = years * 12;
      return (loan * monthlyRate * Math.pow(1 + monthlyRate, numPayments)) / (Math.pow(1 + monthlyRate, numPayments) - 1);
    };

    const currentPayment = calcMonthlyPI(currentLoan, initialRate);
    const futurePayment = calcMonthlyPI(futureLoan, futureRate);
    const monthlyPaymentIncrease = futurePayment - currentPayment;

    // Rent paid while waiting
    let totalRentPaid = 0;
    let monthlyRent = currentRent;
    for (let m = 0; m < waitMonths; m++) {
      totalRentPaid += monthlyRent;
      if (m > 0 && m % 12 === 0) {
        monthlyRent *= (1 + rentIncrease / 100);
      }
    }

    // Total interest over 30 years
    const currentTotalInterest = (currentPayment * 360) - currentLoan;
    const futureTotalInterest = (futurePayment * 360) - futureLoan;
    const interestIncrease = futureTotalInterest - currentTotalInterest;

    // Lost equity building
    const equityBuiltIfBoughtNow = calcEquityBuilt(currentLoan, initialRate, waitMonths);

    // Total cost of waiting
    const totalCostOfWaiting = downPaymentIncrease + totalRentPaid + interestIncrease;

    // Monthly cost equivalent
    const monthlyCostOfWaiting = totalCostOfWaiting / waitMonths;

    return {
      waitMonths,
      waitYears,
      currentHomePrice: initialHomePrice,
      futureHomePrice,
      homePriceIncrease,
      currentRate: initialRate,
      futureRate,
      currentDownPayment,
      futureDownPayment,
      downPaymentIncrease,
      currentLoan,
      futureLoan,
      currentPayment,
      futurePayment,
      monthlyPaymentIncrease,
      totalRentPaid,
      currentTotalInterest,
      futureTotalInterest,
      interestIncrease,
      equityBuiltIfBoughtNow,
      totalCostOfWaiting,
      monthlyCostOfWaiting,
    };
  }, [waitMonths, homeAppreciation, rateIncrease, rentIncrease, initialHomePrice, initialRate, downPaymentPct, currentRent]);

  // Helper to calculate equity built over time
  function calcEquityBuilt(loan, rate, months) {
    const monthlyRate = (rate / 100) / 12;
    const payment = (loan * monthlyRate * Math.pow(1 + monthlyRate, 360)) / (Math.pow(1 + monthlyRate, 360) - 1);
    let balance = loan;
    let totalPrincipal = 0;
    for (let m = 0; m < months; m++) {
      const interest = balance * monthlyRate;
      const principal = payment - interest;
      totalPrincipal += principal;
      balance -= principal;
    }
    return totalPrincipal;
  }

  const [activeTab, setActiveTab] = useState('settings');

  const tabs = [
    { id: 'settings', label: 'Settings', step: 1 },
    { id: 'compare', label: 'Compare', step: 2 },
    { id: 'breakdown', label: 'Cost Breakdown', step: 3 },
    { id: 'summary', label: 'Summary', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view cost-waiting-view">
      <div className="detail-header">
        <h2>Cost of Waiting</h2>
        <p className="detail-subtitle">
          See what delaying your purchase could really cost you
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'settings' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Configure Your Scenario</h3>
              <p>Adjust the assumptions to see how waiting affects you</p>
            </div>
            <div className="waiting-inputs">
              <div className="input-section">
                <h4>How Long Would You Wait?</h4>
                <div className="wait-time-selector">
                  {[6, 12, 18, 24, 36].map(months => (
                    <button key={months} className={`wait-btn ${waitMonths === months ? 'active' : ''}`}
                      onClick={() => setWaitMonths(months)}>
                      {months < 12 ? `${months} mo` : `${months / 12} yr${months > 12 ? 's' : ''}`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="assumptions-grid">
                <div className="assumption-field">
                  <label>Home Price Growth</label>
                  <div className="input-with-suffix small">
                    <input type="number" step="0.5" value={homeAppreciation}
                      onChange={(e) => setHomeAppreciation(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%/yr</span>
                  </div>
                </div>
                <div className="assumption-field">
                  <label>Interest Rate Increase</label>
                  <div className="input-with-suffix small">
                    <input type="number" step="0.25" value={rateIncrease}
                      onChange={(e) => setRateIncrease(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%/yr</span>
                  </div>
                </div>
                <div className="assumption-field">
                  <label>Rent Increase</label>
                  <div className="input-with-suffix small">
                    <input type="number" step="0.5" value={rentIncrease}
                      onChange={(e) => setRentIncrease(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%/yr</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="cost-impact-hero">
              <div className="impact-label">Total Cost of Waiting {calculations.waitMonths} Months</div>
              <div className="impact-amount">{formatCurrency(calculations.totalCostOfWaiting)}</div>
              <div className="impact-monthly">That's {formatCurrency(calculations.monthlyCostOfWaiting)}/month you're losing</div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare Now vs Later →</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Buy Now vs. Buy Later</h3>
              <p>See the detailed comparison after {calculations.waitMonths} months</p>
            </div>
            <div className="waiting-comparison">
              <div className="comparison-column buy-now">
                <div className="column-header">Buy Now</div>
                <div className="comparison-items">
                  <div className="comparison-item"><span className="item-label">Home Price</span><span className="item-value">{formatCurrency(calculations.currentHomePrice)}</span></div>
                  <div className="comparison-item"><span className="item-label">Interest Rate</span><span className="item-value">{calculations.currentRate.toFixed(3)}%</span></div>
                  <div className="comparison-item"><span className="item-label">Down Payment ({downPaymentPct}%)</span><span className="item-value">{formatCurrency(calculations.currentDownPayment)}</span></div>
                  <div className="comparison-item"><span className="item-label">Loan Amount</span><span className="item-value">{formatCurrency(calculations.currentLoan)}</span></div>
                  <div className="comparison-item highlight"><span className="item-label">Monthly P&I</span><span className="item-value">{formatCurrencyFull(calculations.currentPayment)}</span></div>
                  <div className="comparison-item"><span className="item-label">Total Interest (30yr)</span><span className="item-value">{formatCurrency(calculations.currentTotalInterest)}</span></div>
                </div>
              </div>
              <div className="comparison-vs"><div className="vs-circle">VS</div><div className="vs-time">After {calculations.waitMonths} months</div></div>
              <div className="comparison-column buy-later">
                <div className="column-header">Buy Later</div>
                <div className="comparison-items">
                  <div className="comparison-item"><span className="item-label">Home Price</span><span className="item-value negative">{formatCurrency(calculations.futureHomePrice)}<span className="change">+{formatCurrency(calculations.homePriceIncrease)}</span></span></div>
                  <div className="comparison-item"><span className="item-label">Interest Rate</span><span className="item-value negative">{calculations.futureRate.toFixed(3)}%<span className="change">+{(calculations.futureRate - calculations.currentRate).toFixed(3)}%</span></span></div>
                  <div className="comparison-item"><span className="item-label">Down Payment ({downPaymentPct}%)</span><span className="item-value negative">{formatCurrency(calculations.futureDownPayment)}<span className="change">+{formatCurrency(calculations.downPaymentIncrease)}</span></span></div>
                  <div className="comparison-item"><span className="item-label">Loan Amount</span><span className="item-value">{formatCurrency(calculations.futureLoan)}</span></div>
                  <div className="comparison-item highlight"><span className="item-label">Monthly P&I</span><span className="item-value negative">{formatCurrencyFull(calculations.futurePayment)}<span className="change">+{formatCurrencyFull(calculations.monthlyPaymentIncrease)}</span></span></div>
                  <div className="comparison-item"><span className="item-label">Total Interest (30yr)</span><span className="item-value negative">{formatCurrency(calculations.futureTotalInterest)}<span className="change">+{formatCurrency(calculations.interestIncrease)}</span></span></div>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('breakdown')}>See Cost Breakdown →</button>
          </div>
        )}

        {activeTab === 'breakdown' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Where the Cost Comes From</h3>
              <p>Breaking down the total cost of waiting</p>
            </div>
            <div className="cost-breakdown">
              <div className="breakdown-bars">
                <div className="breakdown-item">
                  <div className="breakdown-header">
                    <span className="breakdown-label">Extra Down Payment Needed</span>
                    <span className="breakdown-value">{formatCurrency(calculations.downPaymentIncrease)}</span>
                  </div>
                  <div className="breakdown-bar">
                    <div className="breakdown-fill rent" style={{ width: `${Math.min(100, (calculations.downPaymentIncrease / calculations.totalCostOfWaiting) * 100)}%` }} />
                  </div>
                </div>
                <div className="breakdown-item">
                  <div className="breakdown-header">
                    <span className="breakdown-label">Rent Paid While Waiting</span>
                    <span className="breakdown-value">{formatCurrency(calculations.totalRentPaid)}</span>
                  </div>
                  <div className="breakdown-bar">
                    <div className="breakdown-fill interest" style={{ width: `${Math.min(100, (calculations.totalRentPaid / calculations.totalCostOfWaiting) * 100)}%` }} />
                  </div>
                </div>
                <div className="breakdown-item">
                  <div className="breakdown-header">
                    <span className="breakdown-label">Additional Lifetime Interest</span>
                    <span className="breakdown-value">{formatCurrency(calculations.interestIncrease)}</span>
                  </div>
                  <div className="breakdown-bar">
                    <div className="breakdown-fill extra" style={{ width: `${Math.min(100, (calculations.interestIncrease / calculations.totalCostOfWaiting) * 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>
            <div className="lost-opportunity">
              <h4>Plus: Opportunity Cost</h4>
              <p>
                If you bought today, you'd build <strong>{formatCurrency(calculations.equityBuiltIfBoughtNow)}</strong> in
                equity over the next {calculations.waitMonths} months through principal payments alone — not counting any home appreciation.
              </p>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('summary')}>See Summary →</button>
          </div>
        )}

        {activeTab === 'summary' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>The Bottom Line</h3>
              <p>Summary of what waiting will cost you</p>
            </div>
            <div className="cost-impact-hero">
              <div className="impact-label">Total Cost of Waiting {calculations.waitMonths} Months</div>
              <div className="impact-amount">{formatCurrency(calculations.totalCostOfWaiting)}</div>
              <div className="impact-monthly">That's {formatCurrency(calculations.monthlyCostOfWaiting)}/month you're losing</div>
            </div>
            <div className="waiting-verdict">
              <div className="verdict-title">Key Takeaways</div>
              <ul className="verdict-list">
                <li>Every month you wait costs approximately <strong>{formatCurrency(calculations.monthlyCostOfWaiting)}</strong></li>
                <li>You'll need <strong>{formatCurrency(calculations.downPaymentIncrease)} more</strong> for your down payment</li>
                <li>Your monthly payment will be <strong>{formatCurrencyFull(calculations.monthlyPaymentIncrease)} higher</strong></li>
                <li>You'll pay <strong>{formatCurrency(calculations.interestIncrease)}</strong> more in lifetime interest</li>
              </ul>
              {calculations.totalCostOfWaiting > savings * 0.5 && (
                <div className="verdict-warning">
                  The cost of waiting {calculations.waitMonths} months exceeds 50% of your current savings.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const PrepayOrInvestView = ({ data }) => {
  const {
    loanAmount: initialLoanAmount,
    interestRate: initialRate,
    termYears: initialTerm,
    monthlyExtraCash: initialExtra,
    estimatedMarketReturn: initialReturn,
    currentEquity,
    homePrice,
  } = data;

  // Local state for interactive inputs
  const [mortgageBalance, setMortgageBalance] = useState(initialLoanAmount);
  const [mortgageRate, setMortgageRate] = useState(initialRate);
  const [remainingYears, setRemainingYears] = useState(initialTerm);
  const [monthlyExtra, setMonthlyExtra] = useState(initialExtra);
  const [marketReturn, setMarketReturn] = useState(initialReturn);
  const [showAnalysis, setShowAnalysis] = useState(false);

  // Calculate both strategies
  const results = useMemo(() => {
    const monthlyRate = mortgageRate / 100 / 12;
    const totalMonths = remainingYears * 12;

    // Calculate standard monthly payment
    const standardPayment = (mortgageBalance * monthlyRate * Math.pow(1 + monthlyRate, totalMonths)) /
      (Math.pow(1 + monthlyRate, totalMonths) - 1);

    // Strategy 1: Prepay mortgage
    let prepayBalance = mortgageBalance;
    let prepayMonths = 0;
    let prepayTotalInterest = 0;
    let prepayCash = 0;

    while (prepayBalance > 0 && prepayMonths < 360) {
      const interestPayment = prepayBalance * monthlyRate;
      const principalPayment = Math.min(standardPayment - interestPayment + monthlyExtra, prepayBalance);
      prepayTotalInterest += interestPayment;
      prepayBalance -= principalPayment;
      prepayMonths++;

      // Once mortgage is paid off, invest the full amount
      if (prepayBalance <= 0) {
        const remainingMonths = totalMonths - prepayMonths;
        const monthlyInvestment = standardPayment + monthlyExtra;
        // Future value of monthly investments
        const monthlyMarketRate = marketReturn / 100 / 12;
        prepayCash = monthlyInvestment * ((Math.pow(1 + monthlyMarketRate, remainingMonths) - 1) / monthlyMarketRate);
      }
    }

    // Strategy 2: Invest extra in market
    let investBalance = mortgageBalance;
    let investTotalInterest = 0;
    let investmentValue = 0;
    const monthlyMarketRate = marketReturn / 100 / 12;

    for (let m = 0; m < totalMonths && investBalance > 0; m++) {
      const interestPayment = investBalance * monthlyMarketRate;
      const principalPayment = Math.min(standardPayment - investBalance * monthlyRate, investBalance);
      investTotalInterest += investBalance * monthlyRate;
      investBalance = Math.max(0, investBalance - principalPayment);

      // Monthly investment grows
      investmentValue = (investmentValue + monthlyExtra) * (1 + monthlyMarketRate);
    }

    // Calculate final positions at end of original term
    const prepayEquity = homePrice; // Own home outright
    const prepayTotalWealth = prepayEquity + prepayCash;
    const prepayMortgageFreeDate = prepayMonths;

    const investEquity = homePrice - investBalance; // May still have mortgage
    const investTotalWealth = investEquity + investmentValue;
    const investMortgageFreeDate = totalMonths;

    // Determine winner
    const investingWinsBy = investTotalWealth - prepayTotalWealth;
    const winner = investingWinsBy > 0 ? 'invest' : 'prepay';

    // Interest saved by prepaying
    const standardTotalInterest = (standardPayment * totalMonths) - mortgageBalance;
    const interestSaved = standardTotalInterest - prepayTotalInterest;

    // Year-by-year breakdown for chart
    const yearlyBreakdown = [];
    let pBalance = mortgageBalance;
    let pCash = 0;
    let iBalance = mortgageBalance;
    let iCash = 0;
    let pPaidOff = false;

    for (let year = 1; year <= remainingYears; year++) {
      for (let m = 0; m < 12; m++) {
        // Prepay strategy
        if (pBalance > 0) {
          const pInterest = pBalance * monthlyRate;
          const pPrincipal = Math.min(standardPayment - pInterest + monthlyExtra, pBalance);
          pBalance = Math.max(0, pBalance - pPrincipal);
        } else {
          pCash = (pCash + standardPayment + monthlyExtra) * (1 + monthlyMarketRate);
          pPaidOff = true;
        }

        // Invest strategy
        if (iBalance > 0) {
          const iInterest = iBalance * monthlyRate;
          const iPrincipal = standardPayment - iInterest;
          iBalance = Math.max(0, iBalance - iPrincipal);
        }
        iCash = (iCash + monthlyExtra) * (1 + monthlyMarketRate);
      }

      yearlyBreakdown.push({
        year,
        prepay: {
          equity: homePrice - pBalance,
          cash: pCash,
          total: (homePrice - pBalance) + pCash,
          mortgagePaidOff: pPaidOff,
        },
        invest: {
          equity: homePrice - iBalance,
          cash: iCash,
          total: (homePrice - iBalance) + iCash,
          mortgagePaidOff: iBalance <= 0,
        },
      });
    }

    return {
      standardPayment,
      prepay: {
        monthsToPayoff: prepayMonths,
        yearsToPayoff: (prepayMonths / 12).toFixed(1),
        totalInterest: prepayTotalInterest,
        interestSaved,
        finalCash: prepayCash,
        finalEquity: prepayEquity,
        totalWealth: prepayTotalWealth,
      },
      invest: {
        monthsToPayoff: totalMonths,
        yearsToPayoff: remainingYears,
        totalInterest: investTotalInterest,
        finalCash: investmentValue,
        finalEquity: investEquity,
        totalWealth: investTotalWealth,
      },
      winner,
      difference: Math.abs(investingWinsBy),
      investingWinsBy,
      yearlyBreakdown,
    };
  }, [mortgageBalance, mortgageRate, remainingYears, monthlyExtra, marketReturn, homePrice]);

  const [activeTab, setActiveTab] = useState('settings');

  const tabs = [
    { id: 'settings', label: 'Settings', step: 1 },
    { id: 'compare', label: 'Compare Strategies', step: 2 },
    { id: 'timeline', label: 'Timeline', step: 3 },
    { id: 'analysis', label: 'Analysis', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view prepay-invest-view">
      <div className="detail-header">
        <h2>Prepay or Invest?</h2>
        <p className="detail-subtitle">
          Compare guaranteed debt reduction vs. potential market growth
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'settings' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Configure Your Scenario</h3>
              <p>Adjust your mortgage and investment assumptions</p>
            </div>
            <div className="prepay-inputs">
              <div className="inputs-row">
                <div className="input-group">
                  <label>Mortgage Balance</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input type="number" value={mortgageBalance} onChange={(e) => setMortgageBalance(parseFloat(e.target.value) || 0)} />
                  </div>
                </div>
                <div className="input-group">
                  <label>Mortgage Rate</label>
                  <div className="input-with-suffix">
                    <input type="number" step="0.125" value={mortgageRate} onChange={(e) => setMortgageRate(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%</span>
                  </div>
                </div>
                <div className="input-group">
                  <label>Remaining Years</label>
                  <div className="input-with-suffix">
                    <input type="number" value={remainingYears} onChange={(e) => setRemainingYears(parseInt(e.target.value) || 1)} />
                    <span className="suffix">yrs</span>
                  </div>
                </div>
              </div>
              <div className="inputs-row">
                <div className="input-group">
                  <label>Monthly Extra Cash</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input type="number" value={monthlyExtra} onChange={(e) => setMonthlyExtra(parseFloat(e.target.value) || 0)} />
                  </div>
                </div>
                <div className="input-group">
                  <label>Estimated After-Tax Return</label>
                  <div className="input-with-suffix">
                    <input type="number" step="0.5" value={marketReturn} onChange={(e) => setMarketReturn(parseFloat(e.target.value) || 0)} />
                    <span className="suffix">%</span>
                  </div>
                </div>
              </div>
            </div>
            <div className={`winner-banner ${results.winner}`}>
              <div className="winner-label">{results.winner === 'invest' ? 'Investing Wins By' : 'Prepaying Wins By'}</div>
              <div className="winner-amount">{results.investingWinsBy >= 0 ? '+' : ''}{formatCurrency(results.difference)}</div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare Strategies →</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Strategy Comparison</h3>
              <p>Compare prepaying mortgage vs investing in the market</p>
            </div>
            <div className="strategy-comparison">
              <div className={`strategy-card ${results.winner === 'prepay' ? 'winner' : ''}`}>
                <div className="strategy-header">
                  <span className="strategy-name">Prepay Strategy</span>
                  {results.winner === 'prepay' && <span className="winner-badge">Winner</span>}
                </div>
                <div className="strategy-subtitle">Put extra toward mortgage</div>
                <div className="strategy-metrics">
                  <div className="metric"><span className="metric-label">Mortgage-Free In</span><span className="metric-value highlight">{results.prepay.yearsToPayoff} years</span></div>
                  <div className="metric"><span className="metric-label">Interest Saved</span><span className="metric-value positive">{formatCurrency(results.prepay.interestSaved)}</span></div>
                  <div className="metric"><span className="metric-label">Final Home Equity</span><span className="metric-value">{formatCurrency(results.prepay.finalEquity)}</span></div>
                  <div className="metric"><span className="metric-label">Cash/Investments</span><span className="metric-value">{formatCurrency(results.prepay.finalCash)}</span></div>
                  <div className="metric total"><span className="metric-label">Total Wealth</span><span className="metric-value">{formatCurrency(results.prepay.totalWealth)}</span></div>
                </div>
              </div>
              <div className={`strategy-card ${results.winner === 'invest' ? 'winner' : ''}`}>
                <div className="strategy-header">
                  <span className="strategy-name">Invest Strategy</span>
                  {results.winner === 'invest' && <span className="winner-badge">Winner</span>}
                </div>
                <div className="strategy-subtitle">Invest extra in the market</div>
                <div className="strategy-metrics">
                  <div className="metric"><span className="metric-label">Mortgage-Free In</span><span className="metric-value">{results.invest.yearsToPayoff} years</span></div>
                  <div className="metric"><span className="metric-label">Investment Growth</span><span className="metric-value positive">{formatCurrency(results.invest.finalCash)}</span></div>
                  <div className="metric"><span className="metric-label">Final Home Equity</span><span className="metric-value">{formatCurrency(results.invest.finalEquity)}</span></div>
                  <div className="metric"><span className="metric-label">Cash/Investments</span><span className="metric-value">{formatCurrency(results.invest.finalCash)}</span></div>
                  <div className="metric total"><span className="metric-label">Total Wealth</span><span className="metric-value">{formatCurrency(results.invest.totalWealth)}</span></div>
                </div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('timeline')}>See Timeline →</button>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Wealth Accumulation Timeline</h3>
              <p>Track how your wealth grows over time with each strategy</p>
            </div>
            <div className="yearly-breakdown">
              <div className="breakdown-table-wrapper">
                <table className="breakdown-table">
                  <thead>
                    <tr><th>Year</th><th>Prepay Total</th><th>Invest Total</th><th>Difference</th></tr>
                  </thead>
                  <tbody>
                    {results.yearlyBreakdown.filter((_, i) => i % 5 === 4 || i === 0 || i === results.yearlyBreakdown.length - 1).map(row => (
                      <tr key={row.year}>
                        <td>Year {row.year}</td>
                        <td>{formatCurrency(row.prepay.total)}{row.prepay.mortgagePaidOff && <span className="paid-off-badge">Paid Off</span>}</td>
                        <td>{formatCurrency(row.invest.total)}</td>
                        <td className={row.invest.total > row.prepay.total ? 'positive' : 'negative'}>
                          {row.invest.total > row.prepay.total ? '+' : ''}{formatCurrency(row.invest.total - row.prepay.total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('analysis')}>See Analysis →</button>
          </div>
        )}

        {activeTab === 'analysis' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>AI Underwriter Analysis</h3>
              <p>Detailed analysis and recommendation</p>
            </div>
            <div className="ai-analysis-content">
              <div className="analysis-body">
                <p>
                  <strong>Summary:</strong> With a {mortgageRate}% mortgage rate and {marketReturn}% expected market return,
                  {results.winner === 'invest'
                    ? ` investing wins by ${formatCurrency(results.difference)} over the life of the loan.`
                    : ` prepaying wins by ${formatCurrency(results.difference)} over the life of the loan.`
                  }
                </p>
                <p>
                  <strong>The Math:</strong> Your mortgage interest rate of {mortgageRate}% represents a guaranteed
                  "return" when you prepay. When your mortgage rate is {mortgageRate < marketReturn ? 'lower' : 'higher'} than expected market returns,
                  {mortgageRate < marketReturn ? ' mathematically, investing tends to come out ahead.' : ' mathematically, prepaying tends to be the better choice.'}
                </p>
                <div className="risk-considerations">
                  <h5>Risk Considerations:</h5>
                  <ul>
                    <li>Prepaying provides a <em>guaranteed</em> return equal to your mortgage rate</li>
                    <li>Market returns are <em>variable</em> and could be higher or lower than {marketReturn}%</li>
                    <li>Prepaying builds equity faster, providing financial security</li>
                    <li>Investing maintains liquidity (you can access the funds if needed)</li>
                  </ul>
                </div>
                <p>
                  <strong>Recommendation:</strong>
                  {results.winner === 'invest' && results.difference > 50000
                    ? ' Given the significant difference, investing likely makes sense if you can handle market volatility.'
                    : results.winner === 'prepay' && results.difference > 50000
                    ? ' Given the significant difference, prepaying your mortgage is likely the better choice.'
                    : ' The strategies are relatively close. Consider your risk tolerance and whether you value the peace of mind of being debt-free.'
                  }
                </p>
              </div>
            </div>
            <div className="prepay-verdict">
              <strong>Key Insight:</strong> The breakeven point is when your mortgage rate equals your after-tax investment return.
              At {mortgageRate}% mortgage rate and {marketReturn}% expected return,
              {mortgageRate < marketReturn
                ? ` the ${(marketReturn - mortgageRate).toFixed(2)}% spread favors investing.`
                : mortgageRate > marketReturn
                ? ` the ${(mortgageRate - marketReturn).toFixed(2)}% spread favors prepaying.`
                : ' the rates are equal — choose based on your preference for guaranteed vs. potential returns.'
              }
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ClientDataView = ({ data, onUpdateProfile, onUpdateMarket, onUpdateProperty, stateData }) => {
  const { profile, market, property, locationRates, effectiveRates, effectiveInterestRate } = data;

  // Local state for tab navigation and debt editing
  const [activeTab, setActiveTab] = useState('borrower');
  const [newDebtName, setNewDebtName] = useState('');
  const [newDebtAmount, setNewDebtAmount] = useState('');

  const handleAddDebt = () => {
    if (newDebtName && newDebtAmount) {
      const currentDebts = profile.debtBreakdown || [];
      const updatedDebts = [...currentDebts, { name: newDebtName, amount: parseFloat(newDebtAmount) }];
      const totalDebts = updatedDebts.reduce((sum, d) => sum + d.amount, 0);
      onUpdateProfile({
        debtBreakdown: updatedDebts,
        monthlyDebts: totalDebts,
      });
      setNewDebtName('');
      setNewDebtAmount('');
    }
  };

  const handleRemoveDebt = (index) => {
    const currentDebts = profile.debtBreakdown || [];
    const updatedDebts = currentDebts.filter((_, i) => i !== index);
    const totalDebts = updatedDebts.reduce((sum, d) => sum + d.amount, 0);
    onUpdateProfile({
      debtBreakdown: updatedDebts,
      monthlyDebts: totalDebts,
    });
  };

  const counties = stateData[property.state]?.counties || {};

  // Calculate some derived values for tab badges
  const loanAmount = property.homePrice * (1 - property.downPaymentPct / 100);
  const monthlyPI = useMemo(() => {
    const r = effectiveInterestRate / 100 / 12;
    const n = market.termYears * 12;
    if (r === 0) return loanAmount / n;
    return loanAmount * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
  }, [loanAmount, effectiveInterestRate, market.termYears]);

  const tabs = [
    { id: 'borrower', label: 'Borrower', icon: 'user', description: 'Profile & Income' },
    { id: 'property', label: 'Property', icon: 'home', description: 'Location & Details' },
    { id: 'loan', label: 'Loan', icon: 'percent', description: 'Rates & Terms' },
    { id: 'budget', label: 'Budget', icon: 'wallet', description: 'Monthly Expenses' },
    { id: 'scenarios', label: 'Scenarios', icon: 'chart', description: 'Price Options' },
  ];

  // Calculate DTI for display
  const estimatedPITI = monthlyPI + (property.homePrice * effectiveRates.taxRate / 12) + (property.homePrice * effectiveRates.insuranceRate / 12);
  const frontEndDTI = ((estimatedPITI / (profile.annualIncome / 12)) * 100).toFixed(1);

  return (
    <div className="calculator-detail client-data-view tabbed-view">
      {/* Tab Navigation */}
      <div className="client-data-tabs-wrapper">
        <div className="client-data-tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`client-data-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <div className="tab-icon">
                {tab.icon === 'user' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                  </svg>
                )}
                {tab.icon === 'home' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                  </svg>
                )}
                {tab.icon === 'percent' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="19" y1="5" x2="5" y2="19"/>
                    <circle cx="6.5" cy="6.5" r="2.5"/>
                    <circle cx="17.5" cy="17.5" r="2.5"/>
                  </svg>
                )}
                {tab.icon === 'wallet' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
                    <line x1="1" y1="10" x2="23" y2="10"/>
                  </svg>
                )}
                {tab.icon === 'chart' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="20" x2="18" y2="10"/>
                    <line x1="12" y1="20" x2="12" y2="4"/>
                    <line x1="6" y1="20" x2="6" y2="14"/>
                  </svg>
                )}
              </div>
              <div className="tab-text">
                <span className="tab-label">{tab.label}</span>
                <span className="tab-description">{tab.description}</span>
              </div>
              {activeTab === tab.id && <div className="tab-active-indicator" />}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="client-data-tab-content">
        {/* BORROWER TAB */}
        {activeTab === 'borrower' && (
          <div className="tab-panel borrower-panel">
            <div className="panel-section">
              <h3 className="panel-section-title">Personal Information</h3>
              <div className="data-grid">
                <div className="data-field">
                  <label>Name</label>
                  <input
                    type="text"
                    value={profile.name}
                    onChange={(e) => onUpdateProfile({ name: e.target.value })}
                    placeholder="Client name"
                  />
                </div>
                <div className="data-field">
                  <label>Age</label>
                  <input
                    type="number"
                    value={profile.age}
                    onChange={(e) => onUpdateProfile({ age: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">Income & Assets</h3>
              <div className="data-grid">
                <div className="data-field">
                  <label>Annual Income</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={profile.annualIncome}
                      onChange={(e) => onUpdateProfile({ annualIncome: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <span className="field-note">{formatCurrency(profile.annualIncome / 12)}/month</span>
                </div>
                <div className="data-field">
                  <label>Current Savings</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={profile.savings}
                      onChange={(e) => onUpdateProfile({ savings: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="data-field">
                  <label>Current Rent</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={profile.currentRent}
                      onChange={(e) => onUpdateProfile({ currentRent: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <span className="field-note">per month</span>
                </div>
              </div>
            </div>

            <div className="panel-section credit-section">
              <h3 className="panel-section-title">Credit Score</h3>
              <div className="credit-score-control">
                <div className="credit-score-display">
                  <span className={`credit-score-value ${profile.creditScore >= 740 ? 'excellent' : profile.creditScore >= 700 ? 'good' : profile.creditScore >= 650 ? 'fair' : 'poor'}`}>
                    {profile.creditScore}
                  </span>
                  <span className="credit-score-label">
                    {profile.creditScore >= 740 ? 'Excellent' : profile.creditScore >= 700 ? 'Good' : profile.creditScore >= 650 ? 'Fair' : 'Poor'}
                  </span>
                </div>
                <input
                  type="range"
                  min="500"
                  max="850"
                  value={profile.creditScore}
                  onChange={(e) => onUpdateProfile({ creditScore: parseInt(e.target.value) })}
                  className="credit-slider"
                />
                <div className="credit-scale">
                  <span>500</span>
                  <span>620</span>
                  <span>680</span>
                  <span>740</span>
                  <span>850</span>
                </div>
              </div>
              <div className="credit-impact-note">
                Higher credit scores qualify for better rates and lower PMI
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">
                Monthly Debts
                <span className="section-badge">{formatCurrency(profile.monthlyDebts)}/mo</span>
              </h3>
              <div className="debt-list-modern">
                {(profile.debtBreakdown || []).length === 0 && (
                  <div className="no-debts">No monthly debts added</div>
                )}
                {(profile.debtBreakdown || []).map((debt, index) => (
                  <div key={index} className="debt-item-modern">
                    <div className="debt-info">
                      <span className="debt-name">{debt.name}</span>
                      <span className="debt-amount">{formatCurrency(debt.amount)}/mo</span>
                    </div>
                    <button className="debt-remove-btn" onClick={() => handleRemoveDebt(index)}>
                      &times;
                    </button>
                  </div>
                ))}
              </div>
              <div className="add-debt-row">
                <input
                  type="text"
                  placeholder="Debt name"
                  value={newDebtName}
                  onChange={(e) => setNewDebtName(e.target.value)}
                />
                <div className="input-with-prefix compact">
                  <span className="prefix">$</span>
                  <input
                    type="number"
                    placeholder="0"
                    value={newDebtAmount}
                    onChange={(e) => setNewDebtAmount(e.target.value)}
                  />
                </div>
                <button className="add-debt-btn-modern" onClick={handleAddDebt}>Add</button>
              </div>
            </div>
          </div>
        )}

        {/* PROPERTY TAB */}
        {activeTab === 'property' && (
          <div className="tab-panel property-panel">
            <div className="panel-section">
              <h3 className="panel-section-title">Location</h3>
              <div className="data-grid">
                <div className="data-field">
                  <label>State</label>
                  <select
                    value={property.state}
                    onChange={(e) => onUpdateProperty({ state: e.target.value, county: '' })}
                  >
                    {Object.entries(stateData).map(([code, state]) => (
                      <option key={code} value={code}>{state.name}</option>
                    ))}
                  </select>
                </div>
                <div className="data-field">
                  <label>County</label>
                  <select
                    value={property.county}
                    onChange={(e) => onUpdateProperty({ county: e.target.value })}
                  >
                    <option value="">State Average</option>
                    {Object.keys(counties).map(county => (
                      <option key={county} value={county}>{county}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">Property Type</h3>
              <div className="property-type-selector">
                {[
                  { value: 'single_family', label: 'Single Family' },
                  { value: 'condo', label: 'Condo' },
                  { value: 'townhouse', label: 'Townhouse' },
                  { value: 'multi_family', label: 'Multi-Family' },
                ].map(type => (
                  <button
                    key={type.value}
                    className={`property-type-btn ${property.propertyType === type.value ? 'active' : ''}`}
                    onClick={() => onUpdateProperty({ propertyType: type.value })}
                  >
                    {type.label}
                  </button>
                ))}
              </div>
              <div className="data-field inline-field">
                <label>HOA Fees (if any)</label>
                <div className="input-with-prefix compact">
                  <span className="prefix">$</span>
                  <input
                    type="number"
                    value={property.hoaMonthly}
                    onChange={(e) => onUpdateProperty({ hoaMonthly: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <span className="field-note">/month</span>
              </div>
            </div>

            <div className="panel-section taxes-insurance-section">
              <h3 className="panel-section-title">
                Taxes & Insurance
                <span className="auto-badge">Auto-calculated</span>
              </h3>
              <p className="location-note">
                Based on {property.county || 'state average'} in {stateData[property.state]?.name || property.state}
              </p>

              <div className="tax-insurance-cards">
                <div className="ti-card">
                  <div className="ti-header">
                    <span className="ti-label">Property Tax</span>
                    <label className="override-switch">
                      <input
                        type="checkbox"
                        checked={property.taxRateOverride !== null}
                        onChange={(e) => onUpdateProperty({
                          taxRateOverride: e.target.checked ? effectiveRates.taxRate : null
                        })}
                      />
                      <span className="switch-slider"></span>
                      <span className="switch-label">Override</span>
                    </label>
                  </div>
                  <div className="ti-value">
                    {property.taxRateOverride !== null ? (
                      <div className="input-with-suffix compact">
                        <input
                          type="number"
                          step="0.01"
                          value={(property.taxRateOverride * 100).toFixed(2)}
                          onChange={(e) => onUpdateProperty({ taxRateOverride: parseFloat(e.target.value) / 100 })}
                        />
                        <span className="suffix">%</span>
                      </div>
                    ) : (
                      <span className="auto-value">{(locationRates.taxRate * 100).toFixed(2)}%</span>
                    )}
                  </div>
                  <div className="ti-monthly">
                    {formatCurrency((property.homePrice * effectiveRates.taxRate) / 12)}/mo
                  </div>
                </div>

                <div className="ti-card">
                  <div className="ti-header">
                    <span className="ti-label">Insurance</span>
                    <label className="override-switch">
                      <input
                        type="checkbox"
                        checked={property.insuranceRateOverride !== null}
                        onChange={(e) => onUpdateProperty({
                          insuranceRateOverride: e.target.checked ? effectiveRates.insuranceRate : null
                        })}
                      />
                      <span className="switch-slider"></span>
                      <span className="switch-label">Override</span>
                    </label>
                  </div>
                  <div className="ti-value">
                    {property.insuranceRateOverride !== null ? (
                      <div className="input-with-suffix compact">
                        <input
                          type="number"
                          step="0.01"
                          value={(property.insuranceRateOverride * 100).toFixed(2)}
                          onChange={(e) => onUpdateProperty({ insuranceRateOverride: parseFloat(e.target.value) / 100 })}
                        />
                        <span className="suffix">%</span>
                      </div>
                    ) : (
                      <span className="auto-value">{(locationRates.insuranceRate * 100).toFixed(2)}%</span>
                    )}
                  </div>
                  <div className="ti-monthly">
                    {formatCurrency((property.homePrice * effectiveRates.insuranceRate) / 12)}/mo
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* LOAN TAB */}
        {activeTab === 'loan' && (
          <div className="tab-panel loan-panel">
            {/* Purchase & Down Payment */}
            <div className="panel-section">
              <h3 className="panel-section-title">Purchase Details</h3>
              <div className="data-grid two-col">
                <div className="data-field">
                  <label>Home Price</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={property.homePrice}
                      onChange={(e) => onUpdateProperty({ homePrice: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="data-field">
                  <label>Down Payment</label>
                  <div className="down-payment-control">
                    <div className="input-with-suffix">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.5"
                        value={property.downPaymentPct}
                        onChange={(e) => onUpdateProperty({ downPaymentPct: parseFloat(e.target.value) || 0 })}
                      />
                      <span className="suffix">%</span>
                    </div>
                    <span className="down-amount">{formatCurrency(property.homePrice * property.downPaymentPct / 100)}</span>
                  </div>
                </div>
              </div>
              <div className="down-payment-presets">
                {[3, 3.5, 5, 10, 20].map(pct => (
                  <button
                    key={pct}
                    className={`preset-btn ${property.downPaymentPct === pct ? 'active' : ''}`}
                    onClick={() => onUpdateProperty({ downPaymentPct: pct })}
                  >
                    {pct}%
                  </button>
                ))}
              </div>
              <div className="loan-amount-display">
                <span>Loan Amount:</span>
                <strong>{formatCurrency(loanAmount)}</strong>
              </div>
            </div>

            {/* Loan Programs */}
            <div className="panel-section">
              <h3 className="panel-section-title">Loan Program</h3>
              <div className="loan-programs-grid">
                {[
                  { id: 'conventional', name: 'Conventional', desc: '3-20% down, 620+ credit', minDown: 3 },
                  { id: 'fha', name: 'FHA', desc: '3.5% down, 580+ credit', minDown: 3.5 },
                  { id: 'va', name: 'VA', desc: '0% down, veterans only', minDown: 0 },
                  { id: 'usda', name: 'USDA', desc: '0% down, rural areas', minDown: 0 },
                  { id: 'jumbo', name: 'Jumbo', desc: 'Loans over $832,750', minDown: 10 },
                  { id: 'allinone', name: 'All In One', desc: 'First-lien HELOC, 680+ credit', minDown: 20, special: true },
                ].map(program => (
                  <button
                    key={program.id}
                    className={`loan-program-btn ${market.loanProgram === program.id ? 'active' : ''} ${program.special ? 'special' : ''}`}
                    onClick={() => onUpdateMarket({ loanProgram: program.id })}
                  >
                    {program.special && <span className="program-badge">HELOC</span>}
                    <span className="program-name">{program.name}</span>
                    <span className="program-desc">{program.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Interest Rate Options */}
            <div className="panel-section">
              <h3 className="panel-section-title">Interest Rate Options</h3>
              <p className="section-description">
                Select rates to compare. Check multiple to see side-by-side analysis.
              </p>
              <div className="rate-options-grid">
                {[
                  { rate: 6.25, label: 'Excellent Credit', points: 1.5 },
                  { rate: 6.5, label: 'Great Credit', points: 1 },
                  { rate: 6.75, label: 'Good Credit', points: 0.5 },
                  { rate: 6.875, label: 'Market Rate', points: 0 },
                  { rate: 7.0, label: 'Fair Credit', points: 0 },
                  { rate: 7.25, label: 'Lower Credit', points: 0 },
                ].map(option => (
                  <label
                    key={option.rate}
                    className={`rate-option ${market.interestRate === option.rate ? 'selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="interestRate"
                      checked={market.interestRate === option.rate}
                      onChange={() => onUpdateMarket({ interestRate: option.rate, points: option.points })}
                    />
                    <span className="rate-option-rate">{option.rate}%</span>
                    <span className="rate-option-label">{option.label}</span>
                    {option.points > 0 && (
                      <span className="rate-option-points">{option.points} pts</span>
                    )}
                  </label>
                ))}
              </div>
              <div className="custom-rate-input">
                <label>Or enter custom rate:</label>
                <div className="input-with-suffix compact">
                  <input
                    type="number"
                    step="0.125"
                    value={market.interestRate}
                    onChange={(e) => onUpdateMarket({ interestRate: parseFloat(e.target.value) || 0 })}
                  />
                  <span className="suffix">%</span>
                </div>
              </div>
            </div>

            {/* Loan Term */}
            <div className="panel-section">
              <h3 className="panel-section-title">Loan Term</h3>
              <div className="term-selector">
                {[
                  { years: 30, label: '30 Year' },
                  { years: 20, label: '20 Year' },
                  { years: 15, label: '15 Year' },
                  { years: 10, label: '10 Year' },
                ].map(term => (
                  <button
                    key={term.years}
                    className={`term-btn ${market.termYears === term.years ? 'active' : ''}`}
                    onClick={() => onUpdateMarket({ termYears: term.years })}
                  >
                    <span className="term-years">{term.years}</span>
                    <span className="term-label">years</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Discount Points */}
            <div className="panel-section">
              <h3 className="panel-section-title">Discount Points</h3>
              <p className="section-description">
                Pay upfront to reduce your rate. Each point costs 1% of loan amount.
              </p>
              <div className="points-control">
                <div className="points-buttons">
                  {[0, 0.5, 1, 1.5, 2].map(points => (
                    <button
                      key={points}
                      className={`point-btn ${market.points === points ? 'active' : ''}`}
                      onClick={() => onUpdateMarket({ points })}
                    >
                      {points}
                    </button>
                  ))}
                </div>
                {market.points > 0 && (
                  <div className="points-details">
                    <div className="points-detail-row">
                      <span>Upfront Cost</span>
                      <span className="cost">{formatCurrency(loanAmount * market.points / 100)}</span>
                    </div>
                    <div className="points-detail-row">
                      <span>Rate Reduction</span>
                      <span className="savings">-{(market.points * market.pointsDiscount).toFixed(3)}%</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Loan Summary */}
            <div className="loan-summary-card">
              <div className="summary-row">
                <span>Home Price</span>
                <span>{formatCurrency(property.homePrice)}</span>
              </div>
              <div className="summary-row">
                <span>Down Payment ({property.downPaymentPct}%)</span>
                <span>{formatCurrency(property.homePrice * property.downPaymentPct / 100)}</span>
              </div>
              <div className="summary-row">
                <span>Loan Amount</span>
                <span>{formatCurrency(loanAmount)}</span>
              </div>
              <div className="summary-row">
                <span>Loan Program</span>
                <span style={{ textTransform: 'uppercase' }}>{market.loanProgram || 'Conventional'}</span>
              </div>
              <div className="summary-row">
                <span>Interest Rate</span>
                <span>{effectiveInterestRate.toFixed(3)}%</span>
              </div>
              <div className="summary-row">
                <span>Term</span>
                <span>{market.termYears} years</span>
              </div>
              <div className="summary-row highlight">
                <span>Est. Monthly P&I</span>
                <span>{formatCurrency(monthlyPI)}</span>
              </div>
            </div>
          </div>
        )}

        {/* BUDGET TAB */}
        {activeTab === 'budget' && (
          <div className="tab-panel budget-panel">
            <div className="budget-header-card">
              <div className="budget-income">
                <span className="budget-income-label">Monthly Income</span>
                <span className="budget-income-value">{formatCurrency(profile.annualIncome / 12)}</span>
              </div>
              <div className="budget-available">
                <span className="budget-available-label">Available for Housing</span>
                <span className={`budget-available-value ${
                  (profile.annualIncome / 12) -
                  Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) -
                  profile.monthlyDebts > 0 ? 'positive' : 'negative'
                }`}>
                  {formatCurrency(
                    (profile.annualIncome / 12) -
                    Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) -
                    profile.monthlyDebts
                  )}
                </span>
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">Monthly Expenses</h3>
              <div className="budget-items-modern">
                {Object.entries(profile.budget || {}).map(([key, value]) => (
                  <div key={key} className="budget-item-modern">
                    <label>{key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')}</label>
                    <div className="input-with-prefix compact">
                      <span className="prefix">$</span>
                      <input
                        type="number"
                        value={value}
                        onChange={(e) => onUpdateProfile({
                          budget: { ...profile.budget, [key]: parseFloat(e.target.value) || 0 }
                        })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="budget-breakdown-card">
              <div className="breakdown-bar">
                <div
                  className="bar-segment expenses"
                  style={{
                    width: `${Math.min((Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) / (profile.annualIncome / 12)) * 100, 100)}%`
                  }}
                />
                <div
                  className="bar-segment debts"
                  style={{
                    width: `${Math.min((profile.monthlyDebts / (profile.annualIncome / 12)) * 100, 100)}%`
                  }}
                />
              </div>
              <div className="breakdown-legend">
                <div className="legend-item">
                  <span className="legend-color expenses"></span>
                  <span>Expenses: {formatCurrency(Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0))}</span>
                </div>
                <div className="legend-item">
                  <span className="legend-color debts"></span>
                  <span>Debts: {formatCurrency(profile.monthlyDebts)}</span>
                </div>
                <div className="legend-item">
                  <span className="legend-color available"></span>
                  <span>Available: {formatCurrency(
                    (profile.annualIncome / 12) -
                    Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) -
                    profile.monthlyDebts
                  )}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SCENARIOS TAB */}
        {activeTab === 'scenarios' && (
          <div className="tab-panel scenarios-panel">
            <div className="panel-section">
              <h3 className="panel-section-title">Price Point Scenarios</h3>
              <p className="section-description">
                Compare different home prices and see how they affect your monthly payment
              </p>
            </div>

            <div className="scenario-cards">
              {Object.entries(property.homePrices || {}).map(([key, value]) => {
                const scenarioLoan = value * (1 - property.downPaymentPct / 100);
                const r = effectiveInterestRate / 100 / 12;
                const n = market.termYears * 12;
                const scenarioPI = r === 0
                  ? scenarioLoan / n
                  : scenarioLoan * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
                const isActive = property.homePrice === value;

                return (
                  <div
                    key={key}
                    className={`scenario-card ${isActive ? 'active' : ''}`}
                    onClick={() => onUpdateProperty({ homePrice: value })}
                  >
                    {isActive && <div className="active-badge">Current</div>}
                    <div className="scenario-label">{key.charAt(0).toUpperCase() + key.slice(1)}</div>
                    <div className="scenario-price">
                      <div className="input-with-prefix" onClick={(e) => e.stopPropagation()}>
                        <span className="prefix">$</span>
                        <input
                          type="number"
                          value={value}
                          onChange={(e) => onUpdateProperty({
                            homePrices: { ...property.homePrices, [key]: parseFloat(e.target.value) || 0 }
                          })}
                        />
                      </div>
                    </div>
                    <div className="scenario-details">
                      <div className="scenario-detail">
                        <span className="detail-label">Down</span>
                        <span className="detail-value">{formatCurrency(value * property.downPaymentPct / 100)}</span>
                      </div>
                      <div className="scenario-detail">
                        <span className="detail-label">Loan</span>
                        <span className="detail-value">{formatCurrency(scenarioLoan)}</span>
                      </div>
                      <div className="scenario-detail highlight">
                        <span className="detail-label">Est. P&I</span>
                        <span className="detail-value">{formatCurrency(scenarioPI)}/mo</span>
                      </div>
                    </div>
                    {!isActive && (
                      <button className="use-scenario-btn">
                        Use This Price
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="client-data-footer">
        <span>Changes apply instantly to all calculator views</span>
      </div>
    </div>
  );
};

const ProgramOptionsView = ({ data }) => {
  const { programs, bestMatch, profile: borrowerProfile, homePrice } = data;
  const [expandedProgram, setExpandedProgram] = useState(bestMatch?.id || 'conventional-5');
  const [activeTab, setActiveTab] = useState('recommendation');

  const tabs = [
    { id: 'recommendation', label: 'AI Recommendation', step: 1 },
    { id: 'programs', label: 'Browse Programs', step: 2 },
    { id: 'details', label: 'Program Details', step: 3 },
    { id: 'compare', label: 'Compare', step: 4 },
  ];

  return (
    <div className="calculator-detail tabbed-view">
      <div className="detail-header">
        <h2>Program Options</h2>
        <p className="detail-subtitle">
          Loan programs available for your <strong>{formatCurrency(homePrice)}</strong> home purchase
        </p>
      </div>

      {/* Process Tabs */}
      <div className="process-tabs">
        {tabs.map((tab, idx) => (
          <button
            key={tab.id}
            className={`process-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-step">{tab.step}</span>
            <span className="tab-label">{tab.label}</span>
            {idx < tabs.length - 1 && <span className="tab-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'recommendation' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>AI Underwriter Recommendation</h3>
              <p>Our intelligent analysis of the best program for you</p>
            </div>
            <div className="ai-recommendation-banner">
              <div className="ai-header">
                <div className="ai-badge">AI UNDERWRITER ANALYSIS</div>
                <div className="ai-title">Recommended for You: {bestMatch?.name}</div>
              </div>
              <div className="ai-content">
                <p>{bestMatch?.aiInsight}</p>
              </div>
              <div className="ai-factors">
                <div className="factor-chip">Credit Score: {borrowerProfile.creditScore}</div>
                <div className="factor-chip">Savings: {formatCurrency(borrowerProfile.savings)}</div>
                <div className="factor-chip">First-Time Buyer</div>
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('programs')}>Browse All Programs →</button>
          </div>
        )}

        {activeTab === 'programs' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Available Programs</h3>
              <p>Click on a program to select it, then view details in the next tab</p>
            </div>
            <div className="program-summary-grid">
              {programs.filter(p => !p.requiresEligibility).map(program => (
                <div key={program.id}
                  className={`program-summary-card ${program.id === bestMatch?.id ? 'recommended' : ''} ${program.id === expandedProgram ? 'selected' : ''}`}
                  onClick={() => setExpandedProgram(program.id)}>
                  {program.id === bestMatch?.id && <div className="best-match-tag">Best Match</div>}
                  <div className="program-summary-name">{program.name}</div>
                  <div className="program-summary-payment">{formatCurrencyFull(program.monthlyPayment)}<span>/mo</span></div>
                  <div className="program-summary-down">{program.downPaymentPct}% down ({formatCurrency(program.downPayment)})</div>
                  <div className="program-summary-score">
                    <div className="score-bar"><div className="score-fill" style={{ width: `${program.suitabilityScore}%` }} /></div>
                    <span className="score-value">{program.suitabilityScore}/100</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="eligibility-programs">
              <h4>Programs Requiring Eligibility</h4>
              <p className="eligibility-note">These programs offer excellent terms if you qualify</p>
              <div className="eligibility-cards">
                {programs.filter(p => p.requiresEligibility).map(program => (
                  <div key={program.id}
                    className={`eligibility-card ${program.id === expandedProgram ? 'selected' : ''}`}
                    onClick={() => setExpandedProgram(program.id)}>
                    <div className="eligibility-header">
                      <div className="eligibility-name">{program.name}</div>
                      <div className="eligibility-tag">Check Eligibility</div>
                    </div>
                    <div className="eligibility-highlight">
                      <span className="highlight-label">Down Payment:</span>
                      <span className="highlight-value">{program.downPaymentPct}%</span>
                    </div>
                    <div className="eligibility-note-small">{program.eligibilityNote}</div>
                  </div>
                ))}
              </div>
            </div>
            <button className="next-step-btn" onClick={() => setActiveTab('details')}>View Program Details →</button>
          </div>
        )}

        {activeTab === 'details' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Program Details</h3>
              <p>Detailed information about the selected program</p>
            </div>
            {programs.filter(p => p.id === expandedProgram).map(program => (
              <div key={program.id} className="program-detail-expanded">
                <div className="program-detail-header">
                  <div className="program-detail-title">
                    <h3>{program.name}</h3>
                    <div className="program-lender">{program.lender}</div>
                  </div>
                  <div className={`program-category-badge ${program.category}`}>
                    {program.category === 'government' ? 'Government-Backed' : 'Conventional'}
                  </div>
                </div>
                <div className="program-ai-insight">
                  <div className="insight-label">AI Underwriter Insight</div>
                  <p>{program.aiInsight}</p>
                </div>
                <div className="program-numbers-grid">
                  <div className="number-card"><div className="number-label">Down Payment</div><div className="number-value">{formatCurrency(program.downPayment)}</div><div className="number-detail">{program.downPaymentPct}% of home price</div></div>
                  <div className="number-card"><div className="number-label">Monthly Payment</div><div className="number-value">{formatCurrencyFull(program.monthlyPayment)}</div><div className="number-detail">Principal, interest, taxes, insurance</div></div>
                  <div className="number-card"><div className="number-label">Interest Rate</div><div className="number-value">{program.interestRate}%</div><div className="number-detail">30-year fixed</div></div>
                  <div className="number-card"><div className="number-label">Cash to Close</div><div className="number-value">{formatCurrency(program.totalCashNeeded)}</div><div className="number-detail">Down payment + closing costs</div></div>
                </div>
                <div className="program-insurance-section">
                  <h4>Mortgage Insurance</h4>
                  <div className="insurance-details">
                    <div className="insurance-row"><span>Monthly MI/MIP</span><span>{program.pmi > 0 ? formatCurrencyFull(program.pmi) : 'None'}</span></div>
                    {program.mipUpfront && (<div className="insurance-row"><span>Upfront MIP (added to loan)</span><span>{formatCurrency(program.mipUpfront)}</span></div>)}
                    {program.fundingFee && (<div className="insurance-row"><span>VA Funding Fee</span><span>{formatCurrency(program.fundingFee)}</span></div>)}
                    {program.guaranteeFee && (<div className="insurance-row"><span>USDA Guarantee Fee</span><span>{formatCurrency(program.guaranteeFee)}</span></div>)}
                    <div className="insurance-row"><span>Removable?</span><span className={program.pmiRemovable ? 'positive' : program.pmiRemovable === false ? 'negative' : ''}>{program.pmiRemovable === true ? 'Yes, at 20% equity' : program.pmiRemovable === false ? 'No, for life of loan' : 'N/A - No MI'}</span></div>
                  </div>
                </div>
                <div className="program-requirements">
                  <h4>Requirements</h4>
                  <div className="requirements-grid">
                    <div className="requirement-item"><div className="requirement-label">Min. Credit Score</div><div className={`requirement-value ${borrowerProfile.creditScore >= program.creditScoreMin ? 'met' : 'not-met'}`}>{program.creditScoreMin}<span className="your-value">(Yours: {borrowerProfile.creditScore})</span></div></div>
                    <div className="requirement-item"><div className="requirement-label">Max DTI</div><div className="requirement-value">{program.dtiMax}%</div></div>
                  </div>
                </div>
                <div className="program-pros-cons">
                  <div className="pros-section"><h4>Advantages</h4><ul className="pros-list">{program.pros.map((pro, i) => (<li key={i}>{pro}</li>))}</ul></div>
                  <div className="cons-section"><h4>Considerations</h4><ul className="cons-list">{program.cons.map((con, i) => (<li key={i}>{con}</li>))}</ul></div>
                </div>
                <div className="program-best-for"><strong>Best For:</strong> {program.bestFor}</div>
              </div>
            ))}
            <button className="next-step-btn" onClick={() => setActiveTab('compare')}>Compare All Programs →</button>
          </div>
        )}

        {activeTab === 'compare' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>Side-by-Side Comparison</h3>
              <p>Compare all available programs at a glance</p>
            </div>
            <div className="program-comparison-table">
              <div className="comparison-table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Feature</th>
                      {programs.filter(p => !p.requiresEligibility).map(p => (
                        <th key={p.id} className={p.id === bestMatch?.id ? 'recommended' : ''}>{p.name.replace(' Down', '')}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr><td>Down Payment</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{formatCurrency(p.downPayment)}</td>))}</tr>
                    <tr><td>Monthly Payment</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{formatCurrencyFull(p.monthlyPayment)}</td>))}</tr>
                    <tr><td>Interest Rate</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{p.interestRate}%</td>))}</tr>
                    <tr><td>Monthly MI</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{p.pmi > 0 ? formatCurrencyFull(p.pmi) : '-'}</td>))}</tr>
                    <tr><td>MI Removable?</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id} className={p.pmiRemovable ? 'positive' : 'negative'}>{p.pmiRemovable ? 'Yes' : 'No'}</td>))}</tr>
                    <tr><td>Cash to Close</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{formatCurrency(p.totalCashNeeded)}</td>))}</tr>
                    <tr><td>Min. Credit</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id}>{p.creditScoreMin}</td>))}</tr>
                    <tr className="suitability-row"><td>Fit Score</td>{programs.filter(p => !p.requiresEligibility).map(p => (<td key={p.id} className={p.id === bestMatch?.id ? 'best' : ''}>{p.suitabilityScore}/100</td>))}</tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// NEW CALCULATOR VIEWS - Phase 1
// ============================================================================

const EmergencyRunwayView = ({ data }) => {
  const getStatusColor = (status) => {
    if (status === 'safe') return '#22c55e';
    if (status === 'caution') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Emergency Runway</h2>
        <p className="detail-subtitle">How long can you survive financially after closing?</p>
      </div>

      <div className="runway-overview">
        <div className="runway-stat-grid">
          <div className="runway-stat">
            <span className="stat-label">Current Savings</span>
            <span className="stat-value">{formatCurrency(data.savings)}</span>
          </div>
          <div className="runway-stat">
            <span className="stat-label">Down Payment</span>
            <span className="stat-value negative">-{formatCurrency(data.downPayment)}</span>
          </div>
          <div className="runway-stat">
            <span className="stat-label">Closing Costs</span>
            <span className="stat-value negative">-{formatCurrency(data.closingCosts)}</span>
          </div>
          <div className="runway-stat highlight">
            <span className="stat-label">Post-Close Savings</span>
            <span className="stat-value" style={{ color: data.postCloseSavings > 0 ? '#22c55e' : '#ef4444' }}>
              {formatCurrency(data.postCloseSavings)}
            </span>
          </div>
        </div>
      </div>

      <div className="runway-scenarios">
        <h3>Survival Scenarios</h3>
        <div className="scenario-cards">
          {data.scenarios.map((scenario, idx) => (
            <div key={idx} className="scenario-card" style={{ borderLeftColor: getStatusColor(scenario.status) }}>
              <div className="scenario-header">
                <span className="scenario-name">{scenario.name}</span>
                <span className="scenario-status" style={{ color: getStatusColor(scenario.status) }}>
                  {scenario.status.toUpperCase()}
                </span>
              </div>
              <div className="scenario-body">
                <div className="scenario-months">
                  <span className="months-value">
                    {scenario.months === Infinity ? '∞' : isNaN(scenario.months) ? '0' : scenario.months.toFixed(1)}
                  </span>
                  <span className="months-label">months</span>
                </div>
                <div className="scenario-burn">
                  Monthly burn: {formatCurrency(scenario.monthlyBurn)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="runway-recommendation">
        <div className="rec-header">
          <span className="rec-icon">{data.riskLevel === 'low' ? '✅' : data.riskLevel === 'moderate' ? '⚠️' : '🚨'}</span>
          <span className="rec-level">Risk Level: {data.riskLevel.toUpperCase()}</span>
        </div>
        <p>
          {data.riskLevel === 'low' && 'Great! You have solid reserves after closing.'}
          {data.riskLevel === 'moderate' && 'Caution: Your reserves are tight. Consider a smaller down payment.'}
          {data.riskLevel === 'high' && 'Warning: Very low reserves. Consider waiting to save more.'}
        </p>
        <div className="rec-target">
          Recommended Reserve: {formatCurrency(data.recommendedReserve)} (6 months expenses)
        </div>
      </div>
    </div>
  );
};

const StressTestView = ({ data }) => {
  const getStatusColor = (survivable) => survivable ? '#22c55e' : '#ef4444';

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Life Happens Stress Test</h2>
        <p className="detail-subtitle">Can you survive financial surprises?</p>
      </div>

      <div className="stress-baseline">
        <h3>Your Baseline</h3>
        <div className="baseline-stats">
          <div className="baseline-stat">
            <span>Monthly Payment</span>
            <span>{formatCurrency(data.baseline.piti)}</span>
          </div>
          <div className="baseline-stat">
            <span>Current DTI</span>
            <span>{data.baseline.dti.toFixed(1)}%</span>
          </div>
          <div className="baseline-stat">
            <span>Monthly Income</span>
            <span>{formatCurrency(data.monthlyIncome)}</span>
          </div>
        </div>
      </div>

      <div className="stress-scenarios">
        <h3>Stress Scenarios</h3>
        <div className="stress-table">
          <div className="stress-header">
            <span>Scenario</span>
            <span>New Payment</span>
            <span>New DTI</span>
            <span>Status</span>
          </div>
          {data.scenarios.map((scenario, idx) => (
            <div key={idx} className="stress-row">
              <div className="stress-scenario">
                <span className="scenario-name">{scenario.name}</span>
                <span className="scenario-trigger">{scenario.trigger}</span>
              </div>
              <span className="stress-payment">
                {formatCurrency(scenario.newPayment)}
                {scenario.impact > 0 && <span className="payment-change">+{formatCurrency(scenario.impact)}</span>}
              </span>
              <span className="stress-dti">{scenario.newDti.toFixed(1)}%</span>
              <span className="stress-status" style={{ color: getStatusColor(scenario.survivable) }}>
                {scenario.survivable ? 'PASS' : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="stress-score">
        <div className="score-circle" style={{
          background: `conic-gradient(${data.resilienceScore >= 80 ? '#22c55e' : data.resilienceScore >= 60 ? '#f59e0b' : '#ef4444'} ${data.resilienceScore * 3.6}deg, #e2e8f0 0deg)`
        }}>
          <div className="score-inner">
            <span className="score-value">{data.passCount}/{data.totalScenarios}</span>
            <span className="score-label">Tests Passed</span>
          </div>
        </div>
        <div className="score-assessment">
          <h4>Resilience Score: {data.resilienceScore.toFixed(0)}%</h4>
          <p>
            {data.resilienceScore >= 80 && 'Excellent! Your finances can handle most life surprises.'}
            {data.resilienceScore >= 60 && data.resilienceScore < 80 && 'Good resilience, but some scenarios are tight.'}
            {data.resilienceScore < 60 && 'Consider building more financial cushion before buying.'}
          </p>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// NEW CALCULATOR VIEWS - Phase 2
// ============================================================================

const PaymentShockView = ({ data }) => {
  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Payment Shock Forecast</h2>
        <p className="detail-subtitle">How your payment may change over time</p>
      </div>

      <div className="shock-current">
        <h3>Current Payment Breakdown</h3>
        <div className="payment-breakdown">
          <div className="breakdown-item">
            <span>Principal & Interest</span>
            <span>{formatCurrency(data.current.principalInterest)}</span>
          </div>
          <div className="breakdown-item">
            <span>Property Tax</span>
            <span>{formatCurrency(data.current.propertyTax)}</span>
          </div>
          <div className="breakdown-item">
            <span>Insurance</span>
            <span>{formatCurrency(data.current.insurance)}</span>
          </div>
          {data.current.pmi > 0 && (
            <div className="breakdown-item">
              <span>PMI</span>
              <span>{formatCurrency(data.current.pmi)}</span>
            </div>
          )}
          <div className="breakdown-item total">
            <span>Total PITI</span>
            <span>{formatCurrency(data.current.total)}</span>
          </div>
        </div>
      </div>

      <div className="shock-timeline">
        <h3>10-Year Projection</h3>
        <div className="timeline-table">
          <div className="timeline-header">
            <span>Year</span>
            <span>P&I</span>
            <span>Tax</span>
            <span>Insurance</span>
            <span>PMI</span>
            <span>Total</span>
            <span>Increase</span>
          </div>
          {data.projections.map((p) => (
            <div key={p.year} className="timeline-row">
              <span className="year-col">Year {p.year}</span>
              <span>{formatCurrency(p.principalInterest)}</span>
              <span>{formatCurrency(p.propertyTax)}</span>
              <span>{formatCurrency(p.insurance)}</span>
              <span>{formatCurrency(p.pmi)}</span>
              <span className="total-col">{formatCurrency(p.total)}</span>
              <span className="increase-col" style={{ color: p.increase > 0 ? '#ef4444' : '#22c55e' }}>
                {p.increase > 0 ? '+' : ''}{formatCurrency(p.increase)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="shock-summary">
        <div className="summary-stat">
          <span className="stat-label">Peak Payment (Year {data.peakYear})</span>
          <span className="stat-value">{formatCurrency(data.maxPayment)}</span>
        </div>
        <div className="summary-stat">
          <span className="stat-label">Payment Shock Index</span>
          <span className="stat-value" style={{ color: data.shockIndex > 15 ? '#ef4444' : '#f59e0b' }}>
            +{data.shockIndex.toFixed(1)}%
          </span>
        </div>
        <p className="shock-note">
          Note: Property taxes typically increase 3% annually, insurance 4%, and HOA fees 5%.
          PMI is removed around year 7 when you reach 78% LTV.
        </p>
      </div>
    </div>
  );
};

const LifestyleFitView = ({ data }) => {
  const getFitColor = (level) => {
    if (level === 'comfortable') return '#22c55e';
    if (level === 'adequate') return '#3b82f6';
    if (level === 'tight') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Lifestyle Fit Index</h2>
        <p className="detail-subtitle">Will homeownership change your quality of life?</p>
      </div>

      <div className="lifestyle-score">
        <div className="fit-gauge" style={{ '--fit-color': getFitColor(data.fitLevel) }}>
          <div className="gauge-value">{data.fitScore.toFixed(0)}%</div>
          <div className="gauge-label">Discretionary Income</div>
          <div className="gauge-level" style={{ color: getFitColor(data.fitLevel) }}>
            {data.fitLevel.toUpperCase()}
          </div>
        </div>
      </div>

      <div className="lifestyle-comparison">
        <div className="budget-column renter">
          <h3>As Renter</h3>
          <div className="budget-items">
            <div className="budget-item">
              <span>Housing</span>
              <span>{formatCurrency(data.currentBudget.housing)}</span>
            </div>
            <div className="budget-item">
              <span>Utilities</span>
              <span>{formatCurrency(data.currentBudget.utilities)}</span>
            </div>
            <div className="budget-item">
              <span>Food</span>
              <span>{formatCurrency(data.currentBudget.food)}</span>
            </div>
            <div className="budget-item">
              <span>Transportation</span>
              <span>{formatCurrency(data.currentBudget.transportation)}</span>
            </div>
            <div className="budget-item">
              <span>Entertainment</span>
              <span>{formatCurrency(data.currentBudget.entertainment)}</span>
            </div>
            <div className="budget-item">
              <span>Savings</span>
              <span>{formatCurrency(data.currentBudget.savings)}</span>
            </div>
            <div className="budget-item total">
              <span>Total Expenses</span>
              <span>{formatCurrency(data.currentBudget.total)}</span>
            </div>
          </div>
        </div>

        <div className="budget-arrow">→</div>

        <div className="budget-column homeowner">
          <h3>As Homeowner</h3>
          <div className="budget-items">
            <div className="budget-item">
              <span>Housing (PITI)</span>
              <span>{formatCurrency(data.homeownerBudget.housing)}</span>
            </div>
            <div className="budget-item">
              <span>Utilities</span>
              <span>{formatCurrency(data.homeownerBudget.utilities)}</span>
            </div>
            <div className="budget-item">
              <span>Maintenance Reserve</span>
              <span>{formatCurrency(data.homeownerBudget.maintenance)}</span>
            </div>
            <div className="budget-item">
              <span>Food</span>
              <span>{formatCurrency(data.homeownerBudget.food)}</span>
            </div>
            <div className="budget-item">
              <span>Entertainment</span>
              <span>{formatCurrency(data.homeownerBudget.entertainment)}</span>
            </div>
            <div className="budget-item">
              <span>Savings</span>
              <span>{formatCurrency(data.homeownerBudget.savings)}</span>
            </div>
            <div className="budget-item total">
              <span>Total Expenses</span>
              <span>{formatCurrency(data.homeownerBudget.total)}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="lifestyle-impact">
        <h3>Monthly Impact</h3>
        <div className="impact-summary">
          <div className="impact-stat">
            <span>Monthly Squeeze</span>
            <span style={{ color: data.monthlySqueeze > 0 ? '#ef4444' : '#22c55e' }}>
              {data.monthlySqueeze > 0 ? '+' : ''}{formatCurrency(data.monthlySqueeze)}
            </span>
          </div>
          <div className="impact-stat">
            <span>Discretionary Left</span>
            <span style={{ color: getFitColor(data.fitLevel) }}>{formatCurrency(data.discretionaryIncome)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// SCENARIO SELECTOR COMPONENT
// ============================================================================

const ScenarioSelector = ({
  homePrice,
  downPaymentPct,
  interestRate,
  termYears,
  points,
  loanProgram = 'conventional',
  onUpdate
}) => {
  const DOWN_PAYMENT_OPTIONS = [3, 3.5, 5, 10, 20];
  const TERM_OPTIONS = [30, 20, 15, 10];
  const POINTS_OPTIONS = [0, 0.5, 1, 1.5, 2];

  const LOAN_PROGRAMS = [
    { id: 'conventional', name: 'Conventional', desc: '3-20% down, 620+ credit', minDown: 3 },
    { id: 'fha', name: 'FHA', desc: '3.5% down, 580+ credit', minDown: 3.5 },
    { id: 'va', name: 'VA', desc: '0% down, veterans only', minDown: 0 },
    { id: 'usda', name: 'USDA', desc: '0% down, rural areas', minDown: 0 },
    { id: 'jumbo', name: 'Jumbo', desc: 'Loans over $832,750', minDown: 10 },
    { id: 'allinone', name: 'All In One', desc: 'First-lien HELOC, 680+ credit', minDown: 20, special: true },
  ];

  const RATE_OPTIONS = [
    { rate: 6.25, label: 'Excellent Credit', points: 1.5 },
    { rate: 6.5, label: 'Great Credit', points: 1 },
    { rate: 6.75, label: 'Good Credit', points: 0.5 },
    { rate: 6.875, label: 'Market Rate', points: 0 },
    { rate: 7.0, label: 'Fair Credit', points: 0 },
    { rate: 7.25, label: 'Lower Credit', points: 0 },
  ];

  const [selectedProgram, setSelectedProgram] = useState(loanProgram);
  const [selectedRate, setSelectedRate] = useState(interestRate);
  const [customRate, setCustomRate] = useState(interestRate.toString());

  const downPayment = homePrice * (downPaymentPct / 100);
  const loanAmount = homePrice - downPayment;
  const pointsCost = loanAmount * (points / 100);
  const rateReduction = points * 0.25;

  const handleProgramChange = (programId) => {
    setSelectedProgram(programId);
    const program = LOAN_PROGRAMS.find(p => p.id === programId);
    if (program && downPaymentPct < program.minDown) {
      onUpdate({ downPaymentPct: program.minDown });
    }
  };

  return (
    <div className="scenario-selector">
      {/* Purchase Details */}
      <div className="selector-section">
        <h3>Purchase Details</h3>
        <div className="selector-row">
          <div className="selector-field">
            <label>Home Price</label>
            <div className="input-with-prefix">
              <span className="prefix">$</span>
              <input
                type="number"
                value={homePrice}
                onChange={(e) => onUpdate({ homePrice: Number(e.target.value) || 0 })}
              />
            </div>
          </div>
          <div className="selector-field">
            <label>Down Payment</label>
            <div className="down-payment-input">
              <div className="input-with-suffix">
                <input
                  type="number"
                  value={downPaymentPct}
                  onChange={(e) => onUpdate({ downPaymentPct: Number(e.target.value) || 0 })}
                />
                <span className="suffix">%</span>
              </div>
              <span className="down-amount">{formatCurrency(downPayment)}</span>
            </div>
          </div>
        </div>
        <div className="quick-select-row">
          {DOWN_PAYMENT_OPTIONS.map(pct => (
            <button
              key={pct}
              className={`quick-btn ${downPaymentPct === pct ? 'active' : ''}`}
              onClick={() => onUpdate({ downPaymentPct: pct })}
            >
              {pct}%
            </button>
          ))}
        </div>
        <div className="loan-amount-display">
          <span>Loan Amount:</span>
          <span className="loan-value">{formatCurrency(loanAmount)}</span>
        </div>
      </div>

      {/* Loan Program */}
      <div className="selector-section">
        <h3>Loan Program</h3>
        <div className="program-grid">
          {LOAN_PROGRAMS.map(program => (
            <button
              key={program.id}
              className={`program-btn ${selectedProgram === program.id ? 'active' : ''} ${program.special ? 'special' : ''}`}
              onClick={() => handleProgramChange(program.id)}
            >
              {program.special && <span className="special-badge">HELOC</span>}
              <span className="program-name">{program.name}</span>
              <span className="program-desc">{program.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Interest Rate Options */}
      <div className="selector-section">
        <h3>Interest Rate Options</h3>
        <p className="section-hint">Select rates to compare. Check multiple to see side-by-side analysis.</p>
        <div className="rate-grid">
          {RATE_OPTIONS.map((opt, idx) => (
            <button
              key={idx}
              className={`rate-btn ${selectedRate === opt.rate ? 'active' : ''}`}
              onClick={() => {
                setSelectedRate(opt.rate);
                setCustomRate(opt.rate.toString());
                onUpdate({ interestRate: opt.rate, points: opt.points });
              }}
            >
              <span className="rate-value">{opt.rate}%</span>
              <span className="rate-label">{opt.label}</span>
              {opt.points > 0 && <span className="rate-points">{opt.points} pts</span>}
            </button>
          ))}
        </div>
        <div className="custom-rate-row">
          <span>Or enter custom rate:</span>
          <div className="input-with-suffix small">
            <input
              type="number"
              step="0.125"
              value={customRate}
              onChange={(e) => {
                setCustomRate(e.target.value);
                const rate = parseFloat(e.target.value);
                if (!isNaN(rate) && rate > 0) {
                  setSelectedRate(rate);
                  onUpdate({ interestRate: rate });
                }
              }}
            />
            <span className="suffix">%</span>
          </div>
        </div>
      </div>

      {/* Loan Term */}
      <div className="selector-section">
        <h3>Loan Term</h3>
        <div className="term-grid">
          {TERM_OPTIONS.map(term => (
            <button
              key={term}
              className={`term-btn ${termYears === term ? 'active' : ''}`}
              onClick={() => onUpdate({ termYears: term })}
            >
              <span className="term-value">{term}</span>
              <span className="term-label">years</span>
            </button>
          ))}
        </div>
      </div>

      {/* Discount Points */}
      <div className="selector-section">
        <h3>Discount Points</h3>
        <p className="section-hint">Pay upfront to reduce your rate. Each point costs 1% of loan amount.</p>
        <div className="points-row">
          {POINTS_OPTIONS.map(pt => (
            <button
              key={pt}
              className={`points-btn ${points === pt ? 'active' : ''}`}
              onClick={() => onUpdate({ points: pt })}
            >
              {pt}
            </button>
          ))}
        </div>
        {points > 0 && (
          <div className="points-summary">
            <div className="points-item">
              <span>Upfront Cost</span>
              <span className="cost">{formatCurrency(pointsCost)}</span>
            </div>
            <div className="points-item">
              <span>Rate Reduction</span>
              <span className="reduction">-{rateReduction.toFixed(3)}%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// NEW CALCULATOR VIEWS - Phase 3
// ============================================================================

const BreakEvenHorizonView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Break-Even Horizon</h2>
        <p className="detail-subtitle">When does buying beat renting?</p>
      </div>

      {onUpdate && (
        <ScenarioSelector
          homePrice={property?.homePrice || 285000}
          downPaymentPct={property?.downPaymentPct || 5}
          interestRate={market?.interestRate || 6.875}
          termYears={market?.termYears || 30}
          points={market?.points || 0}
          onUpdate={onUpdate}
        />
      )}

      <div className="breakeven-result">
        <div className="breakeven-highlight">
          <span className="be-label">Break-Even Point</span>
          <span className="be-value">
            Year {data.breakEvenYear}
          </span>
          <span className="be-note">
            {typeof data.breakEvenYear === 'number'
              ? `After ${data.breakEvenYear} years, buying becomes more profitable than renting.`
              : 'Based on assumptions, buying may take longer than 10 years to break even.'}
          </span>
        </div>
      </div>

      <div className="breakeven-timeline">
        <h3>Year-by-Year Comparison</h3>
        <div className="be-table">
          <div className="be-header">
            <span>Year</span>
            <span>Renter Net Worth</span>
            <span>Buyer Net Worth</span>
            <span>Advantage</span>
          </div>
          {data.comparison.map((c) => (
            <div key={c.year} className={`be-row ${c.buyerAdvantage > 0 ? 'buyer-wins' : ''}`}>
              <span>Year {c.year}</span>
              <span>{formatCurrency(c.netRenter)}</span>
              <span>{formatCurrency(c.netBuyer)}</span>
              <span style={{ color: c.buyerAdvantage > 0 ? '#22c55e' : '#ef4444' }}>
                {c.buyerAdvantage > 0 ? '+' : ''}{formatCurrency(c.buyerAdvantage)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="breakeven-assumptions">
        <h4>Assumptions</h4>
        <div className="assumptions-grid">
          <div className="assumption">
            <span>Home Appreciation</span>
            <span>{data.assumptions.homeAppreciation}%/year</span>
          </div>
          <div className="assumption">
            <span>Rent Increase</span>
            <span>{data.assumptions.rentIncrease}%/year</span>
          </div>
          <div className="assumption">
            <span>Investment Return</span>
            <span>{data.assumptions.investmentReturn}%/year</span>
          </div>
          <div className="assumption">
            <span>Maintenance</span>
            <span>{data.assumptions.maintenance}%/year</span>
          </div>
        </div>
      </div>
    </div>
  );
};

const EquityVelocityView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Equity Velocity</h2>
        <p className="detail-subtitle">How fast will your wealth grow?</p>
      </div>

      {onUpdate && (
        <ScenarioSelector
          homePrice={property?.homePrice || 285000}
          downPaymentPct={property?.downPaymentPct || 5}
          interestRate={market?.interestRate || 6.875}
          termYears={market?.termYears || 30}
          points={market?.points || 0}
          onUpdate={onUpdate}
        />
      )}

      <div className="velocity-highlights">
        <div className="velocity-stat">
          <span className="stat-label">Year 5 Equity</span>
          <span className="stat-value green">{formatCurrency(data.year5Equity)}</span>
        </div>
        <div className="velocity-stat">
          <span className="stat-label">Year 10 Equity</span>
          <span className="stat-value green">{formatCurrency(data.year10Equity)}</span>
        </div>
        <div className="velocity-stat">
          <span className="stat-label">Peak Velocity Year</span>
          <span className="stat-value">Year {data.peakVelocityYear}</span>
        </div>
      </div>

      <div className="velocity-timeline">
        <h3>Equity Growth Timeline</h3>
        <div className="velocity-table">
          <div className="v-header">
            <span>Year</span>
            <span>Home Value</span>
            <span>Loan Balance</span>
            <span>Total Equity</span>
            <span>Yearly Gain</span>
            <span>ROI</span>
          </div>
          {data.timeline.slice(0, 10).map((t) => (
            <div key={t.year} className="v-row">
              <span>Year {t.year}</span>
              <span>{formatCurrency(t.homeValue)}</span>
              <span>{formatCurrency(t.loanBalance)}</span>
              <span className="equity-col">{formatCurrency(t.totalEquity)}</span>
              <span style={{ color: '#22c55e' }}>+{formatCurrency(t.velocityThisYear)}</span>
              <span>{t.roi.toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="velocity-breakdown">
        <h3>Equity Sources (Year 10)</h3>
        <div className="source-bars">
          <div className="source-bar">
            <span className="source-label">Down Payment</span>
            <div className="bar-fill" style={{ width: `${(data.initialEquity / data.year10Equity) * 100}%`, background: '#3b82f6' }} />
            <span className="source-value">{formatCurrency(data.initialEquity)}</span>
          </div>
          <div className="source-bar">
            <span className="source-label">Principal Paid</span>
            <div className="bar-fill" style={{ width: `${(data.timeline[9].equityFromPrincipal / data.year10Equity) * 100}%`, background: '#22c55e' }} />
            <span className="source-value">{formatCurrency(data.timeline[9].equityFromPrincipal)}</span>
          </div>
          <div className="source-bar">
            <span className="source-label">Appreciation</span>
            <div className="bar-fill" style={{ width: `${(data.timeline[9].equityFromAppreciation / data.year10Equity) * 100}%`, background: '#f59e0b' }} />
            <span className="source-value">{formatCurrency(data.timeline[9].equityFromAppreciation)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

const TaxBenefitView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Tax Benefit Realization</h2>
        <p className="detail-subtitle">Your actual tax savings from homeownership</p>
      </div>

      {onUpdate && (
        <ScenarioSelector
          homePrice={property?.homePrice || 285000}
          downPaymentPct={property?.downPaymentPct || 5}
          interestRate={market?.interestRate || 6.875}
          termYears={market?.termYears || 30}
          points={market?.points || 0}
          onUpdate={onUpdate}
        />
      )}

      <div className="tax-summary">
        <div className="tax-stat">
          <span className="stat-label">Your Tax Bracket</span>
          <span className="stat-value">{(data.marginalTaxRate * 100).toFixed(0)}%</span>
        </div>
        <div className="tax-stat">
          <span className="stat-label">Year 1 Tax Savings</span>
          <span className="stat-value green">{formatCurrency(data.year1Savings)}</span>
        </div>
        <div className="tax-stat">
          <span className="stat-label">Monthly Benefit</span>
          <span className="stat-value green">{formatCurrency(data.year1MonthlyBenefit)}</span>
        </div>
        <div className="tax-stat highlight">
          <span className="stat-label">Effective Monthly Payment</span>
          <span className="stat-value">{formatCurrency(data.effectiveYear1Payment)}</span>
        </div>
      </div>

      <div className="tax-itemizing">
        <div className={`itemizing-status ${data.itemizingBeneficial ? 'beneficial' : 'not-beneficial'}`}>
          {data.itemizingBeneficial ? (
            <>
              <span className="status-icon">✅</span>
              <span>Itemizing your deductions makes sense!</span>
            </>
          ) : (
            <>
              <span className="status-icon">⚠️</span>
              <span>Standard deduction may be better for you.</span>
            </>
          )}
        </div>
        <div className="deduction-comparison">
          <div className="deduction-item">
            <span>Your Itemized Deductions (Year 1)</span>
            <span>{formatCurrency(data.yearlyBenefits[0].totalDeductions)}</span>
          </div>
          <div className="deduction-item">
            <span>Standard Deduction</span>
            <span>{formatCurrency(data.standardDeduction)}</span>
          </div>
        </div>
      </div>

      <div className="tax-timeline">
        <h3>10-Year Tax Benefit Projection</h3>
        <div className="tax-table">
          <div className="tax-header">
            <span>Year</span>
            <span>Mortgage Interest</span>
            <span>Property Tax</span>
            <span>Tax Savings</span>
            <span>Effective Payment</span>
          </div>
          {data.yearlyBenefits.map((y) => (
            <div key={y.year} className="tax-row">
              <span>Year {y.year}</span>
              <span>{formatCurrency(y.mortgageInterest)}</span>
              <span>{formatCurrency(y.propertyTax)}</span>
              <span style={{ color: '#22c55e' }}>{formatCurrency(y.taxSavings)}</span>
              <span>{formatCurrency(y.effectivePayment)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="tax-total">
        <span>Total 10-Year Tax Savings:</span>
        <span className="total-value">{formatCurrency(data.totalTenYearSavings)}</span>
      </div>
    </div>
  );
};

const InflationHedgeView = ({ data, property, market, onUpdate }) => {
  const getColor = (rec) => {
    if (rec === 'strong') return '#22c55e';
    if (rec === 'moderate') return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Inflation Hedge Index</h2>
        <p className="detail-subtitle">How homeownership protects you from rising costs</p>
      </div>

      {onUpdate && (
        <ScenarioSelector
          homePrice={property?.homePrice || 285000}
          downPaymentPct={property?.downPaymentPct || 5}
          interestRate={market?.interestRate || 6.875}
          termYears={market?.termYears || 30}
          points={market?.points || 0}
          onUpdate={onUpdate}
        />
      )}

      <div className="hedge-score">
        <div className="score-display" style={{ '--hedge-color': getColor(data.recommendation) }}>
          <span className="score-number">{data.hedgeScore.toFixed(0)}</span>
          <span className="score-label">Hedge Score</span>
          <span className="score-recommendation" style={{ color: getColor(data.recommendation) }}>
            {data.recommendation.toUpperCase()} PROTECTION
          </span>
        </div>
      </div>

      <div className="hedge-comparison">
        <h3>Current Costs</h3>
        <div className="cost-compare">
          <div className="cost-item">
            <span>Your Rent Today</span>
            <span>{formatCurrency(data.currentRent)}</span>
          </div>
          <div className="cost-item">
            <span>Mortgage Payment (PITI)</span>
            <span>{formatCurrency(data.currentPiti)}</span>
          </div>
        </div>
      </div>

      <div className="hedge-scenarios">
        <h3>Inflation Scenarios (10-Year Projection)</h3>
        {data.analysis.map((scenario, idx) => (
          <div key={idx} className="scenario-block">
            <div className="scenario-title">
              <span>{scenario.scenario}</span>
              <span className="hedge-value" style={{ color: scenario.totalHedgeValue > 0 ? '#22c55e' : '#ef4444' }}>
                {scenario.totalHedgeValue > 0 ? '+' : ''}{formatCurrency(scenario.totalHedgeValue)} hedge value
              </span>
            </div>
            <div className="scenario-detail">
              <span>Year 10 Rent: {formatCurrency(scenario.year10Rent)}</span>
              <span>Year 10 PITI: {formatCurrency(scenario.year10Piti)}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="hedge-insight">
        <h4>Why This Matters</h4>
        <p>
          With a fixed-rate mortgage, your principal & interest payment never changes.
          While taxes and insurance increase, they're a smaller portion of your payment.
          Meanwhile, rents typically rise 3-5% annually, compounding over time.
        </p>
      </div>
    </div>
  );
};

const JobMobilityView = ({ data, property, market, onUpdate }) => {
  return (
    <div className="calculator-detail with-selector">
      <div className="detail-header">
        <h2>Job Mobility Impact</h2>
        <p className="detail-subtitle">What if you need to relocate?</p>
      </div>

      {onUpdate && (
        <ScenarioSelector
          homePrice={property?.homePrice || 285000}
          downPaymentPct={property?.downPaymentPct || 5}
          interestRate={market?.interestRate || 6.875}
          termYears={market?.termYears || 30}
          points={market?.points || 0}
          onUpdate={onUpdate}
        />
      )}

      <div className="mobility-summary">
        <div className="mobility-stat">
          <span className="stat-label">Minimum Stay to Break Even</span>
          <span className="stat-value">{data.breakEvenYear} years</span>
        </div>
        <div className="mobility-stat">
          <span className="stat-label">Initial Investment</span>
          <span className="stat-value">{formatCurrency(data.initialInvestment)}</span>
        </div>
        <div className="mobility-stat">
          <span className="stat-label">Flexibility Score</span>
          <span className="stat-value" style={{
            color: data.flexibilityScore === 'good' ? '#22c55e' :
                   data.flexibilityScore === 'moderate' ? '#f59e0b' : '#ef4444'
          }}>
            {data.flexibilityScore.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="mobility-scenarios">
        <h3>Relocation Scenarios</h3>
        <div className="mobility-table">
          <div className="mob-header">
            <span>If You Move In</span>
            <span>Home Value</span>
            <span>Net Proceeds</span>
            <span>Total Cost</span>
            <span>vs Renting</span>
          </div>
          {data.scenarios.map((s) => (
            <div key={s.year} className={`mob-row ${s.betterThanRenting ? 'better' : 'worse'}`}>
              <span>Year {s.year}</span>
              <span>{formatCurrency(s.homeValue)}</span>
              <span style={{ color: s.netProceeds > data.initialInvestment ? '#22c55e' : '#ef4444' }}>
                {formatCurrency(s.netProceeds)}
              </span>
              <span>{formatCurrency(s.totalBuyingCost)}</span>
              <span style={{ color: s.betterThanRenting ? '#22c55e' : '#ef4444' }}>
                {s.betterThanRenting ? 'Better' : 'Worse'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mobility-breakdown">
        <h3>Cost Breakdown (If Selling in Year 3)</h3>
        {data.scenarios[2] && (
          <div className="breakdown-items">
            <div className="breakdown-item">
              <span>Down Payment + Closing</span>
              <span>{formatCurrency(data.initialInvestment)}</span>
            </div>
            <div className="breakdown-item">
              <span>3 Years of Payments</span>
              <span>{formatCurrency(data.scenarios[2].totalPiti)}</span>
            </div>
            <div className="breakdown-item">
              <span>Selling Costs (8%)</span>
              <span>-{formatCurrency(data.scenarios[2].sellingCosts)}</span>
            </div>
            <div className="breakdown-item">
              <span>Net Proceeds from Sale</span>
              <span>{formatCurrency(data.scenarios[2].netProceeds)}</span>
            </div>
            <div className="breakdown-item total">
              <span>Total Housing Cost</span>
              <span>{formatCurrency(data.scenarios[2].totalBuyingCost)}</span>
            </div>
            <div className="breakdown-item comparison">
              <span>3 Years Rent Would Cost</span>
              <span>{formatCurrency(data.scenarios[2].rentEquivalent)}</span>
            </div>
          </div>
        )}
      </div>

      <div className="mobility-advice">
        <h4>Recommendation</h4>
        <p>
          {data.flexibilityScore === 'good' && 'Your situation allows for reasonable mobility. Even a 2-year stay could work out financially.'}
          {data.flexibilityScore === 'moderate' && 'Plan to stay at least 3 years to avoid losing money on the transaction.'}
          {data.flexibilityScore === 'poor' && 'Consider renting if you might need to relocate within 3-5 years.'}
        </p>
      </div>
    </div>
  );
};

// ============================================================================
// MAIN COMPONENT
// ============================================================================

const CalculatorDashboard = ({ initialProfile = DEFAULT_PROFILE, initialMarket = DEFAULT_MARKET, initialProperty = DEFAULT_PROPERTY }) => {
  const [activeCalculator, setActiveCalculator] = useState('client-data');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedPhases, setExpandedPhases] = useState(['phase-1']); // Default first phase expanded

  const togglePhase = (phaseId) => {
    setExpandedPhases(prev =>
      prev.includes(phaseId)
        ? prev.filter(id => id !== phaseId)
        : [...prev, phaseId]
    );
  };

  // Editable state for all inputs
  const [profileData, setProfileData] = useState(initialProfile);
  const [marketData, setMarketData] = useState(initialMarket);
  const [propertyData, setPropertyData] = useState(initialProperty);

  // Auto-calculate tax and insurance rates based on location
  const locationRates = useMemo(() => {
    return getLocationRates(propertyData.state, propertyData.county);
  }, [propertyData.state, propertyData.county]);

  // Compute effective tax and insurance rates (override or auto-calculated)
  const effectiveRates = useMemo(() => ({
    taxRate: propertyData.taxRateOverride !== null ? propertyData.taxRateOverride : locationRates.taxRate,
    insuranceRate: propertyData.insuranceRateOverride !== null ? propertyData.insuranceRateOverride : locationRates.insuranceRate,
  }), [propertyData.taxRateOverride, propertyData.insuranceRateOverride, locationRates]);

  // Compute effective interest rate with points
  const effectiveInterestRate = useMemo(() => {
    return marketData.interestRate - (marketData.points * marketData.pointsDiscount);
  }, [marketData.interestRate, marketData.points, marketData.pointsDiscount]);

  // Combined profile with monthly income calculated
  const profile = useMemo(() => ({
    ...profileData,
    monthlyIncome: profileData.annualIncome / 12,
  }), [profileData]);

  // Combined market data with effective rates
  const market = useMemo(() => ({
    ...marketData,
    interestRate: effectiveInterestRate,
    taxRate: effectiveRates.taxRate,
    insuranceRate: effectiveRates.insuranceRate,
  }), [marketData, effectiveInterestRate, effectiveRates]);

  // Build calculators with current data
  const calculators = useMemo(() => {
    const calcs = buildCalculators(profile, market, propertyData);
    // Add client-data tab at the beginning
    return [
      {
        id: 'client-data',
        name: 'Client Data',
        color: '#0ea5e9',
        shortDescription: 'Edit inputs & assumptions',
        data: {
          profile: profileData,
          market: marketData,
          property: propertyData,
          locationRates,
          effectiveRates,
          effectiveInterestRate,
        },
      },
      ...calcs,
    ];
  }, [profile, market, propertyData, profileData, marketData, locationRates, effectiveRates, effectiveInterestRate]);

  const active = calculators.find((c) => c.id === activeCalculator);

  // Handlers for updating data
  const updateProfile = (updates) => {
    setProfileData(prev => ({ ...prev, ...updates }));
  };

  const updateMarket = (updates) => {
    setMarketData(prev => ({ ...prev, ...updates }));
  };

  const updateProperty = (updates) => {
    setPropertyData(prev => ({ ...prev, ...updates }));
  };

  const renderDetail = () => {
    if (!active) return null;

    switch (active.id) {
      case 'client-data':
        return (
          <ClientDataView
            data={active.data}
            onUpdateProfile={updateProfile}
            onUpdateMarket={updateMarket}
            onUpdateProperty={updateProperty}
            stateData={STATE_DATA}
          />
        );
      case 'down-payment':
        return <DownPaymentView data={active.data} profile={profile} />;
      case 'monthly-payment':
        return <MonthlyPaymentView data={active.data} />;
      case 'dti':
        return <DTIView data={active.data} profile={profile} />;
      case 'rent-vs-buy':
        return <RentVsBuyView data={active.data} />;
      case 'cash-reserves':
        return <CashReservesView data={active.data} />;
      case 'closing-costs':
        return <ClosingCostsView data={active.data} />;
      case 'repayment-strategy':
        return <RepaymentStrategyView data={active.data} />;
      case 'exit-strategy':
        return <ExitStrategyView data={active.data} />;
      case 'program-options':
        return <ProgramOptionsView data={active.data} />;
      case 'cost-to-waiting':
        return <CostToWaitingView data={active.data} />;
      case 'prepay-or-invest':
        return <PrepayOrInvestView data={active.data} />;
      // Phase 1 new calculators
      case 'emergency-runway':
        return <EmergencyRunwayView data={active.data} />;
      case 'stress-test':
        return <StressTestView data={active.data} />;
      // Phase 2 new calculators
      case 'payment-shock':
        return <PaymentShockView data={active.data} />;
      case 'lifestyle-fit':
        return <LifestyleFitView data={active.data} />;
      // Phase 3 new calculators - with scenario selector
      case 'break-even-horizon':
        return <BreakEvenHorizonView
          data={active.data}
          property={propertyData}
          market={marketData}
          onUpdate={(updates) => {
            if (updates.homePrice !== undefined || updates.downPaymentPct !== undefined) {
              updateProperty(updates);
            } else {
              updateMarket(updates);
            }
          }}
        />;
      case 'equity-velocity':
        return <EquityVelocityView
          data={active.data}
          property={propertyData}
          market={marketData}
          onUpdate={(updates) => {
            if (updates.homePrice !== undefined || updates.downPaymentPct !== undefined) {
              updateProperty(updates);
            } else {
              updateMarket(updates);
            }
          }}
        />;
      case 'tax-benefit':
        return <TaxBenefitView
          data={active.data}
          property={propertyData}
          market={marketData}
          onUpdate={(updates) => {
            if (updates.homePrice !== undefined || updates.downPaymentPct !== undefined) {
              updateProperty(updates);
            } else {
              updateMarket(updates);
            }
          }}
        />;
      case 'inflation-hedge':
        return <InflationHedgeView
          data={active.data}
          property={propertyData}
          market={marketData}
          onUpdate={(updates) => {
            if (updates.homePrice !== undefined || updates.downPaymentPct !== undefined) {
              updateProperty(updates);
            } else {
              updateMarket(updates);
            }
          }}
        />;
      case 'job-mobility':
        return <JobMobilityView
          data={active.data}
          property={propertyData}
          market={marketData}
          onUpdate={(updates) => {
            if (updates.homePrice !== undefined || updates.downPaymentPct !== undefined) {
              updateProperty(updates);
            } else {
              updateMarket(updates);
            }
          }}
        />;
      default:
        return null;
    }
  };

  // Close mobile menu when calculator changes
  const handleCalculatorChange = (calcId) => {
    setActiveCalculator(calcId);
    setMobileMenuOpen(false);
  };

  return (
    <div className="calculator-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <h1>{profile.name}'s Home Buying Analysis</h1>
        </div>
      </div>

      <div className="dashboard-body">
        {/* Mobile Overlay */}
        <div
          className={`mobile-overlay ${mobileMenuOpen ? 'active' : ''}`}
          onClick={() => setMobileMenuOpen(false)}
        />

        {/* Sidebar */}
        <div className={`calculator-sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}>
          {/* Client Data Button - Always at top */}
          <div className="sidebar-client-data">
            <button
              className={`nav-item client-data-btn ${activeCalculator === 'client-data' ? 'active' : ''}`}
              onClick={() => handleCalculatorChange('client-data')}
              style={{ '--calc-color': '#0ea5e9' }}
            >
              <div className="nav-content">
                <span className="nav-name">Client Data</span>
                <span className="nav-description">Edit inputs & assumptions</span>
              </div>
            </button>
          </div>

          {/* Phase Navigation */}
          <nav className="phase-navigation">
            {CALCULATOR_PHASES.map((phase) => (
              <div key={phase.id} className="phase-group" data-phase={phase.id}>
                <button
                  className={`phase-header ${expandedPhases.includes(phase.id) ? 'expanded' : ''}`}
                  onClick={() => togglePhase(phase.id)}
                  style={{
                    '--phase-color': phase.colorPrimary,
                    '--phase-bg': phase.colorBg,
                    '--phase-border': phase.colorBorder,
                  }}
                >
                  <span className="phase-icon">{phase.icon}</span>
                  <div className="phase-info">
                    <span className="phase-name">{phase.name}</span>
                    <span className="phase-subtitle">{phase.subtitle}</span>
                  </div>
                  <span className="phase-chevron">{expandedPhases.includes(phase.id) ? '▼' : '▶'}</span>
                </button>

                {expandedPhases.includes(phase.id) && (
                  <div className="phase-calculators">
                    {phase.calculators.map((calcId) => {
                      const calc = calculators.find(c => c.id === calcId);
                      if (!calc) return null;
                      return (
                        <button
                          key={calcId}
                          className={`phase-calc-item ${activeCalculator === calcId ? 'active' : ''}`}
                          onClick={() => handleCalculatorChange(calcId)}
                          style={{ '--phase-color': phase.colorPrimary }}
                        >
                          <span className="phase-calc-name">{calc.name}</span>
                          <span className="phase-calc-desc">{calc.shortDescription}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </div>

        {/* Main Content */}
        <div className="calculator-main">
          {renderDetail()}
        </div>
      </div>

      {/* Mobile Menu Toggle */}
      <button
        className="mobile-menu-toggle"
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        aria-label="Toggle menu"
      >
        {mobileMenuOpen ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        )}
      </button>

      {/* Footer */}
      <div className="dashboard-footer">
        <p>
          Calculations are estimates for informational purposes. Actual rates, payments, and costs may vary.
        </p>
      </div>
    </div>
  );
};

export default CalculatorDashboard;
