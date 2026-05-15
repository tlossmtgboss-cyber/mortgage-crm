/**
 * Strategic Calculator Builders (Phase 3)
 *
 * Builds calculator data for the "Is This Smart Long-Term?" phase:
 * repayment-strategy, exit-strategy, program-options,
 * break-even-horizon, equity-velocity, tax-benefit,
 * inflation-hedge, job-mobility.
 *
 * All financial math is preserved exactly as-is from the original CalculatorDashboard.
 */

import CalculatorService, {
  formatCurrency,
  formatCurrencyFull,
} from '../../services/calculator/CalculatorService';

/**
 * Build strategic/long-term calculators.
 */
export function buildStrategicCalculators(profile, market, homePrices, downPaymentScenarios, baselinePiti, monthlyIncome) {
  return [
    buildRepaymentStrategy(market, homePrices, monthlyIncome),
    buildExitStrategy(profile, market, homePrices, baselinePiti),
    buildProgramOptions(profile, market, homePrices),
    buildBreakEvenHorizon(profile, homePrices, baselinePiti),
    buildEquityVelocity(homePrices),
    buildTaxBenefit(profile, market, homePrices, baselinePiti),
    buildInflationHedge(profile, market, homePrices, baselinePiti),
    buildJobMobility(profile, homePrices, baselinePiti),
  ];
}

function buildRepaymentStrategy(market, homePrices, monthlyIncome) {
  return {
    id: 'repayment-strategy',
    name: 'Repayment Strategy',
    color: '#2D7A52',
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
  };
}

function buildExitStrategy(profile, market, homePrices, baselinePiti) {
  return {
    id: 'exit-strategy',
    name: 'Exit Strategy',
    color: '#B8924A',
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
  };
}

function buildProgramOptions(profile, market, homePrices) {
  return {
    id: 'program-options',
    name: 'Program Options',
    color: '#B8924A',
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
  };
}

function buildBreakEvenHorizon(profile, homePrices, baselinePiti) {
  return {
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
  };
}

function buildEquityVelocity(homePrices) {
  return {
    id: 'equity-velocity',
    name: 'Equity Velocity',
    color: '#2D7A52',
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
  };
}

function buildTaxBenefit(profile, market, homePrices, baselinePiti) {
  return {
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
  };
}

function buildInflationHedge(profile, market, homePrices, baselinePiti) {
  return {
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
  };
}

function buildJobMobility(profile, homePrices, baselinePiti) {
  return {
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
  };
}
