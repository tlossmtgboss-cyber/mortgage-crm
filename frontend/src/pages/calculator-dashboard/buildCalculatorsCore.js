/**
 * Core Calculator Builders (Phase 1 & 2)
 *
 * Builds calculator data for the "Can I Buy?" and "What Does This Really Cost?" phases.
 * All financial math is preserved exactly as-is from the original CalculatorDashboard.
 */

import CalculatorService, {
  formatCurrency,
  formatCurrencyFull,
} from '../../services/calculator/CalculatorService';
import { DEFAULT_PROPERTY } from './constants';

/**
 * Build core calculators: down-payment, monthly-payment, dti, rent-vs-buy,
 * cash-reserves, closing-costs, cost-to-waiting, prepay-or-invest,
 * emergency-runway, stress-test, payment-shock, lifestyle-fit.
 */
export function buildCoreCalculators(profile, market, propertyData, homePrices, downPaymentScenarios, baselinePiti, dti, monthlyIncome) {
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

        // Five year rent and equity
        const fiveYearRent = Array.from({ length: 5 }, (_, i) =>
          profile.currentRent * 12 * Math.pow(1.03, i)
        ).reduce((a, b) => a + b, 0);

        return {
          currentRent: profile.currentRent,
          mortgagePayment: baselinePiti.total,
          monthlyDifference: baselinePiti.total - profile.currentRent,
          fiveYearRent,
          fiveYearEquity: homePrices.baseline * Math.pow(1.03, 5) - homePrices.baseline * 0.95 * 0.92,
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
    buildCashReservesCalculator(profile, market, homePrices, downPaymentScenarios, baselinePiti, monthlyIncome),
    buildClosingCostsCalculator(profile, market, homePrices),
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
    // Phase 1 new calculators
    buildEmergencyRunwayCalculator(profile, homePrices, baselinePiti, monthlyIncome),
    buildStressTestCalculator(profile, market, homePrices, baselinePiti, dti, monthlyIncome, propertyData),
    // Phase 2 new calculators
    buildPaymentShockCalculator(baselinePiti, propertyData),
    buildLifestyleFitCalculator(profile, homePrices, baselinePiti, monthlyIncome),
  ];
}

function buildCashReservesCalculator(profile, market, homePrices, downPaymentScenarios, baselinePiti, monthlyIncome) {
  return {
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
  };
}

function buildClosingCostsCalculator(profile, market, homePrices) {
  return {
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
  };
}

function buildEmergencyRunwayCalculator(profile, homePrices, baselinePiti, monthlyIncome) {
  return {
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
  };
}

function buildStressTestCalculator(profile, market, homePrices, baselinePiti, dti, monthlyIncome, propertyData) {
  return {
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
  };
}

function buildPaymentShockCalculator(baselinePiti, propertyData) {
  return {
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
  };
}

function buildLifestyleFitCalculator(profile, homePrices, baselinePiti, monthlyIncome) {
  return {
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
  };
}
