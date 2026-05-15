/**
 * Build calculator data from profile, market, and property inputs.
 * Each calculator definition computes its data upfront for rendering.
 */

import CalculatorService from './CalculatorService';
import { formatCurrency, formatCurrencyFull } from './utils';
import { DEFAULT_PROPERTY } from './constants';

const buildCalculators = (profile, market, propertyData = DEFAULT_PROPERTY) => {
  const monthlyIncome = profile.monthlyIncome;

  const conservativePayment = monthlyIncome * 0.25;
  const moderatePayment = monthlyIncome * 0.28;

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
    buildDownPaymentCalc(homePrices, downPaymentScenarios, profile),
    buildMonthlyPaymentCalc(homePrices, downPaymentScenarios, market),
    buildDTICalc(monthlyIncome, baselinePiti, profile, dti),
    buildRentVsBuyCalc(homePrices, market, profile, baselinePiti, fiveYearRent, fiveYearEquity),
    buildCashReservesCalc(homePrices, downPaymentScenarios, profile, monthlyIncome, market),
    buildClosingCostsCalc(homePrices, market, profile),
    buildRepaymentStrategyCalc(homePrices, market, monthlyIncome),
    buildExitStrategyCalc(homePrices, market, baselinePiti, profile),
    buildProgramOptionsCalc(homePrices, market, profile),
    buildCostToWaitingCalc(homePrices, market, profile, monthlyIncome),
    buildPrepayOrInvestCalc(homePrices, market),
    buildEmergencyRunwayCalc(homePrices, profile, baselinePiti, monthlyIncome),
    buildStressTestCalc(homePrices, market, profile, baselinePiti, dti, monthlyIncome),
    buildPaymentShockCalc(baselinePiti, propertyData),
    buildLifestyleFitCalc(homePrices, profile, baselinePiti, monthlyIncome),
    buildBreakEvenCalc(homePrices, profile, baselinePiti),
    buildEquityVelocityCalc(homePrices),
    buildTaxBenefitCalc(homePrices, market, profile, baselinePiti),
    buildInflationHedgeCalc(profile, homePrices, baselinePiti),
    buildJobMobilityCalc(homePrices, profile, baselinePiti),
  ];
};

function buildDownPaymentCalc(homePrices, downPaymentScenarios, profile) {
  return {
    id: 'down-payment',
    name: 'Down Payment Options',
    color: '#3b82f6',
    shortDescription: 'Compare 3%, 5%, and 10% down',
    data: {
      homePrice: homePrices.baseline,
      scenarios: downPaymentScenarios,
      savings: profile.savings,
    },
  };
}

function buildMonthlyPaymentCalc(homePrices, downPaymentScenarios, market) {
  return {
    id: 'monthly-payment',
    name: 'Monthly Payment (PITI)',
    color: '#B8924A',
    shortDescription: 'Compare payments by down payment',
    data: {
      homePrice: homePrices.baseline,
      scenarios: downPaymentScenarios,
      rate: market.interestRate,
      term: market.termYears,
    },
  };
}

function buildDTICalc(monthlyIncome, baselinePiti, profile, dti) {
  return {
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
  };
}

function buildRentVsBuyCalc(homePrices, market, profile, baselinePiti, fiveYearRent, fiveYearEquity) {
  const loanAmount = homePrices.baseline * 0.95;
  const downPayment = homePrices.baseline * 0.05;
  const closingCosts = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;
  const taxBenefits = CalculatorService.calculateTaxBenefits({
    loanAmount,
    interestRate: market.interestRate,
    homePrice: homePrices.baseline,
  });
  const effectiveMonthlyPayment = baselinePiti.total - taxBenefits.monthlyTaxSavings;
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
  const monthlyInterest = loanAmount * (market.interestRate / 100) / 12;
  const trueMonthlyCost = monthlyInterest + baselinePiti.propertyTax + baselinePiti.insurance + baselinePiti.pmi - taxBenefits.monthlyTaxSavings;

  return {
    id: 'rent-vs-buy',
    name: 'Rent vs. Buy',
    color: '#ec4899',
    shortDescription: 'True cost comparison with tax benefits',
    data: {
      currentRent: profile.currentRent,
      mortgagePayment: baselinePiti.total,
      monthlyDifference: baselinePiti.total - profile.currentRent,
      fiveYearRent,
      fiveYearEquity,
      firstYearEquity: baselinePiti.principalInterest * 12 * 0.18,
      breakEvenYears: 2.1,
      taxBenefits,
      effectiveMonthlyPayment,
      trueMonthlyCost,
      principalBuildup: baselinePiti.principalInterest - monthlyInterest,
      netWorthProjection,
      homePrice: homePrices.baseline,
      downPayment,
      loanAmount,
    },
  };
}

function buildCashReservesCalc(homePrices, downPaymentScenarios, profile, monthlyIncome, market) {
  const monthlyExpenses = monthlyIncome * 0.5;
  const emergencyFundTarget = monthlyExpenses * 3;
  const comfortFundTarget = monthlyExpenses * 6;

  const scoredScenarios = downPaymentScenarios.map((s) => {
    const monthsReserve = s.cashRemaining / monthlyExpenses;
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

    const pmiSavings = s.ltv <= 80 ? 25 : (97 - s.ltv) * 1.5;
    suitabilityScore += pmiSavings;
    factors.push({
      name: 'Monthly Payment', score: Math.round(pmiSavings), max: 25,
      status: s.ltv <= 80 ? 'excellent' : s.ltv <= 90 ? 'good' : 'fair',
      note: s.ltv <= 80 ? 'No PMI required' : `PMI: ${formatCurrencyFull(s.piti.pmi)}/mo`,
    });

    const flexScore = Math.min(20, (s.cashRemaining / 5000) * 10);
    suitabilityScore += Math.max(0, flexScore);
    factors.push({
      name: 'Financial Flexibility', score: Math.round(Math.max(0, flexScore)), max: 20,
      status: flexScore >= 15 ? 'excellent' : flexScore >= 10 ? 'good' : flexScore >= 5 ? 'fair' : 'tight',
      note: s.cashRemaining >= 5000 ? 'Room for unexpected costs' : 'Limited cushion',
    });

    const equityScore = Math.min(15, s.pct * 100);
    suitabilityScore += equityScore;
    factors.push({
      name: 'Starting Equity', score: Math.round(equityScore), max: 15,
      status: s.pct >= 0.10 ? 'excellent' : s.pct >= 0.05 ? 'good' : 'fair',
      note: `${(s.pct * 100).toFixed(0)}% equity on day 1`,
    });

    let fitLevel, fitDescription;
    if (suitabilityScore >= 80) { fitLevel = 'perfect'; fitDescription = 'Tailored Fit'; }
    else if (suitabilityScore >= 60) { fitLevel = 'good'; fitDescription = 'Good Fit'; }
    else if (suitabilityScore >= 40) { fitLevel = 'acceptable'; fitDescription = 'Acceptable'; }
    else { fitLevel = 'poor'; fitDescription = 'Poor Fit'; }

    return { ...s, monthsReserve, suitabilityScore: Math.round(suitabilityScore), factors, fitLevel, fitDescription };
  });

  const targetReserve = emergencyFundTarget;
  const baseClosingCosts = CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total;
  const optimalDownPayment = Math.max(
    homePrices.baseline * 0.03,
    Math.min(profile.savings - targetReserve - baseClosingCosts, homePrices.baseline * 0.20)
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
    label: 'Tailored Fit', pct: optimalPct, downPayment: optimalDownPayment,
    loanAmount: optimalLoanAmount, closingCosts: optimalClosingCosts,
    cashRemaining: optimalCashRemaining, monthsReserve: optimalCashRemaining / monthlyExpenses,
    piti: optimalPiti, ltv: (optimalLoanAmount / homePrices.baseline) * 100, isCustom: true,
  };

  const bestStandard = scoredScenarios.reduce((best, s) =>
    s.suitabilityScore > best.suitabilityScore ? s : best
  );

  return {
    id: 'cash-reserves',
    name: 'Cash Reserves',
    color: '#06b6d4',
    shortDescription: 'Your tailored down payment fit',
    data: {
      savings: profile.savings, homePrice: homePrices.baseline,
      monthlyExpenses, emergencyFundTarget, comfortFundTarget,
      scenarios: scoredScenarios, tailoredOption, bestStandard, monthlyIncome,
    },
  };
}

function buildClosingCostsCalc(homePrices, market, profile) {
  const loanAmount = homePrices.baseline * 0.95;
  const closingCosts = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline, 'CA', market.interestRate);
  return {
    id: 'closing-costs',
    name: 'Closing Costs',
    color: '#64748b',
    shortDescription: 'Itemized costs to close your loan',
    data: {
      homePrice: homePrices.baseline, loanAmount,
      downPayment: homePrices.baseline * 0.05, closingCosts,
      totalCashNeeded: (homePrices.baseline * 0.05) + closingCosts.total,
      savings: profile.savings,
    },
  };
}

function buildRepaymentStrategyCalc(homePrices, market, monthlyIncome) {
  const loanAmount = homePrices.baseline * 0.95;
  const monthlyRate = market.interestRate / 100 / 12;
  const basePayment = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate, 30);

  const standard30 = {
    term: 30, payment: basePayment,
    totalPaid: basePayment * 360,
    totalInterest: (basePayment * 360) - loanAmount,
  };

  const calcExtra = (extraAmount) => {
    const extraPayment = basePayment + extraAmount;
    let balance = loanAmount, months = 0, totalInterest = 0;
    while (balance > 0 && months < 360) {
      const interestPayment = balance * monthlyRate;
      const principalPayment = Math.min(extraPayment - interestPayment, balance);
      totalInterest += interestPayment;
      balance -= principalPayment;
      months++;
    }
    return {
      extraMonthly: extraAmount, payment: extraPayment, months,
      years: (months / 12).toFixed(1), totalInterest,
      interestSaved: standard30.totalInterest - totalInterest,
      yearsSaved: 30 - (months / 12),
    };
  };

  const extra200 = calcExtra(200);
  const extra500 = calcExtra(500);

  // Biweekly
  const biweeklyPayment = basePayment / 2;
  let balance = loanAmount, biweeklyPeriods = 0, totalInterestBiweekly = 0;
  const biweeklyRate = market.interestRate / 100 / 26;
  while (balance > 0 && biweeklyPeriods < 780) {
    const interestPayment = balance * biweeklyRate;
    const principalPayment = Math.min(biweeklyPayment - interestPayment, balance);
    totalInterestBiweekly += interestPayment;
    balance -= principalPayment;
    biweeklyPeriods++;
  }
  const biweekly = {
    payment: biweeklyPayment, frequency: 'Every 2 weeks',
    months: Math.round(biweeklyPeriods / 2.17), years: (biweeklyPeriods / 26).toFixed(1),
    totalInterest: totalInterestBiweekly,
    interestSaved: standard30.totalInterest - totalInterestBiweekly,
    yearsSaved: 30 - (biweeklyPeriods / 26),
  };

  // 15-year
  const payment15 = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate - 0.5, 15);
  const fifteenYear = {
    term: 15, rate: market.interestRate - 0.5, payment: payment15,
    totalPaid: payment15 * 180, totalInterest: (payment15 * 180) - loanAmount,
    interestSaved: standard30.totalInterest - ((payment15 * 180) - loanAmount),
    extraMonthlyNeeded: payment15 - basePayment,
  };

  return {
    id: 'repayment-strategy', name: 'Repayment Strategy', color: '#2D7A52',
    shortDescription: 'Payoff options & wealth building',
    data: { loanAmount, interestRate: market.interestRate, standard30, extra200, extra500, biweekly, fifteenYear, monthlyIncome },
  };
}

function buildExitStrategyCalc(homePrices, market, baselinePiti, profile) {
  const loanAmount = homePrices.baseline * 0.95;
  const downPayment = homePrices.baseline * 0.05;
  const closingCostsBuy = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;
  const monthlyRate = market.interestRate / 100 / 12;

  const equityTimeline = [1, 2, 3, 5, 7, 10].map(year => {
    const futureHomeValue = homePrices.baseline * Math.pow(1.03, year);
    let balance = loanAmount;
    const payment = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate, 30);
    for (let m = 0; m < year * 12; m++) {
      const interest = balance * monthlyRate;
      balance -= (payment - interest);
    }
    const equity = futureHomeValue - balance;
    const equityPercent = (equity / futureHomeValue) * 100;
    const sellingCosts = futureHomeValue * 0.07;
    const netProceeds = futureHomeValue - balance - sellingCosts;
    const totalInvested = downPayment + closingCostsBuy;
    const roi = ((netProceeds - totalInvested) / totalInvested) * 100;
    return { year, homeValue: futureHomeValue, remainingLoan: balance, equity, equityPercent, sellingCosts, netProceeds, roi, canSellProfitably: netProceeds > totalInvested };
  });

  const refinanceScenarios = [
    { name: 'Rate drops 1%', newRate: market.interestRate - 1 },
    { name: 'Rate drops 2%', newRate: market.interestRate - 2 },
  ].map(scenario => {
    const currentPayment = CalculatorService.calculateMonthlyPI(loanAmount, market.interestRate, 30);
    const newPayment = CalculatorService.calculateMonthlyPI(loanAmount, scenario.newRate, 30);
    const monthlySavings = currentPayment - newPayment;
    const refinanceCosts = loanAmount * 0.02;
    const breakEvenMonths = refinanceCosts / monthlySavings;
    return { ...scenario, currentPayment, newPayment, monthlySavings, refinanceCosts, breakEvenMonths: Math.round(breakEvenMonths), worthIt: breakEvenMonths < 36 };
  });

  const estimatedRent = homePrices.baseline * 0.006;
  const rentalScenario = {
    estimatedRent, monthlyMortgage: baselinePiti.total,
    cashFlow: estimatedRent - baselinePiti.total,
    isPositive: (estimatedRent - baselinePiti.total) > 0,
    capRate: ((estimatedRent * 12 - (baselinePiti.propertyTax + baselinePiti.insurance) * 12) / homePrices.baseline) * 100,
  };

  return {
    id: 'exit-strategy', name: 'Exit Strategy', color: '#B8924A',
    shortDescription: 'Future scenarios & flexibility',
    data: { homePrice: homePrices.baseline, loanAmount, downPayment, closingCostsBuy, interestRate: market.interestRate, equityTimeline, refinanceScenarios, rentalScenario, currentPayment: baselinePiti.total },
  };
}

function buildProgramOptionsCalc(homePrices, market, profile) {
  const downPayment5 = homePrices.baseline * 0.05;
  const downPayment3 = homePrices.baseline * 0.03;
  const downPayment35 = homePrices.baseline * 0.035;

  const conventionalPiti = CalculatorService.calculatePITI({ loanAmount: homePrices.baseline * 0.95, interestRate: market.interestRate, homePrice: homePrices.baseline, creditScore: profile.creditScore });
  const fhaPiti = CalculatorService.calculatePITI({ loanAmount: homePrices.baseline * 0.965, interestRate: market.interestRate + 0.125, homePrice: homePrices.baseline, creditScore: profile.creditScore });
  const fhaMipUpfront = homePrices.baseline * 0.965 * 0.0175;
  const fhaMipMonthly = (homePrices.baseline * 0.965 * 0.0055) / 12;
  const conventional3Piti = CalculatorService.calculatePITI({ loanAmount: homePrices.baseline * 0.97, interestRate: market.interestRate, homePrice: homePrices.baseline, creditScore: profile.creditScore });

  const programs = [
    {
      id: 'conventional-5', name: 'Conventional 5% Down', lender: 'Fannie Mae / Freddie Mac', category: 'conventional',
      downPaymentPct: 5, downPayment: downPayment5, loanAmount: homePrices.baseline * 0.95,
      interestRate: market.interestRate, monthlyPayment: conventionalPiti.total, pmi: conventionalPiti.pmi,
      pmiRemovable: true,
      closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total,
      totalCashNeeded: downPayment5 + CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total,
      creditScoreMin: 620, dtiMax: 45,
      pros: ['PMI cancels automatically at 78% LTV', 'No upfront mortgage insurance fee', 'More competitive rates with good credit', 'Flexible property types allowed', 'No income limits in most areas'],
      cons: ['Higher credit score requirements', 'Higher PMI rates if credit is lower', 'Stricter debt-to-income requirements'],
      bestFor: 'Buyers with good credit who want PMI to go away',
      aiInsight: `With your ${profile.creditScore} credit score, you qualify for competitive conventional rates. Your PMI of ${formatCurrencyFull(conventionalPiti.pmi)}/month will automatically cancel once you reach 22% equity (roughly 7-8 years), or you can request removal at 20% equity.`,
      suitabilityScore: profile.creditScore >= 700 ? 92 : profile.creditScore >= 680 ? 78 : 65,
    },
    {
      id: 'conventional-3', name: 'Conventional 3% Down', lender: 'Fannie Mae HomeReady / Freddie Mac Home Possible', category: 'conventional',
      downPaymentPct: 3, downPayment: downPayment3, loanAmount: homePrices.baseline * 0.97,
      interestRate: market.interestRate, monthlyPayment: conventional3Piti.total, pmi: conventional3Piti.pmi,
      pmiRemovable: true,
      closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline * 0.97, homePrices.baseline).total,
      totalCashNeeded: downPayment3 + CalculatorService.calculateClosingCosts(homePrices.baseline * 0.97, homePrices.baseline).total,
      creditScoreMin: 620, dtiMax: 45,
      pros: ['Only 3% down payment required', 'PMI still cancellable at 20% equity', 'Income limits may provide rate discounts', 'Homebuyer education may reduce PMI', 'Gift funds allowed for entire down payment'],
      cons: ['Higher monthly payment due to larger loan', 'Higher PMI due to higher LTV', 'May have income limits in some areas', 'Takes longer to build equity'],
      bestFor: 'First-time buyers who want to preserve cash',
      aiInsight: `This program maximizes your cash reserves. With only ${formatCurrency(downPayment3)} down, you'd keep ${formatCurrency(profile.savings - downPayment3 - CalculatorService.calculateClosingCosts(homePrices.baseline * 0.97, homePrices.baseline).total)} in savings for emergencies. The higher PMI is a trade-off for financial flexibility.`,
      suitabilityScore: profile.savings < 30000 ? 88 : 72,
    },
    {
      id: 'fha', name: 'FHA Loan', lender: 'Federal Housing Administration', category: 'government',
      downPaymentPct: 3.5, downPayment: downPayment35, loanAmount: homePrices.baseline * 0.965,
      interestRate: market.interestRate + 0.125,
      monthlyPayment: fhaPiti.total + fhaMipMonthly - fhaPiti.pmi,
      pmi: fhaMipMonthly, pmiRemovable: false, mipUpfront: fhaMipUpfront,
      closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline * 0.965, homePrices.baseline).total + fhaMipUpfront,
      totalCashNeeded: downPayment35 + CalculatorService.calculateClosingCosts(homePrices.baseline * 0.965, homePrices.baseline).total,
      creditScoreMin: 580, dtiMax: 50,
      pros: ['Lower credit score requirements (580+)', 'Only 3.5% down payment', 'More lenient DTI limits (up to 50%)', 'Seller can contribute up to 6% toward closing', 'Accepts non-traditional credit history'],
      cons: ['MIP required for life of loan (if <10% down)', '1.75% upfront MIP added to loan balance', 'Property must meet FHA standards', 'Loan limits apply (varies by county)', 'Must refinance to remove mortgage insurance'],
      bestFor: 'Buyers with lower credit scores or limited savings',
      aiInsight: `FHA could work for you, but with your ${profile.creditScore} credit score, conventional may be better. The FHA upfront MIP of ${formatCurrency(fhaMipUpfront)} gets added to your loan, and unlike conventional PMI, FHA mortgage insurance never goes away unless you refinance.`,
      suitabilityScore: profile.creditScore < 680 ? 85 : 58,
    },
    {
      id: 'va', name: 'VA Loan', lender: 'Department of Veterans Affairs', category: 'government',
      downPaymentPct: 0, downPayment: 0, loanAmount: homePrices.baseline,
      interestRate: market.interestRate - 0.25,
      monthlyPayment: CalculatorService.calculatePITI({ loanAmount: homePrices.baseline, interestRate: market.interestRate - 0.25, homePrice: homePrices.baseline, creditScore: profile.creditScore }).total - CalculatorService.calculatePITI({ loanAmount: homePrices.baseline, interestRate: market.interestRate - 0.25, homePrice: homePrices.baseline, creditScore: profile.creditScore }).pmi,
      pmi: 0, pmiRemovable: null, fundingFee: homePrices.baseline * 0.023,
      closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
      totalCashNeeded: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
      creditScoreMin: 620, dtiMax: 60,
      pros: ['No down payment required', 'No monthly mortgage insurance', 'Lower interest rates than conventional', 'More flexible DTI requirements', 'No prepayment penalties', 'Seller can pay all closing costs'],
      cons: ['Must be veteran, active duty, or eligible spouse', 'VA funding fee (2.3% first use, can be financed)', 'Property must meet VA minimum standards', 'Primary residence only'],
      bestFor: 'Veterans and active military wanting best terms',
      aiInsight: `If you have VA eligibility, this is likely your best option. Zero down payment, no PMI, and typically the lowest rates available. The 2.3% funding fee (${formatCurrency(homePrices.baseline * 0.023)}) can be rolled into the loan if you prefer to preserve cash.`,
      suitabilityScore: 0, requiresEligibility: true, eligibilityNote: 'Requires military service or eligible spouse status',
    },
    {
      id: 'usda', name: 'USDA Loan', lender: 'US Department of Agriculture', category: 'government',
      downPaymentPct: 0, downPayment: 0, loanAmount: homePrices.baseline,
      interestRate: market.interestRate - 0.125,
      monthlyPayment: CalculatorService.calculatePITI({ loanAmount: homePrices.baseline, interestRate: market.interestRate - 0.125, homePrice: homePrices.baseline, creditScore: profile.creditScore }).total - CalculatorService.calculatePITI({ loanAmount: homePrices.baseline, interestRate: market.interestRate - 0.125, homePrice: homePrices.baseline, creditScore: profile.creditScore }).pmi + (homePrices.baseline * 0.0035 / 12),
      pmi: homePrices.baseline * 0.0035 / 12, pmiRemovable: false, guaranteeFee: homePrices.baseline * 0.01,
      closingCosts: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
      totalCashNeeded: CalculatorService.calculateClosingCosts(homePrices.baseline, homePrices.baseline).total,
      creditScoreMin: 640, dtiMax: 41,
      pros: ['No down payment required', 'Lower guarantee fee than FHA MIP', 'Competitive interest rates', 'Low monthly guarantee fee (0.35%)', 'Seller can contribute toward closing costs'],
      cons: ['Property must be in eligible rural area', 'Income limits apply (115% of area median)', 'Primary residence only', 'Upfront guarantee fee (1%)', 'Geographic restrictions'],
      bestFor: 'Buyers in rural/suburban areas under income limits',
      aiInsight: `USDA loans offer zero down, but the property must be in an eligible area (many suburbs qualify). With your income of ${formatCurrency(profile.annualIncome)}, you'd need to verify you're under the area income limit for your county.`,
      suitabilityScore: 0, requiresEligibility: true, eligibilityNote: 'Requires eligible rural location and income under area limit',
    },
  ];

  const eligiblePrograms = programs.filter(p => !p.requiresEligibility);
  const bestMatch = eligiblePrograms.reduce((best, p) => p.suitabilityScore > best.suitabilityScore ? p : best, eligiblePrograms[0]);

  return {
    id: 'program-options', name: 'Program Options', color: '#B8924A',
    shortDescription: 'Compare loan programs for you',
    data: {
      homePrice: homePrices.baseline, programs, bestMatch,
      profile: { creditScore: profile.creditScore, income: profile.annualIncome, savings: profile.savings, monthlyDebts: profile.monthlyDebts, isFirstTimeBuyer: true },
    },
  };
}

function buildCostToWaitingCalc(homePrices, market, profile, monthlyIncome) {
  return {
    id: 'cost-to-waiting', name: 'Cost of Waiting', color: '#f97316',
    shortDescription: 'What delay really costs you',
    data: {
      homePrice: homePrices.baseline, currentRent: profile.currentRent,
      interestRate: market.interestRate, downPaymentPct: 5,
      savings: profile.savings, monthlyIncome,
      homeAppreciationRate: 4.0, rateIncreasePerYear: 0.5, rentIncreaseRate: 3.0,
    },
  };
}

function buildPrepayOrInvestCalc(homePrices, market) {
  return {
    id: 'prepay-or-invest', name: 'Prepay or Invest', color: '#14b8a6',
    shortDescription: 'Extra payments vs market returns',
    data: {
      loanAmount: homePrices.baseline * 0.95, interestRate: market.interestRate,
      termYears: market.termYears, monthlyExtraCash: 500,
      estimatedMarketReturn: 7.0, currentEquity: homePrices.baseline * 0.05,
      homePrice: homePrices.baseline,
    },
  };
}

function buildEmergencyRunwayCalc(homePrices, profile, baselinePiti, monthlyIncome) {
  const downPayment = homePrices.baseline * 0.05;
  const closingCosts = CalculatorService.calculateClosingCosts(homePrices.baseline * 0.95, homePrices.baseline).total;
  const postCloseSavings = profile.savings - downPayment - closingCosts;
  const monthlyExpenses = monthlyIncome * 0.5;
  const totalMonthlyBurn = baselinePiti.total + monthlyExpenses;

  const scenarios = [
    { name: 'Full Income', monthlyBurn: totalMonthlyBurn - monthlyIncome, months: postCloseSavings > 0 ? Infinity : 0, status: 'safe' },
    { name: 'Job Loss (0% income)', monthlyBurn: totalMonthlyBurn, months: postCloseSavings / totalMonthlyBurn, status: postCloseSavings / totalMonthlyBurn >= 6 ? 'safe' : postCloseSavings / totalMonthlyBurn >= 3 ? 'caution' : 'danger' },
    { name: 'Reduced Income (50%)', monthlyBurn: totalMonthlyBurn - (monthlyIncome * 0.5), months: postCloseSavings / (totalMonthlyBurn - (monthlyIncome * 0.5)), status: 'caution' },
    { name: 'After Major Repair ($10k)', monthlyBurn: totalMonthlyBurn, months: (postCloseSavings - 10000) / totalMonthlyBurn, status: (postCloseSavings - 10000) / totalMonthlyBurn >= 3 ? 'caution' : 'danger' },
  ];

  return {
    id: 'emergency-runway', name: 'Emergency Runway', color: '#0891b2',
    shortDescription: 'Months of survival after closing',
    data: {
      savings: profile.savings, downPayment, closingCosts, postCloseSavings,
      monthlyExpenses, piti: baselinePiti.total, totalMonthlyBurn, scenarios,
      recommendedReserve: monthlyExpenses * 6,
      riskLevel: postCloseSavings >= monthlyExpenses * 6 ? 'low' : postCloseSavings >= monthlyExpenses * 3 ? 'moderate' : 'high',
    },
  };
}

function buildStressTestCalc(homePrices, market, profile, baselinePiti, dti, monthlyIncome) {
  const scenarios = [
    { name: 'Rate Increase +2%', trigger: 'ARM adjustment or refinance', newPayment: CalculatorService.calculatePITI({ loanAmount: homePrices.baseline * 0.95, interestRate: market.interestRate + 2, homePrice: homePrices.baseline, creditScore: profile.creditScore }).total, currentPayment: baselinePiti.total, impact: 0, newDti: 0, survivable: true },
    { name: 'Property Tax +20%', trigger: 'Reassessment', newPayment: baselinePiti.total + (baselinePiti.propertyTax * 0.2), currentPayment: baselinePiti.total, impact: baselinePiti.propertyTax * 0.2, newDti: 0, survivable: true },
    { name: 'Insurance Spike +30%', trigger: 'Market conditions', newPayment: baselinePiti.total + (baselinePiti.insurance * 0.3), currentPayment: baselinePiti.total, impact: baselinePiti.insurance * 0.3, newDti: 0, survivable: true },
    { name: 'Income Reduction -20%', trigger: 'Job change, reduced hours', newPayment: baselinePiti.total, currentPayment: baselinePiti.total, impact: monthlyIncome * 0.2, newDti: 0, survivable: true },
    { name: 'Combined Stress', trigger: 'Multiple events', newPayment: baselinePiti.total + (baselinePiti.propertyTax * 0.1) + (baselinePiti.insurance * 0.15), currentPayment: baselinePiti.total, impact: 0, newDti: 0, survivable: true },
  ];

  scenarios.forEach(s => {
    const effectiveIncome = s.name.includes('Income') ? monthlyIncome * 0.8 : monthlyIncome;
    s.newDti = ((s.newPayment + profile.monthlyDebts) / effectiveIncome) * 100;
    s.survivable = s.newDti <= 50;
    s.impact = s.newPayment - s.currentPayment;
  });

  const passCount = scenarios.filter(s => s.survivable).length;

  return {
    id: 'stress-test', name: 'Life Happens Stress Test', color: '#dc2626',
    shortDescription: 'Survive income drops & expense spikes',
    data: {
      baseline: { piti: baselinePiti.total, dti: dti.backEnd },
      scenarios, monthlyIncome, monthlyDebts: profile.monthlyDebts,
      resilienceScore: (passCount / scenarios.length) * 100,
      passCount, totalScenarios: scenarios.length,
    },
  };
}

function buildPaymentShockCalc(baselinePiti, propertyData) {
  const projections = Array.from({ length: 10 }, (_, year) => {
    const taxMultiplier = Math.pow(1.03, year);
    const insuranceMultiplier = Math.pow(1.04, year);
    const hoaMultiplier = Math.pow(1.05, year);
    const projectedTax = baselinePiti.propertyTax * taxMultiplier;
    const projectedInsurance = baselinePiti.insurance * insuranceMultiplier;
    const projectedHoa = (propertyData.hoaMonthly || 0) * hoaMultiplier;
    const projectedPmi = year >= 7 ? 0 : baselinePiti.pmi;
    const total = baselinePiti.principalInterest + projectedTax + projectedInsurance + projectedHoa + projectedPmi;
    return {
      year: year + 1, principalInterest: baselinePiti.principalInterest,
      propertyTax: projectedTax, insurance: projectedInsurance,
      hoa: projectedHoa, pmi: projectedPmi, total,
      increase: total - baselinePiti.total,
      percentIncrease: ((total - baselinePiti.total) / baselinePiti.total) * 100,
    };
  });

  const maxPayment = Math.max(...projections.map(p => p.total));
  return {
    id: 'payment-shock', name: 'Payment Shock Forecast', color: '#ea580c',
    shortDescription: 'Future payment increases',
    data: {
      current: baselinePiti, projections, maxPayment,
      shockIndex: ((maxPayment - baselinePiti.total) / baselinePiti.total) * 100,
      peakYear: projections.findIndex(p => p.total === maxPayment) + 1,
    },
  };
}

function buildLifestyleFitCalc(homePrices, profile, baselinePiti, monthlyIncome) {
  const currentBudget = {
    housing: profile.currentRent, utilities: profile.budget?.utilities || 200,
    food: profile.budget?.food || 500, transportation: profile.budget?.transportation || 350,
    healthcare: profile.budget?.healthcare || 100, entertainment: profile.budget?.entertainment || 200,
    savings: profile.budget?.savings || 400, other: profile.budget?.other || 250,
    debts: profile.monthlyDebts,
  };
  currentBudget.total = Object.values(currentBudget).reduce((a, b) => a + b, 0);

  const maintenanceReserve = (homePrices.baseline * 0.01) / 12;
  const homeownerBudget = {
    housing: baselinePiti.total, utilities: (profile.budget?.utilities || 200) * 1.4,
    maintenance: maintenanceReserve, food: profile.budget?.food || 500,
    transportation: profile.budget?.transportation || 350, healthcare: profile.budget?.healthcare || 100,
    entertainment: (profile.budget?.entertainment || 200) * 0.8,
    savings: Math.max(0, (profile.budget?.savings || 400) - 150),
    other: profile.budget?.other || 250, debts: profile.monthlyDebts,
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
    id: 'lifestyle-fit', name: 'Lifestyle Fit Index', color: '#B8924A',
    shortDescription: 'Post-purchase spending power',
    data: {
      monthlyIncome, currentBudget, homeownerBudget,
      monthlySqueeze: homeownerBudget.total - currentBudget.total,
      discretionaryIncome, fitScore, fitLevel,
      adjustments: [
        { category: 'Housing', change: baselinePiti.total - profile.currentRent },
        { category: 'Utilities', change: homeownerBudget.utilities - currentBudget.utilities },
        { category: 'Maintenance', change: maintenanceReserve },
        { category: 'Entertainment', change: homeownerBudget.entertainment - currentBudget.entertainment },
        { category: 'Savings', change: homeownerBudget.savings - currentBudget.savings },
      ],
    },
  };
}

function buildBreakEvenCalc(homePrices, profile, baselinePiti) {
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
    const yearlyRent = currentRent * 12;
    cumulativeRenterCost += yearlyRent;
    const renterInvestment = initialInvestment * Math.pow(1.07, year);
    homeValue = homePrices.baseline * Math.pow(1.03, year);
    const yearlyPiti = baselinePiti.total * 12;
    const maintenance = homeValue * 0.01;
    cumulativeBuyerCost += yearlyPiti + maintenance;
    const yearlyPrincipal = loanAmount * (year <= 5 ? 0.018 : year <= 10 ? 0.022 : 0.028);
    balance = Math.max(0, balance - yearlyPrincipal);
    const equity = homeValue - balance;
    const netRenter = renterInvestment - cumulativeRenterCost;
    const netBuyer = equity - cumulativeBuyerCost + initialInvestment;
    const buyerAdvantage = netBuyer - netRenter;
    comparison.push({ year, renterCost: cumulativeRenterCost, renterInvestment, netRenter, buyerCost: cumulativeBuyerCost, homeValue, equity, netBuyer, buyerAdvantage });
    if (!breakEvenYear && buyerAdvantage > 0) breakEvenYear = year;
    currentRent *= 1.03;
  }

  return {
    id: 'break-even-horizon', name: 'Break-Even Horizon', color: '#0d9488',
    shortDescription: 'Years to beat renting',
    data: { initialInvestment, comparison, breakEvenYear: breakEvenYear || '>10', assumptions: { homeAppreciation: 3, rentIncrease: 3, investmentReturn: 7, maintenance: 1 } },
  };
}

function buildEquityVelocityCalc(homePrices) {
  const downPayment = homePrices.baseline * 0.05;
  const loanAmount = homePrices.baseline * 0.95;
  const timeline = [];
  let balance = loanAmount;

  for (let year = 1; year <= 15; year++) {
    const homeValue = homePrices.baseline * Math.pow(1.03, year);
    const principalRate = year <= 5 ? 0.018 : year <= 10 ? 0.022 : 0.028;
    const yearlyPrincipal = loanAmount * principalRate;
    balance = Math.max(0, balance - yearlyPrincipal);
    const equityFromPrincipal = loanAmount - balance;
    const equityFromAppreciation = homeValue - homePrices.baseline;
    const totalEquity = downPayment + equityFromPrincipal + equityFromAppreciation;
    const prevEquity = year > 1 ? timeline[year - 2].totalEquity : downPayment;
    const velocityThisYear = totalEquity - prevEquity;
    const roi = ((totalEquity - downPayment) / downPayment) * 100;
    timeline.push({ year, homeValue, loanBalance: balance, equityFromDownPayment: downPayment, equityFromPrincipal, equityFromAppreciation, totalEquity, velocityThisYear, roi });
  }

  const peakVelocityYear = timeline.reduce((max, t) => t.velocityThisYear > (max?.velocityThisYear || 0) ? t : max, timeline[0]);

  return {
    id: 'equity-velocity', name: 'Equity Velocity', color: '#2D7A52',
    shortDescription: 'Wealth accumulation speed',
    data: { initialEquity: downPayment, timeline, year5Equity: timeline[4].totalEquity, year10Equity: timeline[9].totalEquity, peakVelocityYear: peakVelocityYear.year, peakVelocity: peakVelocityYear.velocityThisYear },
  };
}

function buildTaxBenefitCalc(homePrices, market, profile, baselinePiti) {
  const loanAmount = homePrices.baseline * 0.95;
  const annualPropertyTax = homePrices.baseline * (market.taxRate || 0.0107);
  const marginalRate = profile.annualIncome >= 100525 ? 0.24 : profile.annualIncome >= 47150 ? 0.22 : profile.annualIncome >= 11600 ? 0.12 : 0.10;
  const standardDeduction = 14600;

  const yearlyBenefits = Array.from({ length: 10 }, (_, year) => {
    const interestRate = (10 - year) / 10;
    const yearlyInterest = loanAmount * (market.interestRate / 100) * interestRate;
    const propertyTaxDeduction = Math.min(annualPropertyTax, 10000);
    const totalDeductions = yearlyInterest + propertyTaxDeduction;
    const aboveStandard = Math.max(0, totalDeductions - standardDeduction);
    const taxSavings = aboveStandard * marginalRate;
    return { year: year + 1, mortgageInterest: yearlyInterest, propertyTax: annualPropertyTax, totalDeductions, standardDeduction, aboveStandard, taxSavings, monthlyBenefit: taxSavings / 12, effectivePayment: baselinePiti.total - (taxSavings / 12) };
  });

  return {
    id: 'tax-benefit', name: 'Tax Benefit Realization', color: '#16a34a',
    shortDescription: 'After-tax payment savings',
    data: {
      marginalTaxRate: marginalRate, standardDeduction, yearlyBenefits,
      totalTenYearSavings: yearlyBenefits.reduce((sum, y) => sum + y.taxSavings, 0),
      itemizingBeneficial: yearlyBenefits[0].totalDeductions > standardDeduction,
      year1Savings: yearlyBenefits[0].taxSavings, year1MonthlyBenefit: yearlyBenefits[0].monthlyBenefit,
      effectiveYear1Payment: yearlyBenefits[0].effectivePayment,
    },
  };
}

function buildInflationHedgeCalc(profile, homePrices, baselinePiti) {
  const scenarios = [
    { name: 'Low Inflation (2%)', inflation: 0.02, appreciation: 0.025 },
    { name: 'Normal Inflation (3%)', inflation: 0.03, appreciation: 0.04 },
    { name: 'High Inflation (5%)', inflation: 0.05, appreciation: 0.06 },
  ];

  const analysis = scenarios.map(scenario => {
    const projections = Array.from({ length: 10 }, (_, year) => {
      const futureRent = profile.currentRent * Math.pow(1 + scenario.inflation, year + 1);
      const homeValue = homePrices.baseline * Math.pow(1 + scenario.appreciation, year + 1);
      const taxInsIncrease = (baselinePiti.propertyTax + baselinePiti.insurance) * (Math.pow(1 + scenario.inflation, year + 1) - 1);
      const adjustedPiti = baselinePiti.total + taxInsIncrease;
      return { year: year + 1, rent: futureRent, homeValue, fixedPortion: baselinePiti.principalInterest, adjustedPiti, renterAnnualCost: futureRent * 12, buyerAnnualCost: adjustedPiti * 12, annualSavings: (futureRent - adjustedPiti) * 12 };
    });
    const totalHedgeValue = projections.reduce((sum, p) => sum + p.annualSavings, 0);
    return { scenario: scenario.name, inflationRate: scenario.inflation * 100, projections, totalHedgeValue, year10Rent: projections[9].rent, year10Piti: projections[9].adjustedPiti };
  });

  const normalScenario = analysis[1];
  const hedgeScore = (normalScenario.totalHedgeValue / (baselinePiti.total * 120)) * 100;

  return {
    id: 'inflation-hedge', name: 'Inflation Hedge Index', color: '#ca8a04',
    shortDescription: 'Protection from rising costs',
    data: { currentRent: profile.currentRent, currentPiti: baselinePiti.total, analysis, hedgeScore: Math.max(0, hedgeScore), recommendation: hedgeScore > 20 ? 'strong' : hedgeScore > 0 ? 'moderate' : 'weak' },
  };
}

function buildJobMobilityCalc(homePrices, profile, baselinePiti) {
  const downPayment = homePrices.baseline * 0.05;
  const loanAmount = homePrices.baseline * 0.95;
  const closingCosts = CalculatorService.calculateClosingCosts(loanAmount, homePrices.baseline).total;
  const initialInvestment = downPayment + closingCosts;

  const relocateScenarios = [1, 2, 3, 5, 7].map(year => {
    const homeValue = homePrices.baseline * Math.pow(1.03, year);
    const principalPaid = loanAmount * (year <= 3 ? 0.018 * year : 0.018 * 3 + 0.022 * (year - 3));
    const loanBalance = loanAmount - principalPaid;
    const sellingCosts = homeValue * 0.08;
    const netProceeds = homeValue - loanBalance - sellingCosts;
    const totalPiti = baselinePiti.total * 12 * year;
    let rentPaid = 0, currentRent = profile.currentRent;
    for (let y = 0; y < year; y++) { rentPaid += currentRent * 12; currentRent *= 1.03; }
    const totalBuyingCost = initialInvestment + totalPiti - netProceeds;
    return { year, homeValue, loanBalance, sellingCosts, netProceeds, totalPiti, rentEquivalent: rentPaid, totalBuyingCost, costPerMonth: totalBuyingCost / (year * 12), profitOrLoss: netProceeds - initialInvestment, betterThanRenting: totalBuyingCost < rentPaid };
  });

  const breakEvenYear = relocateScenarios.find(s => s.profitOrLoss > 0)?.year || '>7';

  return {
    id: 'job-mobility', name: 'Job Mobility Impact', color: '#0369a1',
    shortDescription: 'Cost if you need to move',
    data: {
      initialInvestment, currentRent: profile.currentRent, scenarios: relocateScenarios,
      breakEvenYear, minimumStay: breakEvenYear,
      flexibilityScore: relocateScenarios[1].betterThanRenting ? 'good' : relocateScenarios[2].betterThanRenting ? 'moderate' : 'poor',
    },
  };
}

export default buildCalculators;
