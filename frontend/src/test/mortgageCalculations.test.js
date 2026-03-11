/**
 * Mortgage Calculations Tests
 *
 * Tests for core mortgage math: monthly P&I, APR, amortization schedules,
 * DTI ratio, and LTV ratio.  All functions are implemented inline so the
 * tests have no external dependencies and run in any environment.
 */

// ---------------------------------------------------------------------------
// Pure calculation helpers (production equivalents live in utils/)
// ---------------------------------------------------------------------------

/**
 * Calculate fixed-rate monthly principal & interest payment (standard formula).
 *
 * @param {number} principal   - Loan amount in dollars
 * @param {number} annualRate  - Annual interest rate as a decimal (e.g. 0.07 = 7%)
 * @param {number} termMonths  - Loan term in months (e.g. 360 for 30 years)
 * @returns {number} Monthly payment, rounded to 2 decimal places
 */
function calcMonthlyPayment(principal, annualRate, termMonths) {
  if (annualRate === 0) {
    return Math.round((principal / termMonths) * 100) / 100;
  }
  const r = annualRate / 12;
  const payment = (principal * r * Math.pow(1 + r, termMonths)) / (Math.pow(1 + r, termMonths) - 1);
  return Math.round(payment * 100) / 100;
}

/**
 * Approximate APR given a note rate, loan amount, and financed fees.
 * Uses the same monthly-payment formula but solves for the rate that yields
 * the same payment against (principal - financedFees).
 *
 * For test purposes we use a Newton–Raphson iteration to find the monthly
 * rate that satisfies: payment = adjustedPrincipal * r * (1+r)^n / ((1+r)^n - 1)
 *
 * @param {number} principal      - Loan amount (before fees)
 * @param {number} annualNoteRate - Note rate as decimal
 * @param {number} termMonths     - Loan term in months
 * @param {number} financedFees   - Total financed fees (points, origination, etc.)
 * @returns {number} APR as a decimal, rounded to 6 decimal places
 */
function calcAPR(principal, annualNoteRate, termMonths, financedFees) {
  // Monthly payment is computed on the full principal at the note rate
  const monthlyPayment = calcMonthlyPayment(principal, annualNoteRate, termMonths);
  // The amount actually received by the borrower is reduced by fees
  const adjustedPrincipal = principal - financedFees;

  // Newton–Raphson: find monthly rate r such that
  //   adjustedPrincipal = payment * (1 - (1+r)^-n) / r
  let r = annualNoteRate / 12; // initial guess

  for (let i = 0; i < 200; i++) {
    const onePlusR_n = Math.pow(1 + r, termMonths);
    const f = adjustedPrincipal - monthlyPayment * (1 - 1 / onePlusR_n) / r;
    const df = monthlyPayment * (
      (1 - 1 / onePlusR_n) / (r * r) -
      termMonths / (r * onePlusR_n * (1 + r))
    );
    const delta = f / df;
    r -= delta;
    if (Math.abs(delta) < 1e-10) break;
  }

  return Math.round(r * 12 * 1e6) / 1e6; // annualised, 6 dp
}

/**
 * Generate amortization schedule for the first `months` periods.
 *
 * @param {number} principal   - Loan amount
 * @param {number} annualRate  - Annual rate as decimal
 * @param {number} termMonths  - Full loan term in months
 * @param {number} months      - How many months of schedule to return
 * @returns {Array<{month, payment, principal, interest, balance}>}
 */
function generateAmortizationSchedule(principal, annualRate, termMonths, months = termMonths) {
  const monthlyRate = annualRate / 12;
  const payment = calcMonthlyPayment(principal, annualRate, termMonths);
  const schedule = [];
  let balance = principal;

  for (let month = 1; month <= months && balance > 0; month++) {
    const interestCharge = Math.round(balance * monthlyRate * 100) / 100;
    const principalCharge = Math.round((payment - interestCharge) * 100) / 100;
    balance = Math.round((balance - principalCharge) * 100) / 100;
    if (balance < 0) balance = 0;
    schedule.push({ month, payment, principal: principalCharge, interest: interestCharge, balance });
  }

  return schedule;
}

/**
 * Calculate Debt-to-Income (DTI) ratio.
 *
 * @param {number} monthlyDebtPayments - Total monthly debt obligations (PITI + other debts)
 * @param {number} grossMonthlyIncome  - Gross monthly income
 * @returns {number} DTI as a percentage, rounded to 2 decimal places
 */
function calcDTI(monthlyDebtPayments, grossMonthlyIncome) {
  if (grossMonthlyIncome <= 0) throw new Error('Gross monthly income must be positive');
  return Math.round((monthlyDebtPayments / grossMonthlyIncome) * 10000) / 100;
}

/**
 * Calculate Loan-to-Value (LTV) ratio.
 *
 * @param {number} loanAmount     - Loan amount
 * @param {number} propertyValue  - Appraised / purchase price (whichever is lower per guidelines)
 * @returns {number} LTV as a percentage, rounded to 2 decimal places
 */
function calcLTV(loanAmount, propertyValue) {
  if (propertyValue <= 0) throw new Error('Property value must be positive');
  return Math.round((loanAmount / propertyValue) * 10000) / 100;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Monthly Payment Calculation (P&I)', () => {
  test('calculates standard 30-year fixed payment correctly', () => {
    // $400,000 at 7.00% for 360 months → known answer ~$2,661.21
    const payment = calcMonthlyPayment(400_000, 0.07, 360);
    expect(payment).toBeCloseTo(2661.21, 0);
  });

  test('calculates 15-year fixed payment correctly', () => {
    // $300,000 at 6.5% for 180 months → known answer ~$2,613.32
    const payment = calcMonthlyPayment(300_000, 0.065, 180);
    expect(payment).toBeCloseTo(2613.32, 0);
  });

  test('returns principal/months when rate is zero', () => {
    const payment = calcMonthlyPayment(120_000, 0, 120);
    expect(payment).toBe(1000.00);
  });

  test('higher rate produces higher payment for same principal and term', () => {
    const lowRatePayment  = calcMonthlyPayment(300_000, 0.05, 360);
    const highRatePayment = calcMonthlyPayment(300_000, 0.08, 360);
    expect(highRatePayment).toBeGreaterThan(lowRatePayment);
  });

  test('shorter term produces higher payment for same principal and rate', () => {
    const thirtyYear = calcMonthlyPayment(200_000, 0.065, 360);
    const fifteenYear = calcMonthlyPayment(200_000, 0.065, 180);
    expect(fifteenYear).toBeGreaterThan(thirtyYear);
  });

  test('payment is always positive for valid inputs', () => {
    [100_000, 250_000, 750_000, 1_500_000].forEach((amount) => {
      expect(calcMonthlyPayment(amount, 0.07, 360)).toBeGreaterThan(0);
    });
  });
});

describe('APR Calculation', () => {
  test('APR is higher than note rate when fees are present', () => {
    const noteRate = 0.07;
    const fees = 4_000; // e.g. origination + points
    const apr = calcAPR(400_000, noteRate, 360, fees);
    expect(apr).toBeGreaterThan(noteRate);
  });

  test('APR equals note rate when there are no financed fees', () => {
    const noteRate = 0.065;
    const apr = calcAPR(300_000, noteRate, 360, 0);
    // With zero fees the APR should be within 0.001% of the note rate
    expect(Math.abs(apr - noteRate)).toBeLessThan(0.0001);
  });

  test('APR increases as fees increase (same loan)', () => {
    const params = [300_000, 0.07, 360];
    const apr1 = calcAPR(...params, 1_000);
    const apr2 = calcAPR(...params, 5_000);
    expect(apr2).toBeGreaterThan(apr1);
  });

  test('returns a number in a realistic mortgage range (4%–12%)', () => {
    const apr = calcAPR(350_000, 0.075, 360, 3_500);
    expect(apr).toBeGreaterThan(0.04);
    expect(apr).toBeLessThan(0.12);
  });
});

describe('Amortization Schedule Generation', () => {
  const schedule = generateAmortizationSchedule(200_000, 0.06, 360, 360);

  test('generates the correct number of entries', () => {
    expect(schedule).toHaveLength(360);
  });

  test('first entry has month = 1', () => {
    expect(schedule[0].month).toBe(1);
  });

  test('last entry has balance of zero (fully amortised)', () => {
    expect(schedule[359].balance).toBe(0);
  });

  test('every entry has positive interest in first half of loan', () => {
    schedule.slice(0, 180).forEach(({ interest }) => {
      expect(interest).toBeGreaterThan(0);
    });
  });

  test('principal portion grows over the loan term (interest-heavy at start)', () => {
    // Month 1 principal < month 180 principal
    expect(schedule[0].principal).toBeLessThan(schedule[179].principal);
  });

  test('interest portion decreases over the loan term', () => {
    // Month 1 interest > month 180 interest
    expect(schedule[0].interest).toBeGreaterThan(schedule[179].interest);
  });

  test('payment + balance reconcile: balance[n] = balance[n-1] - principal[n]', () => {
    for (let i = 1; i < 12; i++) {
      const prev = schedule[i - 1].balance;
      const curr = schedule[i].balance;
      const paid = schedule[i].principal;
      expect(Math.abs(prev - curr - paid)).toBeLessThan(0.02); // allow 1-cent rounding
    }
  });

  test('partial schedule generates only requested months', () => {
    const partial = generateAmortizationSchedule(200_000, 0.06, 360, 12);
    expect(partial).toHaveLength(12);
  });
});

describe('DTI Ratio Calculation', () => {
  test('calculates DTI correctly for a conventional borrower', () => {
    // $2,000 monthly debt on $7,000 gross income → 28.57%
    const dti = calcDTI(2_000, 7_000);
    expect(dti).toBeCloseTo(28.57, 1);
  });

  test('43% DTI is the standard qualifying threshold (FHA/conventional)', () => {
    // This test documents the business rule: ≤43% passes underwriting
    const borderlineDTI = calcDTI(3_010, 7_000); // just above 43%
    expect(borderlineDTI).toBeGreaterThan(43);

    const passingDTI = calcDTI(2_990, 7_000); // just below 43%
    expect(passingDTI).toBeLessThan(43);
  });

  test('returns 100% when debt equals income', () => {
    expect(calcDTI(5_000, 5_000)).toBe(100);
  });

  test('throws when income is zero', () => {
    expect(() => calcDTI(1_500, 0)).toThrow('Gross monthly income must be positive');
  });

  test('returns 0 when monthly debt is zero', () => {
    expect(calcDTI(0, 8_000)).toBe(0);
  });
});

describe('LTV Ratio Calculation', () => {
  test('calculates 80% LTV for a conventional down-payment scenario', () => {
    // $320,000 loan on $400,000 property = 80.00%
    expect(calcLTV(320_000, 400_000)).toBe(80);
  });

  test('96.5% LTV — standard FHA minimum down payment (3.5%)', () => {
    const loan = 386_000;
    const value = 400_000;
    expect(calcLTV(loan, value)).toBe(96.5);
  });

  test('PMI required threshold: LTV > 80%', () => {
    const withPMI    = calcLTV(325_000, 400_000); // 81.25% — needs PMI
    const withoutPMI = calcLTV(320_000, 400_000); // 80.00% — no PMI

    expect(withPMI).toBeGreaterThan(80);
    expect(withoutPMI).toBeLessThanOrEqual(80);
  });

  test('VA/USDA 100% financing scenario returns 100', () => {
    expect(calcLTV(300_000, 300_000)).toBe(100);
  });

  test('throws when property value is zero', () => {
    expect(() => calcLTV(200_000, 0)).toThrow('Property value must be positive');
  });
});
