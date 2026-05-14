/**
 * Calculator Data Builder
 *
 * Orchestrates building all calculator data from profile, market, and property inputs.
 * Delegates to buildCalculatorsCore (Phase 1 & 2) and buildCalculatorsStrategic (Phase 3).
 */

import CalculatorService from '../../services/calculator/CalculatorService';
import { DEFAULT_PROPERTY } from './constants';
import { buildCoreCalculators } from './buildCalculatorsCore';
import { buildStrategicCalculators } from './buildCalculatorsStrategic';

/**
 * Build all calculator definitions from the given profile, market, and property data.
 * Returns an array of calculator objects with { id, name, color, shortDescription, data }.
 */
export const buildCalculators = (profile, market, propertyData = DEFAULT_PROPERTY) => {
  // Calculate data for each calculator
  const monthlyIncome = profile.monthlyIncome;

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

  // Build all calculators from both modules
  const coreCalcs = buildCoreCalculators(
    profile, market, propertyData, homePrices,
    downPaymentScenarios, baselinePiti, dti, monthlyIncome
  );

  const strategicCalcs = buildStrategicCalculators(
    profile, market, homePrices,
    downPaymentScenarios, baselinePiti, monthlyIncome
  );

  return [...coreCalcs, ...strategicCalcs];
};

export default buildCalculators;
