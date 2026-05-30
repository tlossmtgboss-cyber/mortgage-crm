/**
 * Financial scenario calculators (portal consolidation Phase 1 harvest).
 *
 * Pure functions extracted from the deleted PerenniaClientPortalUltimate
 * scenarios tab so the math is testable independent of React. Formulas are
 * ported verbatim from that component (standard 30yr amortization, 80%-LTV
 * cash-out, 85%-equity HELOC estimate, ~8% selling costs).
 */
import {
  calculateRefinance,
  calculateCashOut,
  calculateHeloc,
  calculateSell,
} from '../scenarioCalcs';

describe('calculateRefinance', () => {
  it('computes monthly/yearly savings for a lower rate', () => {
    const r = calculateRefinance({ currentBalance: 300000, currentRate: 6.5, newRate: 5.5 });
    expect(r.currentPayment).toBeCloseTo(1896.2, 0);
    expect(r.newPayment).toBeCloseTo(1703.37, 0);
    expect(r.monthlySavings).toBeCloseTo(192.83, 0);
    expect(r.yearlySavings).toBeCloseTo(r.monthlySavings * 12, 5);
  });

  it('returns negative savings when the new rate is higher', () => {
    const r = calculateRefinance({ currentBalance: 300000, currentRate: 5.5, newRate: 6.5 });
    expect(r.monthlySavings).toBeLessThan(0);
  });
});

describe('calculateCashOut', () => {
  it('computes available cash, new loan, and new LTV', () => {
    const r = calculateCashOut({
      currentValue: 500000,
      currentBalance: 300000,
      targetLtv: 80,
      cashOutAmount: 50000,
    });
    expect(r.maxLoanAmount).toBe(400000);
    expect(r.availableCashOut).toBe(100000);
    expect(r.newLoanAmount).toBe(350000);
    expect(r.newLtv).toBeCloseTo(70, 5);
  });

  it('floors available cash at zero when already over target LTV', () => {
    const r = calculateCashOut({
      currentValue: 300000,
      currentBalance: 290000,
      targetLtv: 80,
      cashOutAmount: 0,
    });
    expect(r.availableCashOut).toBe(0);
  });
});

describe('calculateHeloc', () => {
  it('estimates 85% of current equity', () => {
    expect(calculateHeloc({ currentEquity: 200000 }).estimatedCreditLine).toBe(170000);
  });
});

describe('calculateSell', () => {
  it('computes ~8% selling costs and net proceeds', () => {
    const r = calculateSell({ currentValue: 500000, currentBalance: 300000 });
    expect(r.salePrice).toBe(500000);
    expect(r.loanPayoff).toBe(300000);
    expect(r.sellingCosts).toBe(40000);
    expect(r.netProceeds).toBe(160000);
  });
});
