/**
 * Financial scenario calculators — portal consolidation Phase 1 harvest.
 *
 * Ported verbatim from the deleted PerenniaClientPortalUltimate "Scenarios" tab
 * so the math survives the consolidation. Pure functions (no React, no network)
 * so they're unit-testable and reusable across portal stages. All run off data
 * the PURL portal already has (loan amount/rate + computed property value), so
 * there is no backend dependency.
 */

const MONTHS = 360; // standard 30-year amortization

/**
 * 30-year fully-amortizing monthly payment.
 * @param {number} principal
 * @param {number} annualRatePct - e.g. 6.5 for 6.5%
 */
function monthlyPayment(principal, annualRatePct) {
  const r = annualRatePct / 100 / 12;
  if (r === 0) return principal / MONTHS;
  return (principal * r) / (1 - Math.pow(1 + r, -MONTHS));
}

/**
 * Refinance: compare current payment to a new-rate payment on the same balance.
 */
export function calculateRefinance({ currentBalance, currentRate, newRate }) {
  const currentPayment = monthlyPayment(currentBalance, currentRate);
  const newPayment = monthlyPayment(currentBalance, newRate);
  const monthlySavings = currentPayment - newPayment;
  return {
    currentPayment,
    newPayment,
    monthlySavings,
    yearlySavings: monthlySavings * 12,
  };
}

/**
 * Cash-out refinance against a target LTV.
 */
export function calculateCashOut({ currentValue, currentBalance, targetLtv, cashOutAmount }) {
  const maxLoan = currentValue * (targetLtv / 100);
  const availableCash = maxLoan - currentBalance;
  return {
    maxLoanAmount: maxLoan,
    availableCashOut: Math.max(0, availableCash),
    newLoanAmount: currentBalance + cashOutAmount,
    newLtv: ((currentBalance + cashOutAmount) / currentValue) * 100,
  };
}

/**
 * HELOC: estimated credit line at 85% of current equity.
 */
export function calculateHeloc({ currentEquity }) {
  return { estimatedCreditLine: currentEquity * 0.85 };
}

/**
 * Sell analysis: net proceeds after ~8% selling costs and loan payoff.
 */
export function calculateSell({ currentValue, currentBalance }) {
  const sellingCosts = currentValue * 0.08;
  return {
    salePrice: currentValue,
    loanPayoff: currentBalance,
    sellingCosts,
    netProceeds: currentValue - currentBalance - sellingCosts,
  };
}
