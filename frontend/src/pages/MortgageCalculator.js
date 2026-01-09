import React, { useState, useEffect, useCallback } from 'react';
import './MortgageCalculator.css';

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
];

const formatCurrency = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
};

const formatPercent = (value, decimals = 3) => {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(decimals)}%`;
};

// Loan calculation functions
const calculateMonthlyPayment = (principal, annualRate, years) => {
  const monthlyRate = annualRate / 100 / 12;
  const numPayments = years * 12;
  if (monthlyRate === 0) return principal / numPayments;
  return principal * (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) /
    (Math.pow(1 + monthlyRate, numPayments) - 1);
};

const calculateAPR = (principal, monthlyPayment, closingCosts, years) => {
  // Simplified APR calculation
  const totalLoan = principal + closingCosts;
  const monthlyRate = monthlyPayment / totalLoan;
  return monthlyRate * 12 * 100 * 1.008; // Approximate adjustment
};

const calculatePMI = (loanAmount, homeValue, creditScore) => {
  const ltv = (loanAmount / homeValue) * 100;
  if (ltv <= 80) return 0;

  // PMI rate based on LTV and credit score
  let pmiRate = 0.005; // 0.5% default
  if (ltv > 95) pmiRate = 0.01;
  else if (ltv > 90) pmiRate = 0.008;
  else if (ltv > 85) pmiRate = 0.006;

  if (creditScore < 680) pmiRate += 0.002;
  else if (creditScore >= 760) pmiRate -= 0.001;

  return (loanAmount * pmiRate) / 12;
};

function MortgageCalculator() {
  // Scenario inputs
  const [scenarios, setScenarios] = useState([
    { id: 1, name: 'Scenario 1', purchasePrice: 275000, downPayment: 4981, interestRate: 5.75, term: 30 },
    { id: 2, name: 'Scenario 2', purchasePrice: 325000, downPayment: 5887, interestRate: 5.75, term: 30 },
    { id: 3, name: 'Scenario 3', purchasePrice: 329900, downPayment: 5975, interestRate: 5.75, term: 30 },
  ]);

  // Shared settings
  const [settings, setSettings] = useState({
    creditScore: 720,
    state: 'CA',
    propertyTax: 1.1, // percentage
    insurance: 1200, // annual
    closingCostPercent: 3,
  });

  // Calculated results
  const [results, setResults] = useState([]);

  // Calculate all scenarios
  const calculateScenarios = useCallback(() => {
    const calculated = scenarios.map((scenario, index) => {
      const loanAmount = scenario.purchasePrice - scenario.downPayment;
      const downPaymentPercent = (scenario.downPayment / scenario.purchasePrice) * 100;
      const ltv = (loanAmount / scenario.purchasePrice) * 100;

      const monthlyPI = calculateMonthlyPayment(loanAmount, scenario.interestRate, scenario.term);
      const monthlyTax = (scenario.purchasePrice * (settings.propertyTax / 100)) / 12;
      const monthlyInsurance = settings.insurance / 12;
      const monthlyPMI = calculatePMI(loanAmount, scenario.purchasePrice, settings.creditScore);

      const totalMonthlyPayment = monthlyPI + monthlyTax + monthlyInsurance + monthlyPMI;
      const closingCosts = loanAmount * (settings.closingCostPercent / 100);
      const cashToClose = scenario.downPayment + closingCosts;

      const apr = calculateAPR(loanAmount, monthlyPI, closingCosts, scenario.term);

      return {
        ...scenario,
        loanAmount,
        downPaymentPercent,
        ltv,
        monthlyPI,
        monthlyTax,
        monthlyInsurance,
        monthlyPMI,
        totalMonthlyPayment,
        closingCosts,
        cashToClose,
        apr,
        termMonths: scenario.term * 12,
      };
    });

    // Calculate monthly savings (compared to highest payment)
    const maxPayment = Math.max(...calculated.map(r => r.totalMonthlyPayment));
    calculated.forEach(r => {
      r.monthlySavings = maxPayment - r.totalMonthlyPayment;
    });

    setResults(calculated);
  }, [scenarios, settings]);

  useEffect(() => {
    calculateScenarios();
  }, [calculateScenarios]);

  // Update scenario
  const updateScenario = (id, field, value) => {
    setScenarios(prev => prev.map(s =>
      s.id === id ? { ...s, [field]: parseFloat(value) || 0 } : s
    ));
  };

  // Update scenario name
  const updateScenarioName = (id, name) => {
    setScenarios(prev => prev.map(s =>
      s.id === id ? { ...s, name } : s
    ));
  };

  // Add scenario
  const addScenario = () => {
    if (scenarios.length >= 5) return;
    const newId = Math.max(...scenarios.map(s => s.id)) + 1;
    setScenarios(prev => [...prev, {
      id: newId,
      name: `Scenario ${newId}`,
      purchasePrice: 350000,
      downPayment: 17500,
      interestRate: 5.75,
      term: 30,
    }]);
  };

  // Remove scenario
  const removeScenario = (id) => {
    if (scenarios.length <= 1) return;
    setScenarios(prev => prev.filter(s => s.id !== id));
  };

  // Comparison rows configuration
  const comparisonRows = [
    { key: 'purchasePrice', label: 'Purchase Price:', format: formatCurrency, editable: true },
    { key: 'downPayment', label: 'Down Payment:', format: formatCurrency, editable: true, subLabel: (r) => `(${r.downPaymentPercent.toFixed(1)}%)` },
    { key: 'loanAmount', label: 'Loan Amount:', format: formatCurrency },
    { key: 'interestRate', label: 'Interest Rate:', format: (v) => formatPercent(v, 3), editable: true },
    { key: 'apr', label: 'APR:', format: (v) => `*${formatPercent(v, 3)}` },
    { key: 'termMonths', label: 'Term (mos):', format: (v) => v },
    { key: 'totalMonthlyPayment', label: 'Payment:', format: formatCurrency, highlight: true },
    { key: 'cashToClose', label: 'Cash To Close:', format: formatCurrency },
    { key: 'monthlySavings', label: 'Monthly Savings', format: formatCurrency, savings: true },
  ];

  return (
    <div className="mortgage-calculator-page">
      <div className="calculator-header">
        <h1>Mortgage Calculator</h1>
        <p>Compare loan scenarios side-by-side to find your best option</p>
      </div>

      {/* Settings Bar */}
      <div className="calculator-settings">
        <div className="setting-item">
          <label>Credit Score</label>
          <select
            value={settings.creditScore}
            onChange={(e) => setSettings(prev => ({ ...prev, creditScore: parseInt(e.target.value) }))}
          >
            <option value="620">620-659</option>
            <option value="660">660-699</option>
            <option value="700">700-739</option>
            <option value="720">720-759</option>
            <option value="760">760-799</option>
            <option value="800">800+</option>
          </select>
        </div>
        <div className="setting-item">
          <label>State</label>
          <select
            value={settings.state}
            onChange={(e) => setSettings(prev => ({ ...prev, state: e.target.value }))}
          >
            {US_STATES.map(state => (
              <option key={state} value={state}>{state}</option>
            ))}
          </select>
        </div>
        <div className="setting-item">
          <label>Property Tax %</label>
          <input
            type="number"
            step="0.1"
            value={settings.propertyTax}
            onChange={(e) => setSettings(prev => ({ ...prev, propertyTax: parseFloat(e.target.value) || 0 }))}
          />
        </div>
        <div className="setting-item">
          <label>Annual Insurance</label>
          <input
            type="number"
            value={settings.insurance}
            onChange={(e) => setSettings(prev => ({ ...prev, insurance: parseFloat(e.target.value) || 0 }))}
          />
        </div>
        <div className="setting-item">
          <label>Closing Costs %</label>
          <input
            type="number"
            step="0.5"
            value={settings.closingCostPercent}
            onChange={(e) => setSettings(prev => ({ ...prev, closingCostPercent: parseFloat(e.target.value) || 0 }))}
          />
        </div>
      </div>

      {/* Comparison Table */}
      <div className="comparison-container">
        <table className="comparison-table">
          <thead>
            <tr>
              <th className="label-column"></th>
              {results.map((result) => (
                <th key={result.id} className="scenario-column">
                  <div className="scenario-header">
                    <input
                      type="text"
                      className="scenario-name-input"
                      value={result.name}
                      onChange={(e) => updateScenarioName(result.id, e.target.value)}
                    />
                    {scenarios.length > 1 && (
                      <button
                        className="remove-scenario-btn"
                        onClick={() => removeScenario(result.id)}
                        title="Remove scenario"
                      >
                        ×
                      </button>
                    )}
                  </div>
                </th>
              ))}
              {scenarios.length < 5 && (
                <th className="add-column">
                  <button className="add-scenario-btn" onClick={addScenario}>
                    + Add
                  </button>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {comparisonRows.map((row, index) => (
              <tr key={row.key} className={index % 2 === 0 ? 'even-row' : 'odd-row'}>
                <td className="label-cell">{row.label}</td>
                {results.map((result) => (
                  <td
                    key={result.id}
                    className={`value-cell ${row.highlight ? 'highlight' : ''} ${row.savings ? 'savings-cell' : ''}`}
                  >
                    {row.editable ? (
                      <div className="editable-cell">
                        {row.key === 'interestRate' ? (
                          <input
                            type="number"
                            step="0.125"
                            value={result[row.key]}
                            onChange={(e) => updateScenario(result.id, row.key, e.target.value)}
                            className="cell-input rate-input"
                          />
                        ) : (
                          <input
                            type="number"
                            value={result[row.key]}
                            onChange={(e) => updateScenario(result.id, row.key, e.target.value)}
                            className="cell-input"
                          />
                        )}
                        {row.subLabel && <span className="sub-label">{row.subLabel(result)}</span>}
                      </div>
                    ) : (
                      <span className={row.savings ? (result[row.key] > 0 ? 'positive' : result[row.key] < 0 ? 'negative' : 'neutral') : ''}>
                        {row.format(result[row.key])}
                      </span>
                    )}
                  </td>
                ))}
                {scenarios.length < 5 && <td className="add-column-spacer"></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Payment Breakdown Section */}
      <div className="breakdown-section">
        <h2>Monthly Payment Breakdown</h2>
        <div className="breakdown-grid">
          {results.map((result) => (
            <div key={result.id} className="breakdown-card">
              <h3>{result.name}</h3>
              <div className="breakdown-items">
                <div className="breakdown-row">
                  <span>Principal & Interest</span>
                  <span>{formatCurrency(result.monthlyPI)}</span>
                </div>
                <div className="breakdown-row">
                  <span>Property Tax</span>
                  <span>{formatCurrency(result.monthlyTax)}</span>
                </div>
                <div className="breakdown-row">
                  <span>Insurance</span>
                  <span>{formatCurrency(result.monthlyInsurance)}</span>
                </div>
                {result.monthlyPMI > 0 && (
                  <div className="breakdown-row">
                    <span>PMI</span>
                    <span>{formatCurrency(result.monthlyPMI)}</span>
                  </div>
                )}
                <div className="breakdown-row total">
                  <span>Total Payment</span>
                  <span>{formatCurrency(result.totalMonthlyPayment)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="calculator-disclaimer">
        <p>
          * APR is an estimate. Actual APR may vary based on loan type, credit profile, and other factors.
          These calculations are for illustrative purposes only and do not constitute a loan offer.
        </p>
      </div>
    </div>
  );
}

export default MortgageCalculator;
