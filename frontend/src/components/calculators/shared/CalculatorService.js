/**
 * Calculator Service - Frontend mortgage calculations
 */

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
      marginalTaxRate = 0.22,
      standardDeduction = 14600,
    } = params;

    const annualInterest = loanAmount * (interestRate / 100) * 0.98;
    const annualPropertyTax = homePrice * taxRate;
    const totalDeductions = annualInterest + annualPropertyTax;
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
      appreciationRate = 0.03,
      rentIncreaseRate = 0.03,
      investmentReturn = 0.07,
      years = 5,
      initialSavings,
      closingCosts,
      taxSavingsMonthly = 0,
    } = params;

    const renterPath = [];
    const buyerPath = [];

    let renterNetWorth = initialSavings;
    let currentRent = monthlyRent;

    let buyerNetWorth = initialSavings - downPayment - closingCosts;
    let homeValue = homePrice;
    let remainingLoan = loanAmount;
    const monthlyRate = (interestRate / 100) / 12;

    for (let year = 1; year <= years; year++) {
      let yearlyRentPaid = 0;
      for (let month = 0; month < 12; month++) {
        yearlyRentPaid += currentRent;
        const monthlySavings = mortgagePayment - currentRent;
        if (monthlySavings > 0) {
          renterNetWorth += monthlySavings;
        }
      }
      renterNetWorth *= (1 + investmentReturn);
      currentRent *= (1 + rentIncreaseRate);

      homeValue *= (1 + appreciationRate);

      let principalPaidThisYear = 0;
      for (let month = 0; month < 12; month++) {
        const interestPayment = remainingLoan * monthlyRate;
        const principalPayment = piti.principalInterest - interestPayment;
        principalPaidThisYear += principalPayment;
        remainingLoan -= principalPayment;
      }

      buyerNetWorth += (taxSavingsMonthly * 12);

      const homeEquity = homeValue - remainingLoan;

      const monthlyExtraCost = mortgagePayment - monthlyRent * Math.pow(1 + rentIncreaseRate, year - 1);
      if (monthlyExtraCost < 0) {
        buyerNetWorth += Math.abs(monthlyExtraCost) * 12;
      }

      buyerNetWorth *= (1 + investmentReturn * 0.5);

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
