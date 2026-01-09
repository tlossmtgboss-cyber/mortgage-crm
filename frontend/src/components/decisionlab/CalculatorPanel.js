import React, { useCallback } from 'react';
import { useMortgageLab } from '../../contexts/MortgageLabContext';
import PaymentCalculator from '../PaymentCalculator';
import './CalculatorPanel.css';

const CALCULATOR_TABS = [
  { id: 'payment', label: 'Payment', icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  { id: 'prequal', label: 'Pre-Qual', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
  { id: 'compare', label: 'Compare', icon: 'M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3' },
  { id: 'exit', label: 'Exit Plan', icon: 'M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1' },
];

function CalculatorPanel() {
  const {
    calculatorPanelOpen,
    activeCalculator,
    setActiveCalculator,
    toggleCalculatorPanel,
    sharedData,
    getCalculatorProps,
    syncFromCalculator,
  } = useMortgageLab();

  // Handle calculator results
  const handleCalculationComplete = useCallback((result) => {
    syncFromCalculator(result);
  }, [syncFromCalculator]);

  if (!calculatorPanelOpen) {
    return (
      <button
        className="calculator-panel-toggle collapsed"
        onClick={toggleCalculatorPanel}
        title="Open Calculator Panel"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
        <span>Calculators</span>
      </button>
    );
  }

  return (
    <div className="calculator-panel">
      <div className="calculator-panel-header">
        <h3>Calculators</h3>
        <button
          className="close-panel-btn"
          onClick={toggleCalculatorPanel}
          title="Close Calculator Panel"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Calculator Tabs */}
      <div className="calculator-tabs">
        {CALCULATOR_TABS.map(tab => (
          <button
            key={tab.id}
            className={`calculator-tab ${activeCalculator === tab.id ? 'active' : ''}`}
            onClick={() => setActiveCalculator(tab.id)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d={tab.icon} />
            </svg>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Data Source Indicator */}
      {sharedData.purchasePrice && (
        <div className="data-source-indicator">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>
            Pre-filled from {sharedData.purchasePrice ? 'your scenario' : 'default values'}
          </span>
        </div>
      )}

      {/* Calculator Content */}
      <div className="calculator-content">
        {activeCalculator === 'payment' && (
          <PaymentCalculator
            {...getCalculatorProps()}
            onCalculationComplete={handleCalculationComplete}
            showAdvancedOptions={true}
            compact={true}
          />
        )}

        {activeCalculator === 'prequal' && (
          <PrequalCalculator sharedData={sharedData} />
        )}

        {activeCalculator === 'compare' && (
          <CompareCalculator sharedData={sharedData} />
        )}

        {activeCalculator === 'exit' && (
          <ExitStrategyCalculator sharedData={sharedData} />
        )}
      </div>
    </div>
  );
}

// Simple Pre-Qualification Calculator
function PrequalCalculator({ sharedData }) {
  const [income, setIncome] = React.useState('');
  const [debt, setDebt] = React.useState('');
  const [results, setResults] = React.useState(null);

  const calculatePrequal = () => {
    const monthlyIncome = parseFloat(income) || 0;
    const monthlyDebt = parseFloat(debt) || 0;

    if (monthlyIncome <= 0) return;

    // Standard DTI limits
    const maxDTI = 0.43; // 43% back-end DTI
    const maxHousingDTI = 0.28; // 28% front-end DTI

    const maxHousingPayment = monthlyIncome * maxHousingDTI;
    const maxTotalPayment = (monthlyIncome * maxDTI) - monthlyDebt;
    const recommendedPayment = Math.min(maxHousingPayment, maxTotalPayment);

    // Estimate max purchase price (rough: payment * 200 for typical 30yr mortgage)
    const estimatedMaxPrice = recommendedPayment * 200;

    setResults({
      monthlyIncome,
      monthlyDebt,
      currentDTI: monthlyDebt / monthlyIncome,
      maxHousingPayment: Math.max(0, recommendedPayment),
      estimatedMaxPrice: Math.max(0, estimatedMaxPrice),
    });
  };

  return (
    <div className="prequal-calculator">
      <h4>Quick Pre-Qualification</h4>
      <p className="calc-description">
        Estimate how much home you can afford based on your income and existing debts.
      </p>

      <div className="prequal-form">
        <div className="form-group">
          <label>Monthly Gross Income</label>
          <div className="input-with-prefix">
            <span>$</span>
            <input
              type="number"
              value={income}
              onChange={(e) => setIncome(e.target.value)}
              placeholder="8,000"
            />
          </div>
        </div>

        <div className="form-group">
          <label>Monthly Debt Payments</label>
          <div className="input-with-prefix">
            <span>$</span>
            <input
              type="number"
              value={debt}
              onChange={(e) => setDebt(e.target.value)}
              placeholder="500"
            />
          </div>
          <span className="help-text">Car loans, credit cards, student loans, etc.</span>
        </div>

        <button className="calculate-btn" onClick={calculatePrequal}>
          Calculate Affordability
        </button>
      </div>

      {results && (
        <div className="prequal-results">
          <div className="result-item highlight">
            <span className="result-label">Estimated Max Home Price</span>
            <span className="result-value">
              ${Math.round(results.estimatedMaxPrice).toLocaleString()}
            </span>
          </div>
          <div className="result-item">
            <span className="result-label">Max Housing Payment</span>
            <span className="result-value">
              ${Math.round(results.maxHousingPayment).toLocaleString()}/mo
            </span>
          </div>
          <div className="result-item">
            <span className="result-label">Current DTI</span>
            <span className="result-value">
              {(results.currentDTI * 100).toFixed(1)}%
            </span>
          </div>

          {sharedData.purchasePrice && (
            <div className={`scenario-comparison ${results.estimatedMaxPrice >= sharedData.purchasePrice ? 'positive' : 'warning'}`}>
              <span>Your scenario: ${sharedData.purchasePrice.toLocaleString()}</span>
              {results.estimatedMaxPrice >= sharedData.purchasePrice ? (
                <span className="status">Within budget</span>
              ) : (
                <span className="status">Above estimated max</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Loan Comparison Calculator
function CompareCalculator({ sharedData }) {
  const scenarios = [
    {
      name: '30-Year Fixed',
      rate: 6.5,
      term: 30,
      points: 0,
    },
    {
      name: '15-Year Fixed',
      rate: 5.875,
      term: 15,
      points: 0,
    },
    {
      name: '30-Year with Points',
      rate: 6.125,
      term: 30,
      points: 1.5,
    },
  ];

  const loanAmount = sharedData.loanAmount || (sharedData.purchasePrice - sharedData.downPayment) || 400000;

  const calculatePayment = (principal, rate, years) => {
    const monthlyRate = rate / 100 / 12;
    const numPayments = years * 12;
    if (monthlyRate === 0) return principal / numPayments;
    return principal * (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) /
      (Math.pow(1 + monthlyRate, numPayments) - 1);
  };

  const calculateTotalInterest = (principal, payment, years) => {
    return (payment * years * 12) - principal;
  };

  return (
    <div className="compare-calculator">
      <h4>Loan Comparison</h4>
      <p className="calc-description">
        Compare different loan options for a ${loanAmount.toLocaleString()} loan.
      </p>

      <div className="comparison-grid">
        {scenarios.map((scenario, index) => {
          const payment = calculatePayment(loanAmount, scenario.rate, scenario.term);
          const totalInterest = calculateTotalInterest(loanAmount, payment, scenario.term);
          const pointsCost = (scenario.points / 100) * loanAmount;

          return (
            <div key={index} className="comparison-card">
              <h5>{scenario.name}</h5>
              <div className="comparison-details">
                <div className="detail-row">
                  <span>Rate</span>
                  <span>{scenario.rate}%</span>
                </div>
                <div className="detail-row">
                  <span>Term</span>
                  <span>{scenario.term} years</span>
                </div>
                <div className="detail-row highlight">
                  <span>Payment</span>
                  <span>${Math.round(payment).toLocaleString()}/mo</span>
                </div>
                <div className="detail-row">
                  <span>Total Interest</span>
                  <span>${Math.round(totalInterest).toLocaleString()}</span>
                </div>
                {scenario.points > 0 && (
                  <div className="detail-row">
                    <span>Points Cost</span>
                    <span>${Math.round(pointsCost).toLocaleString()}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="comparison-note">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>Rates shown are examples. Contact us for current rates.</span>
      </div>
    </div>
  );
}

// Exit Strategy Calculator
function ExitStrategyCalculator({ sharedData }) {
  const [yearsOwned, setYearsOwned] = React.useState('5');
  const [appreciationRate, setAppreciationRate] = React.useState('3');
  const [sellingCosts, setSellingCosts] = React.useState('6');
  const [results, setResults] = React.useState(null);

  const purchasePrice = sharedData.purchasePrice || 400000;
  const downPayment = sharedData.downPayment || 80000;
  const loanAmount = sharedData.loanAmount || (purchasePrice - downPayment);
  const interestRate = sharedData.interestRate || 6.5;

  const calculateExitStrategies = () => {
    const years = parseInt(yearsOwned) || 5;
    const appreciation = parseFloat(appreciationRate) / 100 || 0.03;
    const selling = parseFloat(sellingCosts) / 100 || 0.06;

    // Calculate future home value
    const futureValue = purchasePrice * Math.pow(1 + appreciation, years);

    // Calculate remaining loan balance (simplified)
    const monthlyRate = interestRate / 100 / 12;
    const totalPayments = 30 * 12;
    const monthlyPayment = loanAmount * (monthlyRate * Math.pow(1 + monthlyRate, totalPayments)) /
      (Math.pow(1 + monthlyRate, totalPayments) - 1);

    // Remaining balance calculation
    const remainingBalance = loanAmount * (Math.pow(1 + monthlyRate, totalPayments) - Math.pow(1 + monthlyRate, years * 12)) /
      (Math.pow(1 + monthlyRate, totalPayments) - 1);

    // Total equity
    const equity = futureValue - remainingBalance;

    // Exit Strategy 1: Sell
    const sellProceeds = futureValue - remainingBalance - (futureValue * selling);

    // Exit Strategy 2: Refinance (cash-out)
    const maxCashOut = (futureValue * 0.80) - remainingBalance; // 80% LTV
    const refinanceCosts = futureValue * 0.02; // 2% closing costs

    // Exit Strategy 3: Hold (rental income estimate)
    const estimatedRent = futureValue * 0.006; // 0.6% of value per month
    const estimatedExpenses = estimatedRent * 0.35; // 35% expenses
    const monthlyNetRent = estimatedRent - estimatedExpenses - monthlyPayment;
    const annualCashFlow = monthlyNetRent * 12;
    const capRate = (annualCashFlow + (monthlyPayment * 12 - (loanAmount - remainingBalance))) / futureValue * 100;

    setResults({
      yearsOwned: years,
      futureValue,
      equity,
      remainingBalance,
      sell: {
        proceeds: sellProceeds,
        sellingCosts: futureValue * selling,
        netGain: sellProceeds - downPayment,
      },
      refinance: {
        maxCashOut: Math.max(0, maxCashOut - refinanceCosts),
        newLoanAmount: futureValue * 0.80,
        closingCosts: refinanceCosts,
      },
      hold: {
        estimatedRent,
        monthlyNetCashFlow: monthlyNetRent,
        annualCashFlow,
        capRate: capRate > 0 ? capRate : 0,
      },
    });
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => {
    calculateExitStrategies();
  }, [yearsOwned, appreciationRate, sellingCosts, purchasePrice, downPayment, loanAmount, interestRate]);

  return (
    <div className="exit-calculator">
      <h4>Exit Strategy Planner</h4>
      <p className="calc-description">
        Plan your exit strategy: sell, refinance, or hold as rental.
      </p>

      <div className="prequal-form">
        <div className="form-group">
          <label>Years Until Exit</label>
          <select
            value={yearsOwned}
            onChange={(e) => setYearsOwned(e.target.value)}
            className="exit-select"
          >
            <option value="1">1 year</option>
            <option value="2">2 years</option>
            <option value="3">3 years</option>
            <option value="5">5 years</option>
            <option value="7">7 years</option>
            <option value="10">10 years</option>
            <option value="15">15 years</option>
          </select>
        </div>

        <div className="form-group">
          <label>Annual Appreciation</label>
          <div className="input-with-suffix">
            <input
              type="number"
              value={appreciationRate}
              onChange={(e) => setAppreciationRate(e.target.value)}
              step="0.5"
              min="0"
              max="10"
            />
            <span>%</span>
          </div>
        </div>

        <div className="form-group">
          <label>Selling Costs</label>
          <div className="input-with-suffix">
            <input
              type="number"
              value={sellingCosts}
              onChange={(e) => setSellingCosts(e.target.value)}
              step="0.5"
              min="0"
              max="10"
            />
            <span>%</span>
          </div>
        </div>
      </div>

      {results && (
        <div className="exit-results">
          <div className="result-item highlight">
            <span className="result-label">Projected Home Value</span>
            <span className="result-value">
              ${Math.round(results.futureValue).toLocaleString()}
            </span>
          </div>
          <div className="result-item">
            <span className="result-label">Estimated Equity</span>
            <span className="result-value">
              ${Math.round(results.equity).toLocaleString()}
            </span>
          </div>

          <div className="exit-strategies">
            <div className="strategy-card">
              <h5>Sell</h5>
              <div className="strategy-details">
                <div className="detail-row">
                  <span>Net Proceeds</span>
                  <span className="value-positive">
                    ${Math.round(results.sell.proceeds).toLocaleString()}
                  </span>
                </div>
                <div className="detail-row">
                  <span>Selling Costs</span>
                  <span>-${Math.round(results.sell.sellingCosts).toLocaleString()}</span>
                </div>
                <div className="detail-row highlight">
                  <span>Profit</span>
                  <span className={results.sell.netGain >= 0 ? 'value-positive' : 'value-negative'}>
                    ${Math.round(results.sell.netGain).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            <div className="strategy-card">
              <h5>Refinance</h5>
              <div className="strategy-details">
                <div className="detail-row">
                  <span>Max Cash-Out (80% LTV)</span>
                  <span className="value-positive">
                    ${Math.round(results.refinance.maxCashOut).toLocaleString()}
                  </span>
                </div>
                <div className="detail-row">
                  <span>New Loan Amount</span>
                  <span>${Math.round(results.refinance.newLoanAmount).toLocaleString()}</span>
                </div>
                <div className="detail-row">
                  <span>Est. Closing Costs</span>
                  <span>-${Math.round(results.refinance.closingCosts).toLocaleString()}</span>
                </div>
              </div>
            </div>

            <div className="strategy-card">
              <h5>Hold as Rental</h5>
              <div className="strategy-details">
                <div className="detail-row">
                  <span>Est. Monthly Rent</span>
                  <span>${Math.round(results.hold.estimatedRent).toLocaleString()}</span>
                </div>
                <div className="detail-row">
                  <span>Monthly Cash Flow</span>
                  <span className={results.hold.monthlyNetCashFlow >= 0 ? 'value-positive' : 'value-negative'}>
                    ${Math.round(results.hold.monthlyNetCashFlow).toLocaleString()}
                  </span>
                </div>
                <div className="detail-row highlight">
                  <span>Cap Rate</span>
                  <span>{results.hold.capRate.toFixed(1)}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="comparison-note">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>Projections are estimates. Actual results will vary based on market conditions.</span>
      </div>
    </div>
  );
}

export default CalculatorPanel;
