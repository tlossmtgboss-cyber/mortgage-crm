import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { profitabilityAPI } from '../services/api';
import './ScenarioModeling.css';
import { toast } from '../utils/toast';

const ScenarioModeling = () => {
  const navigate = useNavigate();

  // State
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState([]);
  const [baseMonth, setBaseMonth] = useState('');
  const [scenarioName, setScenarioName] = useState('');
  const [results, setResults] = useState(null);
  const [savedScenarios, setSavedScenarios] = useState([]);

  // Scenario parameters
  const [staffChanges, setStaffChanges] = useState({});
  const [loanVolumeChange, setLoanVolumeChange] = useState(0);
  const [revenuePerLoanChange, setRevenuePerLoanChange] = useState(0);
  const [expenseChanges, setExpenseChanges] = useState({
    personnel: 0,
    marketing: 0,
    technology: 0,
    operations: 0
  });

  // Get current month
  const getCurrentMonth = () => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  };

  // Load roles and saved scenarios
  useEffect(() => {
    setBaseMonth(getCurrentMonth());
    loadRoles();
    loadSavedScenarios();
  }, []);

  const loadRoles = async () => {
    try {
      const data = await profitabilityAPI.getRoles();
      setRoles(data);
      // Initialize staff changes
      const changes = {};
      data.forEach(role => {
        changes[role.id] = 0;
      });
      setStaffChanges(changes);
    } catch (err) {
      console.error('Failed to load roles:', err);
    }
  };

  const loadSavedScenarios = async () => {
    try {
      const data = await profitabilityAPI.getScenarios(true);
      setSavedScenarios(data);
    } catch (err) {
      console.error('Failed to load scenarios:', err);
    }
  };

  // Run scenario
  const runScenario = async () => {
    try {
      setLoading(true);
      const parameters = {
        staff_changes: staffChanges,
        loan_volume_change: loanVolumeChange,
        revenue_per_loan_change: revenuePerLoanChange,
        expense_changes: expenseChanges
      };

      const data = await profitabilityAPI.runScenario(baseMonth, parameters);
      setResults(data);
    } catch (err) {
      console.error('Failed to run scenario:', err);
    } finally {
      setLoading(false);
    }
  };

  // Save scenario
  const saveScenario = async () => {
    if (!scenarioName.trim()) {
      toast.error('Please enter a scenario name');
      return;
    }

    try {
      const data = {
        name: scenarioName,
        description: `What-if analysis for ${baseMonth}`,
        base_month: `${baseMonth}-01`,
        parameters: {
          staff_changes: staffChanges,
          loan_volume_change: loanVolumeChange,
          revenue_per_loan_change: revenuePerLoanChange,
          expense_changes: expenseChanges
        }
      };

      await profitabilityAPI.createScenario(data);
      toast.success('Scenario saved successfully!');
      loadSavedScenarios();
      setScenarioName('');
    } catch (err) {
      console.error('Failed to save scenario:', err);
      toast.error('Failed to save scenario');
    }
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return '$0';
    const num = Number(amount);
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0
    }).format(num);
  };

  // Format change
  const formatChange = (value) => {
    const num = Number(value);
    if (num > 0) return `+${formatCurrency(num)}`;
    if (num < 0) return formatCurrency(num);
    return '$0';
  };

  // Reset scenario
  const resetScenario = () => {
    const changes = {};
    roles.forEach(role => {
      changes[role.id] = 0;
    });
    setStaffChanges(changes);
    setLoanVolumeChange(0);
    setRevenuePerLoanChange(0);
    setExpenseChanges({
      personnel: 0,
      marketing: 0,
      technology: 0,
      operations: 0
    });
    setResults(null);
  };

  // Generate month options
  const getMonthOptions = () => {
    const options = [];
    const now = new Date();
    for (let i = 0; i < 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      const label = date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      options.push({ value, label });
    }
    return options;
  };

  return (
    <div className="scenario-modeling">
      {/* Header */}
      <header className="scenario-header">
        <div className="header-content">
          <button className="btn-back" onClick={() => navigate('/profitability')}>
            &larr; Back to Dashboard
          </button>
          <h1>Scenario Modeling</h1>
          <p className="header-subtitle">Run "What If" analyses to plan business decisions</p>
        </div>
        <div className="header-actions">
          <select
            value={baseMonth}
            onChange={(e) => setBaseMonth(e.target.value)}
            className="month-selector"
          >
            {getMonthOptions().map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </header>

      <div className="scenario-content">
        {/* Parameters Panel */}
        <div className="parameters-panel">
          <h2>Scenario Parameters</h2>

          {/* Staff Changes */}
          <div className="param-section">
            <h3>Staff Changes</h3>
            <p className="param-desc">Adjust employee count by role</p>
            {roles.map(role => (
              <div key={role.id} className="param-row">
                <label>{role.name}</label>
                <div className="param-control">
                  <button
                    onClick={() => setStaffChanges({
                      ...staffChanges,
                      [role.id]: (staffChanges[role.id] || 0) - 1
                    })}
                  >
                    -
                  </button>
                  <span className={staffChanges[role.id] !== 0 ? 'changed' : ''}>
                    {staffChanges[role.id] > 0 ? '+' : ''}{staffChanges[role.id] || 0}
                  </span>
                  <button
                    onClick={() => setStaffChanges({
                      ...staffChanges,
                      [role.id]: (staffChanges[role.id] || 0) + 1
                    })}
                  >
                    +
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Volume Changes */}
          <div className="param-section">
            <h3>Loan Volume</h3>
            <p className="param-desc">Project changes in loan volume</p>
            <div className="param-row">
              <label>Volume Change</label>
              <div className="slider-control">
                <input
                  type="range"
                  min="-50"
                  max="100"
                  value={loanVolumeChange}
                  onChange={(e) => setLoanVolumeChange(Number(e.target.value))}
                />
                <span className={loanVolumeChange !== 0 ? 'changed' : ''}>
                  {loanVolumeChange > 0 ? '+' : ''}{loanVolumeChange}%
                </span>
              </div>
            </div>
            <div className="param-row">
              <label>Revenue Per Loan</label>
              <div className="slider-control">
                <input
                  type="range"
                  min="-30"
                  max="50"
                  value={revenuePerLoanChange}
                  onChange={(e) => setRevenuePerLoanChange(Number(e.target.value))}
                />
                <span className={revenuePerLoanChange !== 0 ? 'changed' : ''}>
                  {revenuePerLoanChange > 0 ? '+' : ''}{revenuePerLoanChange}%
                </span>
              </div>
            </div>
          </div>

          {/* Expense Changes */}
          <div className="param-section">
            <h3>Expense Adjustments</h3>
            <p className="param-desc">Modify expense categories</p>
            {Object.keys(expenseChanges).map(category => (
              <div key={category} className="param-row">
                <label>{category.charAt(0).toUpperCase() + category.slice(1)}</label>
                <div className="slider-control">
                  <input
                    type="range"
                    min="-50"
                    max="100"
                    value={expenseChanges[category]}
                    onChange={(e) => setExpenseChanges({
                      ...expenseChanges,
                      [category]: Number(e.target.value)
                    })}
                  />
                  <span className={expenseChanges[category] !== 0 ? 'changed' : ''}>
                    {expenseChanges[category] > 0 ? '+' : ''}{expenseChanges[category]}%
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="param-actions">
            <button className="btn-primary" onClick={runScenario} disabled={loading}>
              {loading ? 'Running...' : 'Run Scenario'}
            </button>
            <button className="btn-secondary" onClick={resetScenario}>
              Reset
            </button>
          </div>
        </div>

        {/* Results Panel */}
        <div className="results-panel">
          {results ? (
            <>
              <h2>Scenario Results</h2>

              {/* Comparison Cards */}
              <div className="comparison-grid">
                <div className="comparison-card">
                  <h3>Revenue</h3>
                  <div className="comparison-values">
                    <div className="baseline">
                      <span className="label">Baseline</span>
                      <span className="value">{formatCurrency(results.baseline.total_revenue)}</span>
                    </div>
                    <div className="arrow">→</div>
                    <div className="projected">
                      <span className="label">Projected</span>
                      <span className="value">{formatCurrency(results.projected.total_revenue)}</span>
                    </div>
                  </div>
                  <div className={`change ${results.revenue_change >= 0 ? 'positive' : 'negative'}`}>
                    {formatChange(results.revenue_change)}
                  </div>
                </div>

                <div className="comparison-card">
                  <h3>Expenses</h3>
                  <div className="comparison-values">
                    <div className="baseline">
                      <span className="label">Baseline</span>
                      <span className="value">{formatCurrency(results.baseline.total_expenses)}</span>
                    </div>
                    <div className="arrow">→</div>
                    <div className="projected">
                      <span className="label">Projected</span>
                      <span className="value">{formatCurrency(results.projected.total_expenses)}</span>
                    </div>
                  </div>
                  <div className={`change ${results.expense_change <= 0 ? 'positive' : 'negative'}`}>
                    {formatChange(results.expense_change)}
                  </div>
                </div>

                <div className="comparison-card highlight">
                  <h3>Net Profit</h3>
                  <div className="comparison-values">
                    <div className="baseline">
                      <span className="label">Baseline</span>
                      <span className="value">{formatCurrency(results.baseline.net_profit)}</span>
                    </div>
                    <div className="arrow">→</div>
                    <div className="projected">
                      <span className="label">Projected</span>
                      <span className="value">{formatCurrency(results.projected.net_profit)}</span>
                    </div>
                  </div>
                  <div className={`change ${results.profit_change >= 0 ? 'positive' : 'negative'}`}>
                    {formatChange(results.profit_change)}
                  </div>
                </div>
              </div>

              {/* Additional Metrics */}
              <div className="metrics-comparison">
                <div className="metric-row">
                  <span className="metric-label">Loans Closed</span>
                  <span className="metric-baseline">{results.baseline.loans_closed}</span>
                  <span className="metric-arrow">→</span>
                  <span className="metric-projected">{results.projected.loans_closed}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">Cost Per Loan</span>
                  <span className="metric-baseline">{formatCurrency(results.baseline.cost_per_loan)}</span>
                  <span className="metric-arrow">→</span>
                  <span className="metric-projected">{formatCurrency(results.projected.cost_per_loan)}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">Break-Even Loans</span>
                  <span className="metric-baseline">{results.baseline.break_even_loans}</span>
                  <span className="metric-arrow">→</span>
                  <span className="metric-projected">{results.projected.break_even_loans}</span>
                </div>
                <div className="metric-row">
                  <span className="metric-label">Profit Margin</span>
                  <span className="metric-baseline">{results.baseline.profit_margin}%</span>
                  <span className="metric-arrow">→</span>
                  <span className="metric-projected">{results.projected.profit_margin}%</span>
                </div>
              </div>

              {/* Recommendation */}
              <div className={`recommendation ${results.profit_change >= 0 ? 'positive' : 'negative'}`}>
                <h4>Recommendation</h4>
                <p>{results.recommendation}</p>
              </div>

              {/* Save Scenario */}
              <div className="save-scenario">
                <input
                  type="text"
                  placeholder="Scenario name..."
                  value={scenarioName}
                  onChange={(e) => setScenarioName(e.target.value)}
                />
                <button className="btn-primary" onClick={saveScenario}>
                  Save Scenario
                </button>
              </div>
            </>
          ) : (
            <div className="no-results">
              <div className="empty-icon">📊</div>
              <h3>No Results Yet</h3>
              <p>Adjust the parameters and click "Run Scenario" to see projected outcomes.</p>
            </div>
          )}
        </div>
      </div>

      {/* Saved Scenarios */}
      {savedScenarios.length > 0 && (
        <div className="saved-scenarios">
          <h2>Saved Scenarios</h2>
          <div className="scenarios-list">
            {savedScenarios.map(scenario => (
              <div key={scenario.id} className="saved-scenario-card">
                <h4>{scenario.name}</h4>
                <p className="scenario-date">
                  {new Date(scenario.created_at).toLocaleDateString()}
                </p>
                {scenario.results && (
                  <div className="scenario-summary">
                    <span className={scenario.results.profit_change >= 0 ? 'positive' : 'negative'}>
                      {formatChange(scenario.results.profit_change)} profit
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ScenarioModeling;
