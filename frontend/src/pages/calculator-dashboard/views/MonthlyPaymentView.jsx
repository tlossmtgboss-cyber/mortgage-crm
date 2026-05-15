import React, { useState, useMemo } from 'react';
import { formatCurrency, formatCurrencyFull } from '../../../services/calculator/CalculatorService';

// All In One Loan Comparison Component
const AllInOneComparison = ({ purchasePrice, conventionalRate }) => {
  const [monthlyIncome, setMonthlyIncome] = useState(8000);
  const [monthlyExpenses, setMonthlyExpenses] = useState(4000);
  const [aioRate, setAioRate] = useState(7.5);

  const downPaymentPct = 20;
  const downPayment = purchasePrice * (downPaymentPct / 100);
  const loanAmount = purchasePrice - downPayment;

  const calcTraditionalMonthly = (principal, rate, years = 30) => {
    const monthlyRate = rate / 100 / 12;
    const numPayments = years * 12;
    if (monthlyRate === 0) return principal / numPayments;
    return principal * (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) / (Math.pow(1 + monthlyRate, numPayments) - 1);
  };

  const traditionalMonthly = calcTraditionalMonthly(loanAmount, conventionalRate);
  const traditionalTotal30Yr = traditionalMonthly * 360;
  const traditionalInterest = traditionalTotal30Yr - loanAmount;

  const monthlyNetCashflow = monthlyIncome - monthlyExpenses;
  const aioInterestOnlyMonthly = (loanAmount * (aioRate / 100)) / 12;

  const simulateAIOPayoff = () => {
    let balance = loanAmount;
    let months = 0;
    let totalInterestPaid = 0;
    const maxMonths = 360;

    while (balance > 0 && months < maxMonths) {
      const monthlyInterest = (balance * (aioRate / 100)) / 12;
      totalInterestPaid += monthlyInterest;
      const netReduction = monthlyNetCashflow - monthlyInterest;
      if (netReduction > 0) {
        balance -= netReduction;
      } else {
        balance -= netReduction;
      }
      months++;
      if (balance <= 0) break;
    }

    return {
      months: Math.min(months, maxMonths),
      years: Math.min(months / 12, 30),
      totalInterestPaid,
      paidOff: balance <= 0,
    };
  };

  const aioResult = simulateAIOPayoff();
  const interestSavings = traditionalInterest - aioResult.totalInterestPaid;
  const yearsSaved = 30 - aioResult.years;

  return (
    <div className="allinone-section">
      <div className="section-header-special">
        <div className="header-badge">
          <span className="badge-icon">{'\u{1F3E6}'}</span>
          <span>Alternative Strategy</span>
        </div>
        <h3>All In One Loan Comparison</h3>
        <p>First-Lien HELOC with Velocity Banking — Pay off your mortgage faster</p>
      </div>

      <div className="aio-inputs">
        <div className="aio-input-group">
          <label>Monthly Income</label>
          <div className="input-with-prefix">
            <span className="prefix">$</span>
            <input type="number" value={monthlyIncome} onChange={(e) => setMonthlyIncome(Number(e.target.value) || 0)} />
          </div>
        </div>
        <div className="aio-input-group">
          <label>Monthly Expenses</label>
          <div className="input-with-prefix">
            <span className="prefix">$</span>
            <input type="number" value={monthlyExpenses} onChange={(e) => setMonthlyExpenses(Number(e.target.value) || 0)} />
          </div>
        </div>
        <div className="aio-input-group">
          <label>HELOC Rate</label>
          <div className="input-with-suffix">
            <input type="number" step="0.125" value={aioRate} onChange={(e) => setAioRate(Number(e.target.value) || 0)} />
            <span className="suffix">%</span>
          </div>
        </div>
      </div>

      <div className="aio-comparison-grid">
        <div className="aio-card traditional">
          <div className="aio-card-header">
            <span className="aio-card-badge">Traditional</span>
            <h4>30-Year Fixed Mortgage</h4>
          </div>
          <div className="aio-card-body">
            <div className="aio-stat"><span className="stat-label">Loan Amount</span><span className="stat-value">{formatCurrency(loanAmount)}</span></div>
            <div className="aio-stat"><span className="stat-label">Interest Rate</span><span className="stat-value">{conventionalRate}%</span></div>
            <div className="aio-stat"><span className="stat-label">Monthly Payment</span><span className="stat-value">{formatCurrency(traditionalMonthly)}</span></div>
            <div className="aio-stat highlight"><span className="stat-label">Total Interest Paid</span><span className="stat-value negative">{formatCurrency(traditionalInterest)}</span></div>
            <div className="aio-stat"><span className="stat-label">Payoff Time</span><span className="stat-value">30 years</span></div>
          </div>
        </div>

        <div className="aio-card allinone featured">
          <div className="aio-card-header">
            <span className="aio-card-badge special">All In One</span>
            <h4>First-Lien HELOC</h4>
          </div>
          <div className="aio-card-body">
            <div className="aio-stat"><span className="stat-label">Credit Line</span><span className="stat-value">{formatCurrency(loanAmount)}</span></div>
            <div className="aio-stat"><span className="stat-label">HELOC Rate</span><span className="stat-value">{aioRate}%</span></div>
            <div className="aio-stat"><span className="stat-label">Interest-Only Min</span><span className="stat-value">{formatCurrency(aioInterestOnlyMonthly)}</span></div>
            <div className="aio-stat highlight"><span className="stat-label">Total Interest Paid</span><span className="stat-value positive">{formatCurrency(aioResult.totalInterestPaid)}</span></div>
            <div className="aio-stat"><span className="stat-label">Payoff Time</span><span className="stat-value positive">{aioResult.years.toFixed(1)} years</span></div>
          </div>
        </div>
      </div>

      {interestSavings > 0 && (
        <div className="aio-savings-banner">
          <div className="savings-highlight">
            <div className="savings-amount">{formatCurrency(interestSavings)}</div>
            <div className="savings-label">Potential Interest Savings</div>
          </div>
          <div className="savings-details">
            <div className="savings-detail"><span className="detail-icon">{'\u{23F1}️'}</span><span>Pay off {yearsSaved.toFixed(1)} years faster</span></div>
            <div className="savings-detail"><span className="detail-icon">{'\u{1F4B5}'}</span><span>Your monthly cashflow: {formatCurrency(monthlyNetCashflow)}</span></div>
          </div>
        </div>
      )}

      <div className="aio-how-it-works">
        <h4>How All In One Works</h4>
        <div className="how-steps">
          <div className="how-step"><div className="step-number">1</div><div className="step-content"><strong>Deposit All Income</strong><p>Your paychecks go directly into the HELOC, immediately reducing your balance and interest.</p></div></div>
          <div className="how-step"><div className="step-number">2</div><div className="step-content"><strong>Pay Expenses as Needed</strong><p>Use the built-in checking account for bills. Only borrow what you spend.</p></div></div>
          <div className="how-step"><div className="step-number">3</div><div className="step-content"><strong>Interest Calculated Daily</strong><p>Unlike traditional mortgages, interest is based on your daily balance, not the original loan amount.</p></div></div>
          <div className="how-step"><div className="step-number">4</div><div className="step-content"><strong>Accelerated Payoff</strong><p>Your positive cashflow continuously reduces principal, potentially paying off your home in 5-10 years.</p></div></div>
        </div>
      </div>

      <div className="aio-requirements">
        <h4>Requirements</h4>
        <div className="req-grid">
          <div className="req-item"><span className="req-icon">{'\u{1F4CA}'}</span><span className="req-text">680+ Credit Score</span></div>
          <div className="req-item"><span className="req-icon">{'\u{1F4B0}'}</span><span className="req-text">20% Down Payment</span></div>
          <div className="req-item"><span className="req-icon">{'\u{1F4C8}'}</span><span className="req-text">Positive Monthly Cashflow</span></div>
          <div className="req-item"><span className="req-icon">{'\u{1F3E0}'}</span><span className="req-text">Primary Residence</span></div>
        </div>
      </div>

      <div className="aio-disclaimer">
        <strong>Note:</strong> The All In One Loan has a variable rate that may change over time.
        Results shown are estimates based on consistent cashflow. Actual savings depend on your
        spending habits, income consistency, and market conditions. Consult a mortgage professional
        for personalized advice.
      </div>
    </div>
  );
};

const MonthlyPaymentView = ({ data }) => {
  const [purchasePrice, setPurchasePrice] = useState(data.homePrice || 285000);

  const colors = {
    principalInterest: '#3b82f6',
    propertyTax: '#22c55e',
    insurance: '#f59e0b',
    pmi: '#ef4444',
    mip: '#B8924A',
  };

  const calculateMonthlyPI = (principal, annualRate, termYears = 30) => {
    const monthlyRate = annualRate / 100 / 12;
    const numPayments = termYears * 12;
    if (monthlyRate === 0) return principal / numPayments;
    return principal * (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) / (Math.pow(1 + monthlyRate, numPayments) - 1);
  };

  const generateScenarios = useMemo(() => {
    const taxRate = 0.0125;
    const insuranceRate = 0.0035;
    const convRate = data.rate || 6.875;
    const fhaRate = (data.rate || 6.875) - 0.25;

    const scenarios = [
      { id: 'conv-3', label: '3% Down', type: 'Conventional', downPct: 3, rate: convRate, color: '#3b82f6' },
      { id: 'fha-3.5', label: '3.5% Down', type: 'FHA', downPct: 3.5, rate: fhaRate, color: '#B8924A' },
      { id: 'conv-5', label: '5% Down', type: 'Conventional', downPct: 5, rate: convRate, color: '#3b82f6', recommended: true },
      { id: 'fha-5', label: '5% Down', type: 'FHA', downPct: 5, rate: fhaRate, color: '#B8924A' },
    ];

    return scenarios.map(scenario => {
      const downPayment = purchasePrice * (scenario.downPct / 100);
      let loanAmount = purchasePrice - downPayment;
      const ltv = (loanAmount / purchasePrice) * 100;

      let upfrontMIP = 0;
      let monthlyMIP = 0;
      let monthlyPMI = 0;

      if (scenario.type === 'FHA') {
        upfrontMIP = loanAmount * 0.0175;
        loanAmount += upfrontMIP;
        const annualMIPRate = ltv > 95 ? 0.0055 : 0.0050;
        monthlyMIP = (loanAmount * annualMIPRate) / 12;
      } else {
        const pmiRate = ltv > 95 ? 0.0095 : ltv > 90 ? 0.0075 : 0.0055;
        monthlyPMI = (loanAmount * pmiRate) / 12;
      }

      const monthlyPI = calculateMonthlyPI(loanAmount, scenario.rate);
      const monthlyTax = (purchasePrice * taxRate) / 12;
      const monthlyInsurance = (purchasePrice * insuranceRate) / 12;
      const totalPayment = monthlyPI + monthlyTax + monthlyInsurance + monthlyPMI + monthlyMIP;

      const yearsToRemovePMI = scenario.type === 'FHA'
        ? (ltv > 90 ? 'Life of loan' : '11 years')
        : `~${Math.ceil((ltv - 78) / 2)} years`;

      return {
        ...scenario,
        downPayment,
        loanAmount,
        ltv,
        upfrontMIP,
        piti: { principalInterest: monthlyPI, propertyTax: monthlyTax, insurance: monthlyInsurance, pmi: monthlyPMI, mip: monthlyMIP, total: totalPayment },
        pmiDuration: yearsToRemovePMI,
      };
    });
  }, [purchasePrice, data.rate]);

  const getComponents = (scenario) => {
    const { piti } = scenario;
    const components = [
      { key: 'principalInterest', label: 'Principal & Interest', value: piti.principalInterest, color: colors.principalInterest },
      { key: 'propertyTax', label: 'Property Tax', value: piti.propertyTax, color: colors.propertyTax },
      { key: 'insurance', label: 'Insurance', value: piti.insurance, color: colors.insurance },
    ];
    if (scenario.type === 'FHA' && piti.mip > 0) {
      components.push({ key: 'mip', label: 'MIP (FHA)', value: piti.mip, color: colors.mip });
    } else if (piti.pmi > 0) {
      components.push({ key: 'pmi', label: 'PMI', value: piti.pmi, color: colors.pmi });
    }
    return components;
  };

  const lowestPayment = Math.min(...generateScenarios.map(s => s.piti.total));
  const lowestCashNeeded = Math.min(...generateScenarios.map(s => s.downPayment));

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Monthly Payment Comparison</h2>
        <p className="detail-subtitle">Compare Conventional vs FHA loans at different down payments</p>
      </div>

      <div className="price-slider-section">
        <div className="slider-header">
          <label>Purchase Price</label>
          <div className="slider-value">{formatCurrency(purchasePrice)}</div>
        </div>
        <input type="range" min="150000" max="750000" step="5000" value={purchasePrice} onChange={(e) => setPurchasePrice(Number(e.target.value))} className="price-slider" />
        <div className="slider-range"><span>$150,000</span><span>$750,000</span></div>
      </div>

      <div className="loan-type-headers">
        <div className="loan-type-header conv">
          <span className="type-badge conv">Conventional</span>
          <span className="type-rate">{data.rate || 6.875}% rate</span>
        </div>
        <div className="loan-type-header fha">
          <span className="type-badge fha">FHA</span>
          <span className="type-rate">{((data.rate || 6.875) - 0.25).toFixed(3)}% rate</span>
        </div>
      </div>

      <div className="payment-comparison-grid four-col">
        {generateScenarios.map((scenario) => {
          const components = getComponents(scenario);
          const isLowest = scenario.piti.total === lowestPayment;

          return (
            <div key={scenario.id} className={`payment-card ${scenario.type.toLowerCase()} ${scenario.recommended ? 'recommended' : ''}`}>
              <div className="payment-card-header">
                <div className="payment-card-title">
                  {scenario.label}
                  {scenario.recommended && <span className="rec-tag">Recommended</span>}
                </div>
                <div className="payment-card-type">{scenario.type}</div>
                <div className="payment-card-subtitle">{formatCurrency(scenario.downPayment)} down</div>
              </div>
              <div className="payment-total">
                <div className="payment-total-label">Monthly Payment</div>
                <div className="payment-total-amount">
                  {formatCurrencyFull(scenario.piti.total)}
                  {isLowest && <span className="lowest-tag">Lowest</span>}
                </div>
              </div>
              <div className="payment-bar">
                {components.map((comp) => (
                  <div key={comp.key} className="payment-bar-segment" style={{ width: `${(comp.value / scenario.piti.total) * 100}%`, backgroundColor: comp.color }} title={`${comp.label}: ${formatCurrencyFull(comp.value)}`} />
                ))}
              </div>
              <div className="payment-breakdown">
                {components.map((comp) => (
                  <div key={comp.key} className="payment-line">
                    <div className="payment-line-indicator" style={{ backgroundColor: comp.color }} />
                    <div className="payment-line-label">{comp.label}</div>
                    <div className="payment-line-value">{formatCurrencyFull(comp.value)}</div>
                  </div>
                ))}
              </div>
              <div className="payment-card-footer">
                <div className="footer-row"><span>Loan Amount</span><span>{formatCurrency(scenario.loanAmount)}</span></div>
                <div className="footer-row"><span>LTV</span><span>{scenario.ltv.toFixed(1)}%</span></div>
                {scenario.type === 'FHA' && scenario.upfrontMIP > 0 && (
                  <div className="footer-row mip-note"><span>Upfront MIP</span><span>{formatCurrency(scenario.upfrontMIP)}</span></div>
                )}
                <div className="footer-row pmi-note"><span>{scenario.type === 'FHA' ? 'MIP Duration' : 'PMI Duration'}</span><span>{scenario.pmiDuration}</span></div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="payment-legend">
        <h4>Payment Components</h4>
        <div className="legend-items">
          <div className="legend-item"><div className="legend-color" style={{ backgroundColor: colors.principalInterest }} /><span>Principal & Interest — Goes toward loan balance</span></div>
          <div className="legend-item"><div className="legend-color" style={{ backgroundColor: colors.propertyTax }} /><span>Property Tax — Held in escrow, paid annually</span></div>
          <div className="legend-item"><div className="legend-color" style={{ backgroundColor: colors.insurance }} /><span>Homeowners Insurance — Required by lender</span></div>
          <div className="legend-item"><div className="legend-color" style={{ backgroundColor: colors.pmi }} /><span>PMI (Conventional) — Removable at 78% LTV</span></div>
          <div className="legend-item"><div className="legend-color" style={{ backgroundColor: colors.mip }} /><span>MIP (FHA) — 1.75% upfront + annual premium</span></div>
        </div>
      </div>

      <div className="comparison-insights">
        <div className="insight-card">
          <div className="insight-icon">{'\u{1F4B0}'}</div>
          <div className="insight-content"><strong>Conventional Pros:</strong> PMI can be removed once you reach 78% LTV. No upfront mortgage insurance. Better for higher credit scores (740+).</div>
        </div>
        <div className="insight-card">
          <div className="insight-icon">{'\u{1F3E0}'}</div>
          <div className="insight-content"><strong>FHA Pros:</strong> Lower credit score requirements (580+). Lower rates. Easier qualification. Great for first-time buyers.</div>
        </div>
      </div>

      <AllInOneComparison purchasePrice={purchasePrice} conventionalRate={data.rate || 6.875} />
    </div>
  );
};

export default MonthlyPaymentView;
