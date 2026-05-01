/**
 * CalculatorService — Mortgage financial calculation engine.
 *
 * All methods are pure, client-side calculations with no API calls.
 * Used by the CalculatorDashboard and any component that needs
 * PITI, DTI, closing-cost, amortization, PMI, or tax-benefit math.
 *
 * IMPORTANT: Do NOT change calculation logic. These formulas drive
 * lending-decision tools that loan officers rely on daily.
 */

// ============================================================================
// FORMATTING UTILITIES
// ============================================================================

export const formatCurrency = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

export const formatCurrencyFull = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
};

export const formatPercent = (value, decimals = 1) => {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(decimals)}%`;
};

// ============================================================================
// STATE / COUNTY TAX AND INSURANCE RATES
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

export default CalculatorService;
