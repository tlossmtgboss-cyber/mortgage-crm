/**
 * PresentationEngine Component
 *
 * Interactive scenario explorer for MUM (Member Until Maturity) stage.
 * Allows borrowers to explore various equity options:
 * - Rate-and-term refinance calculator
 * - Cash-out refinance calculator
 * - HELOC/Home Equity Line of Credit analysis
 * - Sell/Net proceeds calculator
 * - Comparison tools
 */

import React, { useState, useMemo } from 'react';
import './PresentationEngine.css';

// =============================================================================
// CONSTANTS
// =============================================================================

const SCENARIOS = {
  REFINANCE: 'refinance',
  CASH_OUT: 'cashOut',
  HELOC: 'heloc',
  SELL: 'sell',
};

const SCENARIO_CONFIG = {
  [SCENARIOS.REFINANCE]: {
    id: SCENARIOS.REFINANCE,
    title: 'Rate & Term Refinance',
    subtitle: 'Lower your rate or change your term',
    icon: '🔄',
    color: '#3b82f6',
    benefits: ['Lower monthly payment', 'Reduce interest paid', 'Pay off faster'],
  },
  [SCENARIOS.CASH_OUT]: {
    id: SCENARIOS.CASH_OUT,
    title: 'Cash-Out Refinance',
    subtitle: 'Access your home equity',
    icon: '💰',
    color: '#2D7A52',
    benefits: ['Home improvements', 'Debt consolidation', 'Major purchases'],
  },
  [SCENARIOS.HELOC]: {
    id: SCENARIOS.HELOC,
    title: 'Home Equity Line',
    subtitle: 'Flexible access to equity',
    icon: '🏦',
    color: '#B8924A',
    benefits: ['Draw as needed', 'Interest only on what you use', 'Keeps first mortgage'],
  },
  [SCENARIOS.SELL]: {
    id: SCENARIOS.SELL,
    title: 'Sell Analysis',
    subtitle: 'Calculate your net proceeds',
    icon: '🏠',
    color: '#f59e0b',
    benefits: ['Know your equity', 'Plan your next move', 'Understand costs'],
  },
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function PresentationEngine({
  loanId,
  homeValue = 500000,
  loanBalance = 350000,
  currentRate = 6.5,
  monthlyPayment = 2200,
  onRequestQuote,
}) {
  const [activeScenario, setActiveScenario] = useState(SCENARIOS.REFINANCE);

  // Calculate base equity
  const equity = homeValue - loanBalance;

  return (
    <div className="presentation-engine">
      {/* Header */}
      <header className="pe-header">
        <div className="pe-header-content">
          <h2>Explore Your Options</h2>
          <p>See what opportunities your home equity unlocks</p>
        </div>
        <div className="equity-summary">
          <div className="equity-badge">
            <span className="equity-label">Your Equity</span>
            <span className="equity-value">{formatCurrency(equity)}</span>
          </div>
        </div>
      </header>

      {/* Scenario Selector */}
      <nav className="scenario-nav">
        {Object.values(SCENARIO_CONFIG).map((scenario) => (
          <button
            key={scenario.id}
            className={`scenario-tab ${activeScenario === scenario.id ? 'active' : ''}`}
            onClick={() => setActiveScenario(scenario.id)}
            style={{ '--accent-color': scenario.color }}
          >
            <span className="scenario-icon">{scenario.icon}</span>
            <span className="scenario-title">{scenario.title}</span>
          </button>
        ))}
      </nav>

      {/* Scenario Content */}
      <div className="scenario-content">
        {activeScenario === SCENARIOS.REFINANCE && (
          <RefinanceCalculator
            homeValue={homeValue}
            loanBalance={loanBalance}
            currentRate={currentRate}
            monthlyPayment={monthlyPayment}
            onRequestQuote={onRequestQuote}
          />
        )}
        {activeScenario === SCENARIOS.CASH_OUT && (
          <CashOutCalculator
            homeValue={homeValue}
            loanBalance={loanBalance}
            equity={equity}
            currentRate={currentRate}
            onRequestQuote={onRequestQuote}
          />
        )}
        {activeScenario === SCENARIOS.HELOC && (
          <HelocCalculator
            homeValue={homeValue}
            loanBalance={loanBalance}
            equity={equity}
            onRequestQuote={onRequestQuote}
          />
        )}
        {activeScenario === SCENARIOS.SELL && (
          <SellCalculator
            homeValue={homeValue}
            loanBalance={loanBalance}
            equity={equity}
            onRequestQuote={onRequestQuote}
          />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// REFINANCE CALCULATOR
// =============================================================================

function RefinanceCalculator({
  homeValue,
  loanBalance,
  currentRate,
  monthlyPayment,
  onRequestQuote,
}) {
  const [newRate, setNewRate] = useState(currentRate - 1);
  const [newTerm, setNewTerm] = useState(30);
  const [showDetails, setShowDetails] = useState(false);

  // Calculate new payment
  const calculations = useMemo(() => {
    const monthlyRate = newRate / 100 / 12;
    const numPayments = newTerm * 12;
    const newPayment = (loanBalance * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -numPayments));

    // Current loan remaining (assume 25 years left)
    const currentRemaining = 25 * 12;
    const currentTotalInterest = (monthlyPayment * currentRemaining) - loanBalance;

    // New loan total interest
    const newTotalPayments = newPayment * numPayments;
    const newTotalInterest = newTotalPayments - loanBalance;

    return {
      newPayment,
      monthlyChange: monthlyPayment - newPayment,
      yearlyChange: (monthlyPayment - newPayment) * 12,
      currentTotalInterest,
      newTotalInterest,
      interestSavings: currentTotalInterest - newTotalInterest,
      breakEvenMonths: Math.ceil(3000 / (monthlyPayment - newPayment)), // Assume $3k closing costs
    };
  }, [loanBalance, currentRate, newRate, newTerm, monthlyPayment]);

  return (
    <div className="calculator-panel refinance">
      <div className="calc-header">
        <div className="calc-icon">🔄</div>
        <div className="calc-title">
          <h3>Rate & Term Refinance</h3>
          <p>Lower your interest rate or change your loan term</p>
        </div>
      </div>

      <div className="calc-body">
        <div className="input-section">
          {/* New Rate Slider */}
          <div className="input-group">
            <label>
              <span>New Interest Rate</span>
              <span className="input-value">{newRate.toFixed(3)}%</span>
            </label>
            <input
              type="range"
              min={currentRate - 2}
              max={currentRate}
              step={0.125}
              value={newRate}
              onChange={(e) => setNewRate(parseFloat(e.target.value))}
            />
            <div className="range-labels">
              <span>{(currentRate - 2).toFixed(2)}%</span>
              <span>Current: {currentRate}%</span>
            </div>
          </div>

          {/* Term Selector */}
          <div className="input-group">
            <label>Loan Term</label>
            <div className="term-buttons">
              {[15, 20, 30].map((term) => (
                <button
                  key={term}
                  className={`term-btn ${newTerm === term ? 'active' : ''}`}
                  onClick={() => setNewTerm(term)}
                >
                  {term} Years
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="results-section">
          <div className="result-main">
            <div className="current-vs-new">
              <div className="payment-box current">
                <span className="payment-label">Current Payment</span>
                <span className="payment-amount">{formatCurrency(monthlyPayment)}/mo</span>
              </div>
              <div className="arrow">→</div>
              <div className="payment-box new">
                <span className="payment-label">New Payment</span>
                <span className="payment-amount">{formatCurrency(calculations.newPayment)}/mo</span>
              </div>
            </div>

            <div className="savings-highlight">
              <span className="savings-label">Monthly Savings</span>
              <span className={`savings-amount ${calculations.monthlyChange > 0 ? 'positive' : 'negative'}`}>
                {calculations.monthlyChange > 0 ? '+' : ''}{formatCurrency(calculations.monthlyChange)}
              </span>
            </div>
          </div>

          <button
            className="details-toggle"
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? 'Hide Details' : 'Show Details'} {showDetails ? '▲' : '▼'}
          </button>

          {showDetails && (
            <div className="result-details">
              <div className="detail-row">
                <span>Yearly Savings</span>
                <span className="positive">{formatCurrency(calculations.yearlyChange)}</span>
              </div>
              <div className="detail-row">
                <span>Interest Savings (over life of loan)</span>
                <span className="positive">{formatCurrency(calculations.interestSavings)}</span>
              </div>
              <div className="detail-row">
                <span>Break-Even Point</span>
                <span>{calculations.breakEvenMonths} months</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="calc-footer">
        <button
          className="cta-button primary"
          onClick={() => onRequestQuote?.({ type: 'refinance', newRate, newTerm })}
        >
          Get a Refinance Quote
        </button>
        <p className="disclaimer">
          Estimates are for illustrative purposes only. Actual rates and terms may vary.
        </p>
      </div>
    </div>
  );
}

// =============================================================================
// CASH-OUT CALCULATOR
// =============================================================================

function CashOutCalculator({
  homeValue,
  loanBalance,
  equity,
  currentRate,
  onRequestQuote,
}) {
  const [cashOutAmount, setCashOutAmount] = useState(50000);
  const [newRate, setNewRate] = useState(currentRate + 0.25);
  const newTerm = 30; // Fixed 30-year term for cash-out

  const calculations = useMemo(() => {
    const maxLtv = 0.80;
    const maxLoanAmount = homeValue * maxLtv;
    const maxCashOut = Math.max(0, maxLoanAmount - loanBalance);

    const newLoanAmount = loanBalance + cashOutAmount;
    const newLtv = (newLoanAmount / homeValue) * 100;

    const monthlyRate = newRate / 100 / 12;
    const numPayments = newTerm * 12;
    const newPayment = (newLoanAmount * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -numPayments));

    return {
      maxCashOut,
      newLoanAmount,
      newLtv,
      newPayment,
      effectiveCashOut: Math.min(cashOutAmount, maxCashOut),
    };
  }, [homeValue, loanBalance, cashOutAmount, newRate]);

  return (
    <div className="calculator-panel cash-out">
      <div className="calc-header">
        <div className="calc-icon">💰</div>
        <div className="calc-title">
          <h3>Cash-Out Refinance</h3>
          <p>Turn your home equity into cash</p>
        </div>
      </div>

      <div className="calc-body">
        <div className="equity-meter">
          <div className="meter-label">
            <span>Available Equity (80% LTV)</span>
            <span className="meter-value">{formatCurrency(calculations.maxCashOut)}</span>
          </div>
          <div className="meter-bar">
            <div
              className="meter-fill"
              style={{ width: `${Math.min((cashOutAmount / calculations.maxCashOut) * 100, 100)}%` }}
            />
          </div>
        </div>

        <div className="input-section">
          <div className="input-group">
            <label>
              <span>Cash-Out Amount</span>
              <span className="input-value">{formatCurrency(cashOutAmount)}</span>
            </label>
            <input
              type="range"
              min={10000}
              max={Math.max(calculations.maxCashOut, 10000)}
              step={5000}
              value={Math.min(cashOutAmount, calculations.maxCashOut)}
              onChange={(e) => setCashOutAmount(parseFloat(e.target.value))}
            />
            <div className="range-labels">
              <span>$10,000</span>
              <span>{formatCurrency(calculations.maxCashOut)}</span>
            </div>
          </div>

          <div className="input-group">
            <label>
              <span>Estimated Rate</span>
              <span className="input-value">{newRate.toFixed(3)}%</span>
            </label>
            <input
              type="range"
              min={currentRate}
              max={currentRate + 1.5}
              step={0.125}
              value={newRate}
              onChange={(e) => setNewRate(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <div className="results-section">
          <div className="result-cards">
            <div className="result-card">
              <span className="card-label">Cash to You</span>
              <span className="card-value highlight">{formatCurrency(calculations.effectiveCashOut)}</span>
            </div>
            <div className="result-card">
              <span className="card-label">New Loan Amount</span>
              <span className="card-value">{formatCurrency(calculations.newLoanAmount)}</span>
            </div>
            <div className="result-card">
              <span className="card-label">New Monthly Payment</span>
              <span className="card-value">{formatCurrency(calculations.newPayment)}</span>
            </div>
            <div className="result-card">
              <span className="card-label">New LTV</span>
              <span className="card-value">{calculations.newLtv.toFixed(1)}%</span>
            </div>
          </div>

          <div className="use-cases">
            <h4>Common Uses for Cash-Out</h4>
            <div className="use-case-grid">
              <div className="use-case">🏠 Home Improvements</div>
              <div className="use-case">💳 Debt Consolidation</div>
              <div className="use-case">🎓 Education Expenses</div>
              <div className="use-case">💼 Investment</div>
            </div>
          </div>
        </div>
      </div>

      <div className="calc-footer">
        <button
          className="cta-button primary"
          onClick={() => onRequestQuote?.({ type: 'cashOut', cashOutAmount, newRate })}
        >
          Explore Cash-Out Options
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// HELOC CALCULATOR
// =============================================================================

function HelocCalculator({
  homeValue,
  loanBalance,
  equity,
  onRequestQuote,
}) {
  const [drawAmount, setDrawAmount] = useState(0);
  const [helocRate, setHelocRate] = useState(8.5);

  const calculations = useMemo(() => {
    const maxCltv = 0.85;
    const maxCombinedLoan = homeValue * maxCltv;
    const maxHelocLine = Math.max(0, maxCombinedLoan - loanBalance);

    const monthlyInterest = (drawAmount * (helocRate / 100)) / 12;

    return {
      maxHelocLine,
      monthlyInterestOnly: monthlyInterest,
      annualInterest: monthlyInterest * 12,
    };
  }, [homeValue, loanBalance, drawAmount, helocRate]);

  return (
    <div className="calculator-panel heloc">
      <div className="calc-header">
        <div className="calc-icon">🏦</div>
        <div className="calc-title">
          <h3>Home Equity Line of Credit</h3>
          <p>Flexible access to your equity when you need it</p>
        </div>
      </div>

      <div className="calc-body">
        <div className="heloc-explainer">
          <div className="explainer-item">
            <span className="explainer-icon">✓</span>
            <span>Only pay interest on what you draw</span>
          </div>
          <div className="explainer-item">
            <span className="explainer-icon">✓</span>
            <span>Keep your existing mortgage</span>
          </div>
          <div className="explainer-item">
            <span className="explainer-icon">✓</span>
            <span>Draw and repay as needed</span>
          </div>
        </div>

        <div className="heloc-limit">
          <span className="limit-label">Estimated Credit Line</span>
          <span className="limit-amount">{formatCurrency(calculations.maxHelocLine)}</span>
        </div>

        <div className="input-section">
          <div className="input-group">
            <label>
              <span>Example Draw Amount</span>
              <span className="input-value">{formatCurrency(drawAmount)}</span>
            </label>
            <input
              type="range"
              min={0}
              max={calculations.maxHelocLine}
              step={5000}
              value={drawAmount}
              onChange={(e) => setDrawAmount(parseFloat(e.target.value))}
            />
          </div>

          <div className="input-group">
            <label>
              <span>Current HELOC Rates (Variable)</span>
              <span className="input-value">{helocRate.toFixed(2)}%</span>
            </label>
            <input
              type="range"
              min={7.0}
              max={12.0}
              step={0.25}
              value={helocRate}
              onChange={(e) => setHelocRate(parseFloat(e.target.value))}
            />
          </div>
        </div>

        {drawAmount > 0 && (
          <div className="results-section">
            <div className="heloc-payment">
              <span className="payment-label">Interest-Only Payment</span>
              <span className="payment-amount">{formatCurrency(calculations.monthlyInterestOnly)}/mo</span>
              <span className="payment-note">on a {formatCurrency(drawAmount)} draw</span>
            </div>
          </div>
        )}

        <div className="heloc-comparison">
          <h4>HELOC vs Cash-Out Refinance</h4>
          <table className="comparison-table">
            <thead>
              <tr>
                <th></th>
                <th>HELOC</th>
                <th>Cash-Out Refi</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Closing Costs</td>
                <td className="good">Low/None</td>
                <td>2-5%</td>
              </tr>
              <tr>
                <td>Interest Rate</td>
                <td>Variable</td>
                <td className="good">Fixed</td>
              </tr>
              <tr>
                <td>First Mortgage</td>
                <td className="good">Unchanged</td>
                <td>Replaced</td>
              </tr>
              <tr>
                <td>Flexibility</td>
                <td className="good">Draw as needed</td>
                <td>Lump sum</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="calc-footer">
        <button
          className="cta-button primary"
          onClick={() => onRequestQuote?.({ type: 'heloc', creditLine: calculations.maxHelocLine })}
        >
          Learn About HELOC Options
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// SELL CALCULATOR
// =============================================================================

function SellCalculator({
  homeValue,
  loanBalance,
  equity,
  onRequestQuote,
}) {
  const [salePrice, setSalePrice] = useState(homeValue);
  const [agentCommission, setAgentCommission] = useState(5.5);
  const [repairCredits, setRepairCredits] = useState(0);

  const calculations = useMemo(() => {
    const commission = (salePrice * agentCommission) / 100;
    const closingCosts = salePrice * 0.015; // ~1.5% seller closing costs
    const totalCosts = commission + closingCosts + repairCredits;
    const netProceeds = salePrice - loanBalance - totalCosts;

    return {
      commission,
      closingCosts,
      totalCosts,
      netProceeds,
    };
  }, [salePrice, loanBalance, agentCommission, repairCredits]);

  return (
    <div className="calculator-panel sell">
      <div className="calc-header">
        <div className="calc-icon">🏠</div>
        <div className="calc-title">
          <h3>Sell Analysis</h3>
          <p>Estimate your net proceeds if you sell</p>
        </div>
      </div>

      <div className="calc-body">
        <div className="input-section">
          <div className="input-group">
            <label>
              <span>Expected Sale Price</span>
              <span className="input-value">{formatCurrency(salePrice)}</span>
            </label>
            <input
              type="range"
              min={homeValue * 0.9}
              max={homeValue * 1.1}
              step={5000}
              value={salePrice}
              onChange={(e) => setSalePrice(parseFloat(e.target.value))}
            />
            <div className="range-labels">
              <span>{formatCurrency(homeValue * 0.9)}</span>
              <span>{formatCurrency(homeValue * 1.1)}</span>
            </div>
          </div>

          <div className="input-group">
            <label>
              <span>Agent Commission</span>
              <span className="input-value">{agentCommission}%</span>
            </label>
            <input
              type="range"
              min={4}
              max={6}
              step={0.5}
              value={agentCommission}
              onChange={(e) => setAgentCommission(parseFloat(e.target.value))}
            />
          </div>

          <div className="input-group">
            <label>
              <span>Repair Credits / Concessions</span>
              <span className="input-value">{formatCurrency(repairCredits)}</span>
            </label>
            <input
              type="range"
              min={0}
              max={20000}
              step={1000}
              value={repairCredits}
              onChange={(e) => setRepairCredits(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <div className="results-section">
          <div className="proceeds-breakdown">
            <div className="breakdown-row">
              <span>Sale Price</span>
              <span>{formatCurrency(salePrice)}</span>
            </div>
            <div className="breakdown-row subtract">
              <span>Loan Payoff</span>
              <span>- {formatCurrency(loanBalance)}</span>
            </div>
            <div className="breakdown-row subtract">
              <span>Commission ({agentCommission}%)</span>
              <span>- {formatCurrency(calculations.commission)}</span>
            </div>
            <div className="breakdown-row subtract">
              <span>Closing Costs (~1.5%)</span>
              <span>- {formatCurrency(calculations.closingCosts)}</span>
            </div>
            {repairCredits > 0 && (
              <div className="breakdown-row subtract">
                <span>Repair Credits</span>
                <span>- {formatCurrency(repairCredits)}</span>
              </div>
            )}
            <div className="breakdown-row total">
              <span>Estimated Net Proceeds</span>
              <span className={calculations.netProceeds >= 0 ? 'positive' : 'negative'}>
                {formatCurrency(calculations.netProceeds)}
              </span>
            </div>
          </div>

          <div className="proceeds-visual">
            <div className="visual-bar">
              <div
                className="visual-fill equity"
                style={{ width: `${Math.max(0, (calculations.netProceeds / salePrice) * 100)}%` }}
              />
              <div
                className="visual-fill costs"
                style={{ width: `${(calculations.totalCosts / salePrice) * 100}%` }}
              />
              <div
                className="visual-fill loan"
                style={{ width: `${(loanBalance / salePrice) * 100}%` }}
              />
            </div>
            <div className="visual-legend">
              <div className="legend-item">
                <span className="legend-dot equity" />
                <span>Your Proceeds</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot costs" />
                <span>Selling Costs</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot loan" />
                <span>Loan Payoff</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="calc-footer">
        <button
          className="cta-button primary"
          onClick={() => onRequestQuote?.({ type: 'sell', salePrice })}
        >
          Get a Home Valuation
        </button>
        <p className="disclaimer">
          These are estimates only. Actual proceeds may vary based on market conditions and final sale terms.
        </p>
      </div>
    </div>
  );
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function formatCurrency(amount) {
  if (amount === null || amount === undefined) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

// Export component
export { PresentationEngine };
