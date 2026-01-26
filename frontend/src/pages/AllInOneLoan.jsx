/**
 * All In One Loan Calculator
 *
 * Dedicated page for comparing traditional mortgages with
 * First-Lien HELOC using velocity banking strategy.
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import './AllInOneLoan.css';

const formatCurrency = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const AllInOneLoan = () => {
  // User inputs
  const [homePrice, setHomePrice] = useState(350000);
  const [downPaymentPct, setDownPaymentPct] = useState(20);
  const [conventionalRate, setConventionalRate] = useState(6.875);
  const [helocRate, setHelocRate] = useState(7.5);
  const [monthlyIncome, setMonthlyIncome] = useState(12000);
  const [monthlyExpenses, setMonthlyExpenses] = useState(5000);

  // Derived values
  const downPayment = homePrice * (downPaymentPct / 100);
  const loanAmount = homePrice - downPayment;
  const monthlyNetCashflow = monthlyIncome - monthlyExpenses;

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

  // Interest only payment for HELOC
  const helocInterestOnlyMonthly = (loanAmount * (helocRate / 100)) / 12;

  // Simulate All In One payoff with velocity banking
  const simulateAIOPayoff = () => {
    let balance = loanAmount;
    let months = 0;
    let totalInterestPaid = 0;
    const maxMonths = 360;
    const yearlyData = [];

    while (balance > 0 && months < maxMonths) {
      const monthlyInterest = (balance * (helocRate / 100)) / 12;
      totalInterestPaid += monthlyInterest;
      const netReduction = monthlyNetCashflow - monthlyInterest;

      if (netReduction > 0) {
        balance -= netReduction;
      } else {
        balance -= netReduction;
      }

      months++;

      // Track yearly milestones
      if (months % 12 === 0) {
        yearlyData.push({
          year: months / 12,
          balance: Math.max(0, balance),
          interestPaid: totalInterestPaid,
        });
      }

      if (balance <= 0) break;
    }

    return {
      months: Math.min(months, maxMonths),
      years: Math.min(months / 12, 30),
      totalInterestPaid,
      paidOff: balance <= 0,
      yearlyData,
    };
  };

  const aioResult = simulateAIOPayoff();
  const interestSavings = traditionalInterest - aioResult.totalInterestPaid;
  const yearsSaved = 30 - aioResult.years;

  // Calculate traditional mortgage yearly data for comparison
  const getTraditionalYearlyData = () => {
    const data = [];
    let balance = loanAmount;
    const monthlyRate = conventionalRate / 100 / 12;
    let totalInterest = 0;

    for (let year = 1; year <= 30; year++) {
      for (let month = 0; month < 12; month++) {
        const interest = balance * monthlyRate;
        const principal = traditionalMonthly - interest;
        totalInterest += interest;
        balance -= principal;
      }
      data.push({
        year,
        balance: Math.max(0, balance),
        interestPaid: totalInterest,
      });
    }
    return data;
  };

  const traditionalYearlyData = getTraditionalYearlyData();

  return (
    <div className="aio-page">
      {/* Header */}
      <header className="aio-header">
        <div className="aio-header-content">
          <Link to="/calculators" className="back-link">
            <span className="back-icon">←</span>
            <span>Back to Calculators</span>
          </Link>
          <div className="header-title">
            <div className="title-badge">
              <span className="badge-icon">🏦</span>
              <span>Alternative Mortgage Strategy</span>
            </div>
            <h1>All In One Loan Calculator</h1>
            <p className="subtitle">Compare traditional mortgages with First-Lien HELOC velocity banking</p>
          </div>
        </div>
      </header>

      <main className="aio-main">
        {/* Input Section */}
        <section className="aio-inputs-section">
          <h2>Your Scenario</h2>
          <div className="inputs-grid">
            <div className="input-card">
              <h3>Property & Loan</h3>
              <div className="input-group">
                <label>Home Price</label>
                <div className="input-with-prefix">
                  <span className="prefix">$</span>
                  <input
                    type="number"
                    value={homePrice}
                    onChange={(e) => setHomePrice(Number(e.target.value) || 0)}
                  />
                </div>
              </div>
              <div className="input-group">
                <label>Down Payment</label>
                <div className="input-with-suffix">
                  <input
                    type="number"
                    value={downPaymentPct}
                    onChange={(e) => setDownPaymentPct(Number(e.target.value) || 0)}
                  />
                  <span className="suffix">%</span>
                </div>
                <span className="input-hint">{formatCurrency(downPayment)}</span>
              </div>
            </div>

            <div className="input-card">
              <h3>Interest Rates</h3>
              <div className="input-group">
                <label>Traditional Mortgage Rate</label>
                <div className="input-with-suffix">
                  <input
                    type="number"
                    step="0.125"
                    value={conventionalRate}
                    onChange={(e) => setConventionalRate(Number(e.target.value) || 0)}
                  />
                  <span className="suffix">%</span>
                </div>
              </div>
              <div className="input-group">
                <label>HELOC Rate</label>
                <div className="input-with-suffix">
                  <input
                    type="number"
                    step="0.125"
                    value={helocRate}
                    onChange={(e) => setHelocRate(Number(e.target.value) || 0)}
                  />
                  <span className="suffix">%</span>
                </div>
              </div>
            </div>

            <div className="input-card">
              <h3>Monthly Cashflow</h3>
              <div className="input-group">
                <label>Gross Monthly Income</label>
                <div className="input-with-prefix">
                  <span className="prefix">$</span>
                  <input
                    type="number"
                    value={monthlyIncome}
                    onChange={(e) => setMonthlyIncome(Number(e.target.value) || 0)}
                  />
                </div>
              </div>
              <div className="input-group">
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
              <div className="cashflow-summary">
                <span>Net Monthly Cashflow:</span>
                <span className={monthlyNetCashflow >= 0 ? 'positive' : 'negative'}>
                  {formatCurrency(monthlyNetCashflow)}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Comparison Section */}
        <section className="aio-comparison-section">
          <h2>Side-by-Side Comparison</h2>
          <div className="comparison-cards">
            {/* Traditional Card */}
            <div className="comparison-card traditional">
              <div className="card-header">
                <span className="card-badge">Traditional</span>
                <h3>30-Year Fixed Mortgage</h3>
              </div>
              <div className="card-body">
                <div className="stat-row">
                  <span className="stat-label">Loan Amount</span>
                  <span className="stat-value">{formatCurrency(loanAmount)}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Interest Rate</span>
                  <span className="stat-value">{conventionalRate}%</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Monthly Payment</span>
                  <span className="stat-value">{formatCurrency(traditionalMonthly)}</span>
                </div>
                <div className="stat-row highlight negative">
                  <span className="stat-label">Total Interest Paid</span>
                  <span className="stat-value">{formatCurrency(traditionalInterest)}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Payoff Time</span>
                  <span className="stat-value">30 years</span>
                </div>
              </div>
            </div>

            {/* All In One Card */}
            <div className="comparison-card allinone featured">
              <div className="card-header">
                <span className="card-badge special">All In One</span>
                <h3>First-Lien HELOC</h3>
              </div>
              <div className="card-body">
                <div className="stat-row">
                  <span className="stat-label">Credit Line</span>
                  <span className="stat-value">{formatCurrency(loanAmount)}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">HELOC Rate</span>
                  <span className="stat-value">{helocRate}%</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Interest-Only Min</span>
                  <span className="stat-value">{formatCurrency(helocInterestOnlyMonthly)}</span>
                </div>
                <div className="stat-row highlight positive">
                  <span className="stat-label">Total Interest Paid</span>
                  <span className="stat-value">{formatCurrency(aioResult.totalInterestPaid)}</span>
                </div>
                <div className="stat-row positive">
                  <span className="stat-label">Payoff Time</span>
                  <span className="stat-value">{aioResult.years.toFixed(1)} years</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Savings Banner */}
        {interestSavings > 0 && (
          <section className="aio-savings-section">
            <div className="savings-card">
              <div className="savings-main">
                <div className="savings-amount">{formatCurrency(interestSavings)}</div>
                <div className="savings-label">Potential Interest Savings</div>
              </div>
              <div className="savings-details">
                <div className="savings-detail">
                  <span className="detail-icon">⏱️</span>
                  <span className="detail-text">
                    <strong>Pay off {yearsSaved.toFixed(1)} years faster</strong>
                    <span>Own your home free and clear sooner</span>
                  </span>
                </div>
                <div className="savings-detail">
                  <span className="detail-icon">💵</span>
                  <span className="detail-text">
                    <strong>Monthly cashflow: {formatCurrency(monthlyNetCashflow)}</strong>
                    <span>Working for you every day</span>
                  </span>
                </div>
                <div className="savings-detail">
                  <span className="detail-icon">📈</span>
                  <span className="detail-text">
                    <strong>{((interestSavings / traditionalInterest) * 100).toFixed(0)}% less interest</strong>
                    <span>More money stays in your pocket</span>
                  </span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* How It Works Section */}
        <section className="aio-how-section">
          <h2>How Velocity Banking Works</h2>
          <div className="how-grid">
            <div className="how-card">
              <div className="how-number">1</div>
              <h3>Deposit All Income</h3>
              <p>Your entire paycheck goes directly into the HELOC. This immediately reduces your balance and the interest calculated on it.</p>
            </div>
            <div className="how-card">
              <div className="how-number">2</div>
              <h3>Pay Expenses as Needed</h3>
              <p>Use the built-in checking feature to pay bills. You only "borrow" what you actually spend, keeping your average balance low.</p>
            </div>
            <div className="how-card">
              <div className="how-number">3</div>
              <h3>Daily Interest Calculation</h3>
              <p>Unlike traditional mortgages, interest is calculated daily on your current balance, not the original loan amount.</p>
            </div>
            <div className="how-card">
              <div className="how-number">4</div>
              <h3>Accelerated Payoff</h3>
              <p>Your positive cashflow continuously reduces principal. The more disciplined your spending, the faster you pay off your home.</p>
            </div>
          </div>
        </section>

        {/* Amortization Comparison */}
        <section className="aio-amortization-section">
          <h2>Balance Over Time</h2>
          <div className="amortization-table">
            <div className="table-header">
              <span>Year</span>
              <span>Traditional Balance</span>
              <span>All In One Balance</span>
              <span>Difference</span>
            </div>
            {[1, 2, 3, 5, 7, 10, 15, 20, 25, 30].map(year => {
              const tradData = traditionalYearlyData[year - 1];
              const aioData = aioResult.yearlyData[year - 1];
              const tradBalance = tradData?.balance || 0;
              const aioBalance = aioData?.balance || 0;
              const diff = tradBalance - aioBalance;

              return (
                <div key={year} className={`table-row ${aioBalance === 0 ? 'paid-off' : ''}`}>
                  <span className="year-cell">Year {year}</span>
                  <span>{formatCurrency(tradBalance)}</span>
                  <span className={aioBalance === 0 ? 'positive' : ''}>
                    {aioBalance === 0 ? 'PAID OFF' : formatCurrency(aioBalance)}
                  </span>
                  <span className="positive">{diff > 0 ? `+${formatCurrency(diff)}` : '-'}</span>
                </div>
              );
            })}
          </div>
        </section>

        {/* Requirements Section */}
        <section className="aio-requirements-section">
          <h2>Requirements & Considerations</h2>
          <div className="requirements-grid">
            <div className="requirement-card">
              <div className="req-icon">📊</div>
              <h3>Credit Score</h3>
              <p>680+ credit score typically required for first-lien HELOC approval</p>
            </div>
            <div className="requirement-card">
              <div className="req-icon">💰</div>
              <h3>Down Payment</h3>
              <p>20% down payment required (no PMI with this structure)</p>
            </div>
            <div className="requirement-card">
              <div className="req-icon">📈</div>
              <h3>Positive Cashflow</h3>
              <p>Strategy works best with consistent income exceeding expenses</p>
            </div>
            <div className="requirement-card">
              <div className="req-icon">🏠</div>
              <h3>Primary Residence</h3>
              <p>Most lenders require this for primary residence only</p>
            </div>
            <div className="requirement-card warning">
              <div className="req-icon">⚠️</div>
              <h3>Variable Rate</h3>
              <p>HELOC rates can change over time, affecting your payment</p>
            </div>
            <div className="requirement-card warning">
              <div className="req-icon">🎯</div>
              <h3>Discipline Required</h3>
              <p>Success depends on maintaining spending discipline</p>
            </div>
          </div>
        </section>

        {/* Disclaimer */}
        <section className="aio-disclaimer-section">
          <div className="disclaimer-content">
            <strong>Important Disclaimer:</strong> The All In One Loan strategy uses a variable-rate HELOC
            that may change over time. Results shown are estimates based on consistent cashflow and current rates.
            Actual savings depend on your spending habits, income consistency, rate changes, and market conditions.
            This calculator is for educational purposes only. Consult a licensed mortgage professional for
            personalized advice before making any financial decisions.
          </div>
        </section>
      </main>
    </div>
  );
};

export default AllInOneLoan;
