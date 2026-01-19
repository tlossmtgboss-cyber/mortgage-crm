/**
 * TotalCostAnalysis Component
 *
 * Comprehensive mortgage cost analysis inspired by Mortgage Coach.
 * Features:
 * - Side-by-side loan scenario comparisons
 * - Payment breakdown with table/chart views
 * - Closing costs analysis
 * - Breakeven analysis
 * - Net worth calculator
 * - Savings over time (short-term & long-term)
 */

import React, { useState, useMemo } from 'react';
import './TotalCostAnalysis.css';

// =============================================================================
// CONSTANTS
// =============================================================================

const VIEWS = {
  OVERVIEW: 'overview',
  COMPARISON: 'comparison',
  PAYMENT_BREAKDOWN: 'paymentBreakdown',
  CLOSING_COSTS: 'closingCosts',
  BREAKEVEN: 'breakeven',
  NET_WORTH: 'netWorth',
  SAVINGS: 'savings',
};

const TIME_FRAMES = {
  SHORT: 180, // 15 years
  LONG: 360,  // 30 years
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function TotalCostAnalysis({
  // Current loan details
  currentLoanBalance = 400000,
  currentRate = 6.5,
  currentMonthlyPayment = 2528,
  currentRemainingMonths = 348,

  // Property details
  homeValue = 550000,

  // Proposed scenario (from AI/user goals)
  proposedScenarios = [],

  // Client info
  clientName = 'Valued Client',

  // Callbacks
  onRequestQuote,
  onScheduleCall,
}) {
  const [activeView, setActiveView] = useState(VIEWS.OVERVIEW);
  const [selectedScenario, setSelectedScenario] = useState(0);
  const [timeFrame, setTimeFrame] = useState(TIME_FRAMES.LONG);
  const [showModal, setShowModal] = useState(null);

  // Default scenarios if none provided
  const scenarios = useMemo(() => {
    if (proposedScenarios.length > 0) return proposedScenarios;

    return [
      {
        id: 'current',
        name: 'Current Loan',
        type: 'current',
        loanAmount: currentLoanBalance,
        rate: currentRate,
        term: Math.ceil(currentRemainingMonths / 12),
        monthlyPayment: currentMonthlyPayment,
        closingCosts: 0,
        cashOut: 0,
      },
      {
        id: 'refinance',
        name: 'Rate & Term Refinance',
        type: 'refinance',
        loanAmount: currentLoanBalance,
        rate: 5.875,
        term: 30,
        monthlyPayment: 2367,
        closingCosts: 8500,
        cashOut: 0,
      },
      {
        id: 'cashout',
        name: 'Cash-Out Refinance',
        type: 'cashout',
        loanAmount: currentLoanBalance + 50000,
        rate: 6.125,
        term: 30,
        monthlyPayment: 2734,
        closingCosts: 9200,
        cashOut: 50000,
      },
    ];
  }, [proposedScenarios, currentLoanBalance, currentRate, currentRemainingMonths, currentMonthlyPayment]);

  // Calculate detailed metrics for each scenario
  const scenarioMetrics = useMemo(() => {
    return scenarios.map(scenario => {
      const monthlyRate = scenario.rate / 100 / 12;
      const numPayments = scenario.term * 12;

      // Calculate total interest
      const totalPayments = scenario.monthlyPayment * numPayments;
      const totalInterest = totalPayments - scenario.loanAmount;

      // Calculate breakeven (months to recoup closing costs from savings)
      const currentScenario = scenarios.find(s => s.type === 'current') || scenarios[0];
      const monthlySavings = currentScenario.monthlyPayment - scenario.monthlyPayment;
      const breakevenMonths = monthlySavings > 0 ? Math.ceil(scenario.closingCosts / monthlySavings) : null;

      // Calculate net worth impact over time
      const netWorthAtTimeFrame = calculateNetWorth(scenario, timeFrame, homeValue);

      return {
        ...scenario,
        totalPayments,
        totalInterest,
        monthlySavings,
        breakevenMonths,
        netWorthAtTimeFrame,
        monthlyPrincipal: scenario.monthlyPayment - (scenario.loanAmount * monthlyRate),
        monthlyInterest: scenario.loanAmount * monthlyRate,
      };
    });
  }, [scenarios, timeFrame, homeValue]);

  // Navigation menu items
  const menuItems = [
    { id: VIEWS.OVERVIEW, label: 'Report Overview', icon: '📊' },
    { id: VIEWS.COMPARISON, label: 'Loan Comparison', icon: '⚖️' },
    { id: VIEWS.PAYMENT_BREAKDOWN, label: 'Payment Breakdown', icon: '💳' },
    { id: VIEWS.CLOSING_COSTS, label: 'Closing Costs', icon: '📋' },
    { id: VIEWS.BREAKEVEN, label: 'Breakeven Analysis', icon: '⏱️' },
    { id: VIEWS.NET_WORTH, label: 'Net Worth Impact', icon: '📈' },
    { id: VIEWS.SAVINGS, label: 'Savings Over Time', icon: '💰' },
  ];

  return (
    <div className="tca-container">
      {/* Header */}
      <header className="tca-header">
        <div className="tca-branding">
          <div className="tca-logo">
            <span className="logo-icon">🏠</span>
            <span className="logo-text">Total Cost Analysis</span>
          </div>
          <p className="tca-tagline">Your personalized mortgage comparison</p>
        </div>
        <div className="tca-client-info">
          <span className="client-label">Prepared for:</span>
          <span className="client-name">{clientName}</span>
        </div>
      </header>

      {/* Disclaimer */}
      <div className="tca-disclaimer">
        <span className="disclaimer-icon">ℹ️</span>
        <p>Your actual rate, payment, and costs could vary. Get an official Loan Estimate before choosing a loan.</p>
      </div>

      {/* Main Content */}
      <div className="tca-main">
        {/* Side Navigation */}
        <nav className="tca-nav">
          <ul className="nav-menu">
            {menuItems.map(item => (
              <li key={item.id}>
                <button
                  className={`nav-item ${activeView === item.id ? 'active' : ''}`}
                  onClick={() => setActiveView(item.id)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                </button>
              </li>
            ))}
          </ul>

          {/* Time Frame Toggle */}
          <div className="timeframe-toggle">
            <span className="toggle-label">Analysis Period:</span>
            <div className="toggle-buttons">
              <button
                className={timeFrame === TIME_FRAMES.SHORT ? 'active' : ''}
                onClick={() => setTimeFrame(TIME_FRAMES.SHORT)}
              >
                15 Years
              </button>
              <button
                className={timeFrame === TIME_FRAMES.LONG ? 'active' : ''}
                onClick={() => setTimeFrame(TIME_FRAMES.LONG)}
              >
                30 Years
              </button>
            </div>
          </div>

          {/* CTA Buttons */}
          <div className="nav-cta">
            <button className="cta-primary" onClick={() => onScheduleCall?.()}>
              📞 Schedule a Call
            </button>
            <button className="cta-secondary" onClick={() => onRequestQuote?.()}>
              📝 Get Quote
            </button>
          </div>
        </nav>

        {/* Content Area */}
        <main className="tca-content">
          {activeView === VIEWS.OVERVIEW && (
            <OverviewSection
              scenarios={scenarioMetrics}
              selectedScenario={selectedScenario}
              onSelectScenario={setSelectedScenario}
              timeFrame={timeFrame}
              onViewDetails={setShowModal}
            />
          )}

          {activeView === VIEWS.COMPARISON && (
            <ComparisonSection
              scenarios={scenarioMetrics}
              timeFrame={timeFrame}
            />
          )}

          {activeView === VIEWS.PAYMENT_BREAKDOWN && (
            <PaymentBreakdownSection
              scenarios={scenarioMetrics}
              selectedScenario={selectedScenario}
              onSelectScenario={setSelectedScenario}
            />
          )}

          {activeView === VIEWS.CLOSING_COSTS && (
            <ClosingCostsSection
              scenarios={scenarioMetrics}
              selectedScenario={selectedScenario}
              onSelectScenario={setSelectedScenario}
            />
          )}

          {activeView === VIEWS.BREAKEVEN && (
            <BreakevenSection
              scenarios={scenarioMetrics}
              currentScenario={scenarioMetrics[0]}
            />
          )}

          {activeView === VIEWS.NET_WORTH && (
            <NetWorthSection
              scenarios={scenarioMetrics}
              timeFrame={timeFrame}
              homeValue={homeValue}
            />
          )}

          {activeView === VIEWS.SAVINGS && (
            <SavingsSection
              scenarios={scenarioMetrics}
              timeFrame={timeFrame}
            />
          )}
        </main>
      </div>

      {/* Modal for detailed views */}
      {showModal && (
        <DetailModal
          type={showModal.type}
          scenario={showModal.scenario}
          onClose={() => setShowModal(null)}
        />
      )}
    </div>
  );
}

// =============================================================================
// OVERVIEW SECTION
// =============================================================================

function OverviewSection({ scenarios, selectedScenario, onSelectScenario, timeFrame, onViewDetails }) {
  const currentScenario = scenarios[0];
  const bestSavingsScenario = scenarios.reduce((best, s) =>
    s.monthlySavings > (best?.monthlySavings || 0) ? s : best, null);

  return (
    <div className="tca-section overview">
      <h2>Report Overview</h2>
      <p className="section-intro">
        Compare your current mortgage with alternative options to find the best fit for your financial goals.
      </p>

      {/* Quick Stats */}
      <div className="quick-stats">
        <div className="stat-card highlight">
          <span className="stat-icon">💵</span>
          <div className="stat-content">
            <span className="stat-value">
              {formatCurrency(bestSavingsScenario?.monthlySavings || 0)}
            </span>
            <span className="stat-label">Potential Monthly Savings</span>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📅</span>
          <div className="stat-content">
            <span className="stat-value">
              {bestSavingsScenario?.breakevenMonths
                ? `${Math.floor(bestSavingsScenario.breakevenMonths / 12)}y ${bestSavingsScenario.breakevenMonths % 12}m`
                : 'N/A'}
            </span>
            <span className="stat-label">Breakeven Point</span>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📈</span>
          <div className="stat-content">
            <span className="stat-value">
              {formatCurrency(bestSavingsScenario?.netWorthAtTimeFrame || 0)}
            </span>
            <span className="stat-label">Net Worth at {timeFrame / 12} Years</span>
          </div>
        </div>
      </div>

      {/* Scenario Cards */}
      <h3>Your Options</h3>
      <div className="scenario-cards">
        {scenarios.map((scenario, index) => (
          <div
            key={scenario.id}
            className={`scenario-card ${selectedScenario === index ? 'selected' : ''} ${scenario.type}`}
            onClick={() => onSelectScenario(index)}
          >
            <div className="card-header">
              <h4>{scenario.name}</h4>
              {scenario.type !== 'current' && scenario.monthlySavings > 0 && (
                <span className="savings-badge">
                  Save {formatCurrency(scenario.monthlySavings)}/mo
                </span>
              )}
            </div>

            <div className="card-details">
              <div className="detail-row">
                <span>Loan Amount</span>
                <span>{formatCurrency(scenario.loanAmount)}</span>
              </div>
              <div className="detail-row">
                <span>Interest Rate</span>
                <span>{scenario.rate}%</span>
              </div>
              <div className="detail-row">
                <span>Term</span>
                <span>{scenario.term} years</span>
              </div>
              <div className="detail-row highlight">
                <span>Monthly Payment</span>
                <span>{formatCurrency(scenario.monthlyPayment)}</span>
              </div>
              {scenario.closingCosts > 0 && (
                <div className="detail-row">
                  <span>Closing Costs</span>
                  <span>{formatCurrency(scenario.closingCosts)}</span>
                </div>
              )}
              {scenario.cashOut > 0 && (
                <div className="detail-row cashout">
                  <span>Cash to You</span>
                  <span>{formatCurrency(scenario.cashOut)}</span>
                </div>
              )}
            </div>

            <div className="card-actions">
              <button
                className="action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewDetails({ type: 'payment', scenario });
                }}
              >
                Payment Details
              </button>
              <button
                className="action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewDetails({ type: 'closing', scenario });
                }}
              >
                Closing Costs
              </button>
              <button
                className="action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewDetails({ type: 'strategy', scenario });
                }}
              >
                Strategy
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// COMPARISON SECTION
// =============================================================================

function ComparisonSection({ scenarios, timeFrame }) {
  return (
    <div className="tca-section comparison">
      <h2>Side-by-Side Comparison</h2>
      <p className="section-intro">
        Compare all loan options at a glance to make an informed decision.
      </p>

      <div className="comparison-table-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Feature</th>
              {scenarios.map(s => (
                <th key={s.id} className={s.type}>
                  {s.name}
                  {s.type !== 'current' && s.monthlySavings > 0 && (
                    <span className="best-badge">Best Value</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Loan Amount</td>
              {scenarios.map(s => <td key={s.id}>{formatCurrency(s.loanAmount)}</td>)}
            </tr>
            <tr>
              <td>Interest Rate</td>
              {scenarios.map(s => <td key={s.id}>{s.rate}%</td>)}
            </tr>
            <tr>
              <td>Loan Term</td>
              {scenarios.map(s => <td key={s.id}>{s.term} years</td>)}
            </tr>
            <tr className="highlight-row">
              <td>Monthly Payment</td>
              {scenarios.map(s => <td key={s.id}>{formatCurrency(s.monthlyPayment)}</td>)}
            </tr>
            <tr>
              <td>Monthly Savings</td>
              {scenarios.map(s => (
                <td key={s.id} className={s.monthlySavings > 0 ? 'positive' : ''}>
                  {s.monthlySavings > 0 ? `+${formatCurrency(s.monthlySavings)}` : '-'}
                </td>
              ))}
            </tr>
            <tr>
              <td>Total Interest ({timeFrame / 12} yrs)</td>
              {scenarios.map(s => <td key={s.id}>{formatCurrency(s.totalInterest)}</td>)}
            </tr>
            <tr>
              <td>Closing Costs</td>
              {scenarios.map(s => <td key={s.id}>{formatCurrency(s.closingCosts)}</td>)}
            </tr>
            <tr>
              <td>Cash Out</td>
              {scenarios.map(s => (
                <td key={s.id} className={s.cashOut > 0 ? 'cashout' : ''}>
                  {s.cashOut > 0 ? formatCurrency(s.cashOut) : '-'}
                </td>
              ))}
            </tr>
            <tr>
              <td>Breakeven</td>
              {scenarios.map(s => (
                <td key={s.id}>
                  {s.breakevenMonths
                    ? `${Math.floor(s.breakevenMonths / 12)}y ${s.breakevenMonths % 12}m`
                    : '-'}
                </td>
              ))}
            </tr>
            <tr className="highlight-row">
              <td>Net Worth at {timeFrame / 12} Years</td>
              {scenarios.map(s => (
                <td key={s.id}>{formatCurrency(s.netWorthAtTimeFrame)}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =============================================================================
// PAYMENT BREAKDOWN SECTION
// =============================================================================

function PaymentBreakdownSection({ scenarios, selectedScenario, onSelectScenario }) {
  const scenario = scenarios[selectedScenario];
  const [viewType, setViewType] = useState('table'); // 'table' or 'chart'

  // Generate amortization schedule (first 12 months for display)
  const amortizationPreview = useMemo(() => {
    const schedule = [];
    let balance = scenario.loanAmount;
    const monthlyRate = scenario.rate / 100 / 12;

    for (let month = 1; month <= 12; month++) {
      const interest = balance * monthlyRate;
      const principal = scenario.monthlyPayment - interest;
      balance -= principal;

      schedule.push({
        month,
        payment: scenario.monthlyPayment,
        principal,
        interest,
        balance: Math.max(0, balance),
      });
    }

    return schedule;
  }, [scenario]);

  return (
    <div className="tca-section payment-breakdown">
      <h2>Payment Breakdown</h2>

      {/* Scenario Selector */}
      <div className="scenario-selector">
        {scenarios.map((s, index) => (
          <button
            key={s.id}
            className={`selector-btn ${selectedScenario === index ? 'active' : ''}`}
            onClick={() => onSelectScenario(index)}
          >
            {s.name}
          </button>
        ))}
      </div>

      {/* View Toggle */}
      <div className="view-toggle">
        <button
          className={viewType === 'table' ? 'active' : ''}
          onClick={() => setViewType('table')}
        >
          📋 Table View
        </button>
        <button
          className={viewType === 'chart' ? 'active' : ''}
          onClick={() => setViewType('chart')}
        >
          📊 Chart View
        </button>
      </div>

      {/* Payment Summary */}
      <div className="payment-summary">
        <div className="summary-card">
          <h4>Monthly Payment</h4>
          <span className="big-number">{formatCurrency(scenario.monthlyPayment)}</span>
        </div>
        <div className="summary-breakdown">
          <div className="breakdown-item principal">
            <span className="item-label">Principal</span>
            <span className="item-value">{formatCurrency(scenario.monthlyPrincipal)}</span>
            <div className="item-bar" style={{ width: `${(scenario.monthlyPrincipal / scenario.monthlyPayment) * 100}%` }} />
          </div>
          <div className="breakdown-item interest">
            <span className="item-label">Interest</span>
            <span className="item-value">{formatCurrency(scenario.monthlyInterest)}</span>
            <div className="item-bar" style={{ width: `${(scenario.monthlyInterest / scenario.monthlyPayment) * 100}%` }} />
          </div>
        </div>
      </div>

      {viewType === 'table' ? (
        <div className="amortization-table">
          <h3>First Year Amortization</h3>
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Payment</th>
                <th>Principal</th>
                <th>Interest</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {amortizationPreview.map(row => (
                <tr key={row.month}>
                  <td>{row.month}</td>
                  <td>{formatCurrency(row.payment)}</td>
                  <td>{formatCurrency(row.principal)}</td>
                  <td>{formatCurrency(row.interest)}</td>
                  <td>{formatCurrency(row.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="payment-chart">
          <h3>Principal vs Interest Over Time</h3>
          <div className="chart-container">
            {amortizationPreview.map((row, index) => (
              <div key={row.month} className="chart-bar-group">
                <div className="chart-bars">
                  <div
                    className="bar principal"
                    style={{ height: `${(row.principal / scenario.monthlyPayment) * 150}px` }}
                    title={`Principal: ${formatCurrency(row.principal)}`}
                  />
                  <div
                    className="bar interest"
                    style={{ height: `${(row.interest / scenario.monthlyPayment) * 150}px` }}
                    title={`Interest: ${formatCurrency(row.interest)}`}
                  />
                </div>
                <span className="chart-label">M{row.month}</span>
              </div>
            ))}
          </div>
          <div className="chart-legend">
            <span className="legend-item principal">● Principal</span>
            <span className="legend-item interest">● Interest</span>
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// CLOSING COSTS SECTION
// =============================================================================

function ClosingCostsSection({ scenarios, selectedScenario, onSelectScenario }) {
  const scenario = scenarios[selectedScenario];
  const [viewType, setViewType] = useState('table');

  // Sample closing costs breakdown
  const closingCostsBreakdown = useMemo(() => {
    const total = scenario.closingCosts;
    if (total === 0) return [];

    return [
      { category: 'Origination Fee', amount: total * 0.25, description: 'Lender processing fee' },
      { category: 'Appraisal', amount: 550, description: 'Property valuation' },
      { category: 'Title Insurance', amount: total * 0.15, description: 'Protects against title issues' },
      { category: 'Title Search', amount: 400, description: 'Title history research' },
      { category: 'Recording Fees', amount: 250, description: 'County recording charges' },
      { category: 'Credit Report', amount: 75, description: 'Credit check fee' },
      { category: 'Flood Certification', amount: 25, description: 'Flood zone check' },
      { category: 'Prepaid Interest', amount: total * 0.20, description: 'Interest to first payment' },
      { category: 'Escrow Setup', amount: total * 0.15, description: 'Tax & insurance reserves' },
    ];
  }, [scenario]);

  return (
    <div className="tca-section closing-costs">
      <h2>Closing Costs Analysis</h2>

      {/* Scenario Selector */}
      <div className="scenario-selector">
        {scenarios.map((s, index) => (
          <button
            key={s.id}
            className={`selector-btn ${selectedScenario === index ? 'active' : ''}`}
            onClick={() => onSelectScenario(index)}
          >
            {s.name}
          </button>
        ))}
      </div>

      {scenario.closingCosts === 0 ? (
        <div className="no-costs-message">
          <span className="icon">✓</span>
          <p>No closing costs for your current loan.</p>
        </div>
      ) : (
        <>
          {/* View Toggle */}
          <div className="view-toggle">
            <button
              className={viewType === 'table' ? 'active' : ''}
              onClick={() => setViewType('table')}
            >
              📋 Table View
            </button>
            <button
              className={viewType === 'chart' ? 'active' : ''}
              onClick={() => setViewType('chart')}
            >
              📊 Chart View
            </button>
          </div>

          {/* Total */}
          <div className="costs-total">
            <h3>Total Closing Costs</h3>
            <span className="total-amount">{formatCurrency(scenario.closingCosts)}</span>
          </div>

          {viewType === 'table' ? (
            <table className="costs-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Description</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {closingCostsBreakdown.map((item, index) => (
                  <tr key={index}>
                    <td>{item.category}</td>
                    <td className="description">{item.description}</td>
                    <td>{formatCurrency(item.amount)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan="2">Total</td>
                  <td>{formatCurrency(scenario.closingCosts)}</td>
                </tr>
              </tfoot>
            </table>
          ) : (
            <div className="costs-chart">
              <div className="pie-chart-container">
                {closingCostsBreakdown.map((item, index) => {
                  const percentage = (item.amount / scenario.closingCosts) * 100;
                  return (
                    <div key={index} className="pie-segment">
                      <div
                        className="segment-bar"
                        style={{
                          width: `${percentage}%`,
                          backgroundColor: `hsl(${index * 40}, 60%, 50%)`
                        }}
                      />
                      <div className="segment-info">
                        <span className="segment-label">{item.category}</span>
                        <span className="segment-value">{formatCurrency(item.amount)} ({percentage.toFixed(1)}%)</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// =============================================================================
// BREAKEVEN SECTION
// =============================================================================

function BreakevenSection({ scenarios, currentScenario }) {
  return (
    <div className="tca-section breakeven">
      <h2>Breakeven Analysis</h2>
      <p className="section-intro">
        See how long it takes to recoup your closing costs through monthly savings.
      </p>

      <div className="breakeven-cards">
        {scenarios.filter(s => s.type !== 'current').map(scenario => {
          const monthlySavings = currentScenario.monthlyPayment - scenario.monthlyPayment;
          const breakevenMonths = monthlySavings > 0
            ? Math.ceil(scenario.closingCosts / monthlySavings)
            : null;

          return (
            <div key={scenario.id} className="breakeven-card">
              <h3>{scenario.name}</h3>

              <div className="breakeven-visual">
                {breakevenMonths ? (
                  <>
                    <div className="timeline">
                      <div className="timeline-line">
                        <div
                          className="timeline-progress"
                          style={{ width: `${Math.min((breakevenMonths / 60) * 100, 100)}%` }}
                        />
                        <div
                          className="timeline-marker"
                          style={{ left: `${Math.min((breakevenMonths / 60) * 100, 100)}%` }}
                        >
                          <span className="marker-label">Breakeven</span>
                        </div>
                      </div>
                      <div className="timeline-labels">
                        <span>Today</span>
                        <span>5 Years</span>
                      </div>
                    </div>

                    <div className="breakeven-stats">
                      <div className="stat">
                        <span className="stat-value">
                          {Math.floor(breakevenMonths / 12)} years, {breakevenMonths % 12} months
                        </span>
                        <span className="stat-label">Time to Breakeven</span>
                      </div>
                      <div className="stat">
                        <span className="stat-value">{formatCurrency(monthlySavings)}</span>
                        <span className="stat-label">Monthly Savings</span>
                      </div>
                      <div className="stat">
                        <span className="stat-value">{formatCurrency(scenario.closingCosts)}</span>
                        <span className="stat-label">Closing Costs</span>
                      </div>
                    </div>

                    <div className="savings-projection">
                      <h4>Savings Projection</h4>
                      <div className="projection-grid">
                        <div className="projection-item">
                          <span className="period">1 Year</span>
                          <span className="amount">{formatCurrency(monthlySavings * 12 - scenario.closingCosts)}</span>
                        </div>
                        <div className="projection-item">
                          <span className="period">3 Years</span>
                          <span className="amount">{formatCurrency(monthlySavings * 36 - scenario.closingCosts)}</span>
                        </div>
                        <div className="projection-item">
                          <span className="period">5 Years</span>
                          <span className="amount">{formatCurrency(monthlySavings * 60 - scenario.closingCosts)}</span>
                        </div>
                        <div className="projection-item">
                          <span className="period">10 Years</span>
                          <span className="amount">{formatCurrency(monthlySavings * 120 - scenario.closingCosts)}</span>
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="no-savings-message">
                    <span className="icon">ℹ️</span>
                    <p>This option does not provide monthly savings compared to your current loan.</p>
                    {scenario.cashOut > 0 && (
                      <p className="cashout-note">
                        However, you receive <strong>{formatCurrency(scenario.cashOut)}</strong> in cash.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// =============================================================================
// NET WORTH SECTION
// =============================================================================

function NetWorthSection({ scenarios, timeFrame, homeValue }) {
  // Calculate net worth at different time points
  const netWorthData = useMemo(() => {
    const years = [1, 3, 5, 10, 15, 20, 25, 30].filter(y => y * 12 <= timeFrame);

    return years.map(year => {
      const months = year * 12;
      return {
        year,
        values: scenarios.map(scenario => ({
          id: scenario.id,
          name: scenario.name,
          netWorth: calculateNetWorth(scenario, months, homeValue),
        })),
      };
    });
  }, [scenarios, timeFrame, homeValue]);

  return (
    <div className="tca-section net-worth">
      <h2>Net Worth Impact</h2>
      <p className="section-intro">
        See how each loan option affects your wealth accumulation over time.
      </p>

      {/* Net Worth Chart */}
      <div className="net-worth-chart">
        <div className="chart-header">
          <h3>Projected Net Worth Over Time</h3>
        </div>

        <div className="chart-visualization">
          {netWorthData.map((point, index) => (
            <div key={point.year} className="chart-column">
              <div className="column-bars">
                {point.values.map((val, vIndex) => (
                  <div
                    key={val.id}
                    className={`column-bar scenario-${vIndex}`}
                    style={{
                      height: `${Math.min((val.netWorth / 500000) * 200, 250)}px`,
                    }}
                    title={`${val.name}: ${formatCurrency(val.netWorth)}`}
                  >
                    <span className="bar-value">{formatCurrency(val.netWorth)}</span>
                  </div>
                ))}
              </div>
              <span className="column-label">Year {point.year}</span>
            </div>
          ))}
        </div>

        <div className="chart-legend">
          {scenarios.map((s, index) => (
            <span key={s.id} className={`legend-item scenario-${index}`}>
              ● {s.name}
            </span>
          ))}
        </div>
      </div>

      {/* Net Worth Table */}
      <div className="net-worth-table">
        <h3>Net Worth Comparison</h3>
        <table>
          <thead>
            <tr>
              <th>Year</th>
              {scenarios.map(s => <th key={s.id}>{s.name}</th>)}
              <th>Best Option</th>
            </tr>
          </thead>
          <tbody>
            {netWorthData.map(point => {
              const best = point.values.reduce((a, b) => a.netWorth > b.netWorth ? a : b);
              return (
                <tr key={point.year}>
                  <td>Year {point.year}</td>
                  {point.values.map(val => (
                    <td
                      key={val.id}
                      className={val.id === best.id ? 'best' : ''}
                    >
                      {formatCurrency(val.netWorth)}
                    </td>
                  ))}
                  <td className="best-column">{best.name}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =============================================================================
// SAVINGS SECTION
// =============================================================================

function SavingsSection({ scenarios, timeFrame }) {
  const currentScenario = scenarios[0];

  return (
    <div className="tca-section savings">
      <h2>Savings Over Time</h2>
      <p className="section-intro">
        Compare total savings for each loan option over short-term and long-term periods.
      </p>

      <div className="savings-grid">
        {scenarios.filter(s => s.type !== 'current').map(scenario => {
          const monthlySavings = currentScenario.monthlyPayment - scenario.monthlyPayment;
          const shortTermSavings = (monthlySavings * TIME_FRAMES.SHORT) - scenario.closingCosts;
          const longTermSavings = (monthlySavings * TIME_FRAMES.LONG) - scenario.closingCosts;

          return (
            <div key={scenario.id} className="savings-card">
              <h3>{scenario.name}</h3>

              <div className="savings-comparison">
                <div className="savings-period short">
                  <span className="period-label">Short-Term (15 Years)</span>
                  <span className={`period-value ${shortTermSavings > 0 ? 'positive' : 'negative'}`}>
                    {shortTermSavings > 0 ? '+' : ''}{formatCurrency(shortTermSavings)}
                  </span>
                  <span className="period-detail">
                    Monthly: {formatCurrency(monthlySavings)} × 180 months
                  </span>
                </div>

                <div className="savings-period long">
                  <span className="period-label">Long-Term (30 Years)</span>
                  <span className={`period-value ${longTermSavings > 0 ? 'positive' : 'negative'}`}>
                    {longTermSavings > 0 ? '+' : ''}{formatCurrency(longTermSavings)}
                  </span>
                  <span className="period-detail">
                    Monthly: {formatCurrency(monthlySavings)} × 360 months
                  </span>
                </div>
              </div>

              <div className="savings-breakdown">
                <h4>Savings Breakdown</h4>
                <div className="breakdown-row">
                  <span>Total Monthly Savings</span>
                  <span>{formatCurrency(monthlySavings * timeFrame)}</span>
                </div>
                <div className="breakdown-row negative">
                  <span>Less: Closing Costs</span>
                  <span>-{formatCurrency(scenario.closingCosts)}</span>
                </div>
                <div className="breakdown-row total">
                  <span>Net Savings</span>
                  <span>{formatCurrency((monthlySavings * timeFrame) - scenario.closingCosts)}</span>
                </div>
              </div>

              {scenario.cashOut > 0 && (
                <div className="cashout-note">
                  <span className="icon">💵</span>
                  <p>Plus {formatCurrency(scenario.cashOut)} cash at closing</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// =============================================================================
// DETAIL MODAL
// =============================================================================

function DetailModal({ type, scenario, onClose }) {
  return (
    <div className="tca-modal-overlay" onClick={onClose}>
      <div className="tca-modal" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>

        <h2>{scenario.name}</h2>

        {type === 'payment' && (
          <div className="modal-content payment-details">
            <h3>Payment Breakdown</h3>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="label">Monthly Payment</span>
                <span className="value">{formatCurrency(scenario.monthlyPayment)}</span>
              </div>
              <div className="detail-item">
                <span className="label">Principal</span>
                <span className="value">{formatCurrency(scenario.monthlyPrincipal)}</span>
              </div>
              <div className="detail-item">
                <span className="label">Interest</span>
                <span className="value">{formatCurrency(scenario.monthlyInterest)}</span>
              </div>
              <div className="detail-item">
                <span className="label">Total Over Loan Term</span>
                <span className="value">{formatCurrency(scenario.totalPayments)}</span>
              </div>
              <div className="detail-item">
                <span className="label">Total Interest Paid</span>
                <span className="value">{formatCurrency(scenario.totalInterest)}</span>
              </div>
            </div>
          </div>
        )}

        {type === 'closing' && (
          <div className="modal-content closing-details">
            <h3>Closing Costs</h3>
            {scenario.closingCosts > 0 ? (
              <>
                <div className="total-costs">
                  <span className="label">Total Closing Costs</span>
                  <span className="value">{formatCurrency(scenario.closingCosts)}</span>
                </div>
                <p className="detail-note">
                  Closing costs include origination fees, appraisal, title insurance,
                  recording fees, and prepaid items like interest and escrow setup.
                </p>
              </>
            ) : (
              <p>No closing costs for this option.</p>
            )}
          </div>
        )}

        {type === 'strategy' && (
          <div className="modal-content strategy-details">
            <h3>Repayment Strategy</h3>
            <div className="strategy-info">
              <div className="strategy-item">
                <span className="icon">📅</span>
                <div>
                  <span className="label">Loan Term</span>
                  <span className="value">{scenario.term} years ({scenario.term * 12} payments)</span>
                </div>
              </div>
              <div className="strategy-item">
                <span className="icon">📈</span>
                <div>
                  <span className="label">Interest Rate</span>
                  <span className="value">{scenario.rate}% APR</span>
                </div>
              </div>
              {scenario.monthlySavings > 0 && (
                <div className="strategy-item highlight">
                  <span className="icon">💰</span>
                  <div>
                    <span className="label">Monthly Savings</span>
                    <span className="value">{formatCurrency(scenario.monthlySavings)}/month</span>
                  </div>
                </div>
              )}
              {scenario.breakevenMonths && (
                <div className="strategy-item">
                  <span className="icon">⏱️</span>
                  <div>
                    <span className="label">Breakeven Point</span>
                    <span className="value">
                      {Math.floor(scenario.breakevenMonths / 12)} years, {scenario.breakevenMonths % 12} months
                    </span>
                  </div>
                </div>
              )}
              {scenario.cashOut > 0 && (
                <div className="strategy-item cashout">
                  <span className="icon">💵</span>
                  <div>
                    <span className="label">Cash at Closing</span>
                    <span className="value">{formatCurrency(scenario.cashOut)}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button className="action-btn primary" onClick={onClose}>
            Got It
          </button>
        </div>
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

function calculateNetWorth(scenario, months, homeValue) {
  // Simple net worth calculation:
  // Home equity (principal paid) + savings from lower payments - closing costs
  const monthlyRate = scenario.rate / 100 / 12;
  let balance = scenario.loanAmount;
  let totalPrincipalPaid = 0;

  for (let i = 0; i < Math.min(months, scenario.term * 12); i++) {
    const interest = balance * monthlyRate;
    const principal = scenario.monthlyPayment - interest;
    totalPrincipalPaid += principal;
    balance -= principal;
  }

  // Assume 3% annual home appreciation
  const appreciatedHomeValue = homeValue * Math.pow(1.03, months / 12);
  const equity = appreciatedHomeValue - Math.max(0, balance);

  // Add cash out if applicable
  const cashBenefit = scenario.cashOut || 0;

  return equity + cashBenefit - scenario.closingCosts;
}

export { TotalCostAnalysis };
