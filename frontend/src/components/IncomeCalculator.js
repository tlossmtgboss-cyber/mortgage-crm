import React, { useState, useEffect } from 'react';
import { incomeAPI } from '../services/api';
import './IncomeCalculator.css';

const INCOME_TYPE_INFO = {
  W2_WAGES: { icon: '💼', label: 'W-2 Employment', color: '#3b82f6' },
  SELF_EMPLOYMENT: { icon: '🏢', label: 'Self-Employment', color: '#8b5cf6' },
  RENTAL: { icon: '🏠', label: 'Rental Income', color: '#10b981' },
  PARTNERSHIP_SCORP: { icon: '🤝', label: 'K-1 Partnership/S-Corp', color: '#f59e0b' },
  CCORP: { icon: '🏛️', label: 'C-Corporation', color: '#6366f1' },
  BANK_STATEMENT: { icon: '🏦', label: 'Bank Statement', color: '#ec4899' },
};

const SEVERITY_STYLES = {
  BLOCKING: { bg: '#fef2f2', border: '#fecaca', text: '#991b1b', icon: '🚫' },
  ERROR: { bg: '#fef2f2', border: '#fecaca', text: '#dc2626', icon: '❌' },
  WARNING: { bg: '#fffbeb', border: '#fde68a', text: '#92400e', icon: '⚠️' },
  INFO: { bg: '#eff6ff', border: '#bfdbfe', text: '#1e40af', icon: 'ℹ️' },
};

function IncomeCalculator({ loanId, borrowerId = 1, onIncomeCalculated }) {
  const [activeView, setActiveView] = useState('summary'); // 'summary', 'input', 'details'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Calculation result
  const [calculationResult, setCalculationResult] = useState(null);

  // Supported types
  const [supportedTypes, setSupportedTypes] = useState([]);

  // Input forms
  const [selectedType, setSelectedType] = useState(null);
  const [incomeEntries, setIncomeEntries] = useState({
    w2: [],
    scheduleC: [],
    scheduleE: [],
    k1: [],
    bankStatement: []
  });

  // Load supported income types on mount
  useEffect(() => {
    loadSupportedTypes();
  }, []);

  // Try to load existing calculation for this loan
  useEffect(() => {
    if (loanId) {
      loadExistingCalculation();
    }
  }, [loanId, borrowerId]);

  const loadSupportedTypes = async () => {
    try {
      const types = await incomeAPI.getSupportedTypes();
      setSupportedTypes(types);
    } catch (err) {
      console.error('Failed to load income types:', err);
    }
  };

  const loadExistingCalculation = async () => {
    try {
      setLoading(true);
      const summary = await incomeAPI.getLoanSummary(loanId, borrowerId);
      if (summary && summary.total_monthly_income > 0) {
        setCalculationResult(summary);
      }
    } catch (err) {
      // No existing calculation, that's okay
      console.log('No existing income calculation found');
    } finally {
      setLoading(false);
    }
  };

  const addW2Entry = () => {
    setIncomeEntries(prev => ({
      ...prev,
      w2: [...prev.w2, {
        id: Date.now(),
        tax_year: new Date().getFullYear() - 1,
        employer_name: '',
        box1_wages: '',
      }]
    }));
  };

  const addScheduleCEntry = () => {
    setIncomeEntries(prev => ({
      ...prev,
      scheduleC: [...prev.scheduleC, {
        id: Date.now(),
        tax_year: new Date().getFullYear() - 1,
        business_name: '',
        line31_net_profit_loss: '',
        line13_depreciation: '',
      }]
    }));
  };

  const addScheduleEEntry = () => {
    setIncomeEntries(prev => ({
      ...prev,
      scheduleE: [...prev.scheduleE, {
        id: Date.now(),
        tax_year: new Date().getFullYear() - 1,
        property_address: '',
        gross_rents: '',
        total_expenses: '',
        depreciation: '',
      }]
    }));
  };

  const addK1Entry = () => {
    setIncomeEntries(prev => ({
      ...prev,
      k1: [...prev.k1, {
        id: Date.now(),
        tax_year: new Date().getFullYear() - 1,
        k1_type: 'PARTNERSHIP',
        entity_name: '',
        ownership_percentage: '',
        box1_ordinary_income: '',
        box4_guaranteed_payments: '',
      }]
    }));
  };

  const addBankStatementEntry = () => {
    setIncomeEntries(prev => ({
      ...prev,
      bankStatement: [...prev.bankStatement, {
        id: Date.now(),
        bank_name: '',
        account_type: 'checking',
        months_of_data: 12,
        business_type: 'service',
        total_deposits: '',
      }]
    }));
  };

  const updateEntry = (type, id, field, value) => {
    setIncomeEntries(prev => ({
      ...prev,
      [type]: prev[type].map(entry =>
        entry.id === id ? { ...entry, [field]: value } : entry
      )
    }));
  };

  const removeEntry = (type, id) => {
    setIncomeEntries(prev => ({
      ...prev,
      [type]: prev[type].filter(entry => entry.id !== id)
    }));
  };

  const calculateIncome = async () => {
    setLoading(true);
    setError(null);

    try {
      // Build the request with all entries
      const now = new Date().toISOString();

      const w2Facts = incomeEntries.w2.filter(e => e.employer_name && e.box1_wages).map((e, idx) => ({
        document_id: `w2-${e.tax_year}-${idx}`,
        document_type: 'W2',
        extraction_date: now,
        confidence_score: 100,
        tax_year: parseInt(e.tax_year),
        employer_name: e.employer_name,
        box1_wages: parseFloat(e.box1_wages) || 0,
      }));

      const scheduleCFacts = incomeEntries.scheduleC.filter(e => e.line31_net_profit_loss).map((e, idx) => ({
        document_id: `sch-c-${e.tax_year}-${idx}`,
        document_type: 'SCHEDULE_C',
        extraction_date: now,
        confidence_score: 100,
        tax_year: parseInt(e.tax_year),
        business_name: e.business_name || 'Self-Employment',
        line31_net_profit_loss: parseFloat(e.line31_net_profit_loss) || 0,
        line13_depreciation: parseFloat(e.line13_depreciation) || 0,
      }));

      const scheduleEFacts = incomeEntries.scheduleE.filter(e => e.gross_rents).map((e, idx) => ({
        document_id: `sch-e-${e.tax_year}-${idx}`,
        document_type: 'SCHEDULE_E',
        extraction_date: now,
        confidence_score: 100,
        tax_year: parseInt(e.tax_year),
        properties: [{
          property_address: e.property_address || 'Rental Property',
          gross_rents: parseFloat(e.gross_rents) || 0,
          total_expenses: parseFloat(e.total_expenses) || 0,
          depreciation: parseFloat(e.depreciation) || 0,
        }]
      }));

      const k1Facts = incomeEntries.k1.filter(e => e.entity_name && e.box1_ordinary_income).map((e, idx) => ({
        document_id: `k1-${e.tax_year}-${idx}`,
        document_type: 'K1',
        extraction_date: now,
        confidence_score: 100,
        tax_year: parseInt(e.tax_year),
        k1_type: e.k1_type,
        entity_name: e.entity_name,
        ownership_percentage: parseFloat(e.ownership_percentage) || 0,
        box1_ordinary_income: parseFloat(e.box1_ordinary_income) || 0,
        box4_guaranteed_payments: parseFloat(e.box4_guaranteed_payments) || 0,
      }));

      const bankStatementFacts = incomeEntries.bankStatement.filter(e => e.total_deposits).map((e, idx) => ({
        document_id: `bank-${idx}`,
        document_type: 'BANK_STATEMENT',
        extraction_date: now,
        confidence_score: 100,
        bank_name: e.bank_name || 'Bank',
        account_type: e.account_type,
        months_of_data: parseInt(e.months_of_data) || 12,
        monthly_data: [{
          month: new Date().toISOString().slice(0, 7),
          total_deposits: parseFloat(e.total_deposits) || 0,
          ending_balance: 0,
        }]
      }));

      const request = {
        loan_id: loanId,
        borrower_id: borrowerId,
        w2_facts: w2Facts.length > 0 ? w2Facts : undefined,
        schedule_c_facts: scheduleCFacts.length > 0 ? scheduleCFacts : undefined,
        schedule_e_facts: scheduleEFacts.length > 0 ? scheduleEFacts : undefined,
        k1_facts: k1Facts.length > 0 ? k1Facts : undefined,
        bank_statement_facts: bankStatementFacts.length > 0 ? bankStatementFacts : undefined,
      };

      const result = await incomeAPI.calculate(request);
      setCalculationResult(result);
      setActiveView('summary');

      if (onIncomeCalculated) {
        onIncomeCalculated(result);
      }
    } catch (err) {
      console.error('Income calculation failed:', err);
      setError(err.response?.data?.detail || 'Failed to calculate income');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(amount || 0);
  };

  const renderSummaryView = () => {
    if (!calculationResult) {
      return (
        <div className="income-empty-state">
          <div className="income-empty-icon">📊</div>
          <h3>No Income Calculated</h3>
          <p>Add income sources to calculate qualifying income for this loan.</p>
          <button
            className="income-btn income-btn-primary"
            onClick={() => setActiveView('input')}
          >
            + Add Income Sources
          </button>
        </div>
      );
    }

    return (
      <div className="income-summary">
        {/* Total Income Card */}
        <div className="income-total-card">
          <div className="income-total-header">
            <span className="income-total-label">Total Qualifying Income</span>
            <span className={`income-status ${calculationResult.is_approvable ? 'approvable' : 'not-approvable'}`}>
              {calculationResult.is_approvable ? '✓ Approvable' : '✗ Issues Found'}
            </span>
          </div>
          <div className="income-total-amounts">
            <div className="income-amount-box">
              <span className="income-amount-value">{formatCurrency(calculationResult.total_monthly_income)}</span>
              <span className="income-amount-label">Monthly</span>
            </div>
            <div className="income-amount-divider">×12</div>
            <div className="income-amount-box">
              <span className="income-amount-value">{formatCurrency(calculationResult.total_annual_income)}</span>
              <span className="income-amount-label">Annual</span>
            </div>
          </div>
        </div>

        {/* Income Streams */}
        {calculationResult.income_streams && calculationResult.income_streams.length > 0 && (
          <div className="income-streams-section">
            <h4>Income Breakdown</h4>
            <div className="income-streams-list">
              {calculationResult.income_streams.map((stream, idx) => {
                const typeInfo = INCOME_TYPE_INFO[stream.stream_type] || { icon: '💰', label: stream.stream_type, color: '#6b7280' };
                return (
                  <div key={idx} className="income-stream-card" style={{ borderLeftColor: typeInfo.color }}>
                    <div className="income-stream-header">
                      <span className="income-stream-icon">{typeInfo.icon}</span>
                      <span className="income-stream-name">{stream.stream_name}</span>
                      {stream.trending_direction && (
                        <span className={`income-trend ${stream.trending_direction.toLowerCase()}`}>
                          {stream.trending_direction === 'INCREASING' ? '↑' : stream.trending_direction === 'DECLINING' ? '↓' : '→'}
                          {stream.trending_percentage ? ` ${Math.abs(stream.trending_percentage).toFixed(1)}%` : ''}
                        </span>
                      )}
                    </div>
                    <div className="income-stream-amounts">
                      <span className="income-stream-monthly">{formatCurrency(stream.monthly_income)}/mo</span>
                      <span className="income-stream-annual">{formatCurrency(stream.annual_income)}/yr</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Flags */}
        {calculationResult.flags && calculationResult.flags.length > 0 && (
          <div className="income-flags-section">
            <h4>Flags & Conditions</h4>
            <div className="income-flags-list">
              {calculationResult.flags.map((flag, idx) => {
                const style = SEVERITY_STYLES[flag.severity] || SEVERITY_STYLES.INFO;
                return (
                  <div
                    key={idx}
                    className="income-flag-card"
                    style={{ backgroundColor: style.bg, borderColor: style.border }}
                  >
                    <span className="income-flag-icon">{style.icon}</span>
                    <div className="income-flag-content">
                      <span className="income-flag-message" style={{ color: style.text }}>
                        {flag.message}
                      </span>
                      {flag.required_action && (
                        <span className="income-flag-action">{flag.required_action}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Flags Summary */}
        {calculationResult.flags_summary && (
          <div className="income-flags-summary">
            {calculationResult.flags_summary.blocking > 0 && (
              <span className="flag-badge blocking">{calculationResult.flags_summary.blocking} Blocking</span>
            )}
            {calculationResult.flags_summary.errors > 0 && (
              <span className="flag-badge error">{calculationResult.flags_summary.errors} Errors</span>
            )}
            {calculationResult.flags_summary.warnings > 0 && (
              <span className="flag-badge warning">{calculationResult.flags_summary.warnings} Warnings</span>
            )}
            {calculationResult.flags_summary.info > 0 && (
              <span className="flag-badge info">{calculationResult.flags_summary.info} Info</span>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="income-actions">
          <button
            className="income-btn income-btn-secondary"
            onClick={() => setActiveView('input')}
          >
            Edit Income Sources
          </button>
          <button
            className="income-btn income-btn-primary"
            onClick={calculateIncome}
            disabled={loading}
          >
            {loading ? 'Recalculating...' : 'Recalculate'}
          </button>
        </div>
      </div>
    );
  };

  const renderInputView = () => {
    return (
      <div className="income-input-view">
        <div className="income-input-header">
          <h3>Income Sources</h3>
          <p>Add all income sources for this borrower. Two years of history is typically required.</p>
        </div>

        {/* Income Type Buttons */}
        <div className="income-type-buttons">
          <button className="income-type-btn" onClick={addW2Entry}>
            <span className="income-type-icon">💼</span>
            <span>Add W-2</span>
          </button>
          <button className="income-type-btn" onClick={addScheduleCEntry}>
            <span className="income-type-icon">🏢</span>
            <span>Add Schedule C</span>
          </button>
          <button className="income-type-btn" onClick={addScheduleEEntry}>
            <span className="income-type-icon">🏠</span>
            <span>Add Rental (Sch E)</span>
          </button>
          <button className="income-type-btn" onClick={addK1Entry}>
            <span className="income-type-icon">🤝</span>
            <span>Add K-1</span>
          </button>
          <button className="income-type-btn" onClick={addBankStatementEntry}>
            <span className="income-type-icon">🏦</span>
            <span>Add Bank Stmt</span>
          </button>
        </div>

        {/* W-2 Entries */}
        {incomeEntries.w2.length > 0 && (
          <div className="income-entry-section">
            <h4>💼 W-2 Employment Income</h4>
            {incomeEntries.w2.map(entry => (
              <div key={entry.id} className="income-entry-card">
                <button className="income-entry-remove" onClick={() => removeEntry('w2', entry.id)}>×</button>
                <div className="income-entry-fields">
                  <div className="income-field">
                    <label>Tax Year</label>
                    <select
                      value={entry.tax_year}
                      onChange={(e) => updateEntry('w2', entry.id, 'tax_year', e.target.value)}
                    >
                      {[0, 1, 2, 3].map(offset => {
                        const year = new Date().getFullYear() - offset;
                        return <option key={year} value={year}>{year}</option>;
                      })}
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Employer Name</label>
                    <input
                      type="text"
                      placeholder="e.g., ACME Corporation"
                      value={entry.employer_name}
                      onChange={(e) => updateEntry('w2', entry.id, 'employer_name', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Box 1 Wages</label>
                    <input
                      type="number"
                      placeholder="e.g., 85000"
                      value={entry.box1_wages}
                      onChange={(e) => updateEntry('w2', entry.id, 'box1_wages', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Schedule C Entries */}
        {incomeEntries.scheduleC.length > 0 && (
          <div className="income-entry-section">
            <h4>🏢 Schedule C Self-Employment</h4>
            {incomeEntries.scheduleC.map(entry => (
              <div key={entry.id} className="income-entry-card">
                <button className="income-entry-remove" onClick={() => removeEntry('scheduleC', entry.id)}>×</button>
                <div className="income-entry-fields">
                  <div className="income-field">
                    <label>Tax Year</label>
                    <select
                      value={entry.tax_year}
                      onChange={(e) => updateEntry('scheduleC', entry.id, 'tax_year', e.target.value)}
                    >
                      {[0, 1, 2, 3].map(offset => {
                        const year = new Date().getFullYear() - offset;
                        return <option key={year} value={year}>{year}</option>;
                      })}
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Business Name</label>
                    <input
                      type="text"
                      placeholder="Optional"
                      value={entry.business_name}
                      onChange={(e) => updateEntry('scheduleC', entry.id, 'business_name', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Net Profit (Line 31)</label>
                    <input
                      type="number"
                      placeholder="e.g., 75000"
                      value={entry.line31_net_profit_loss}
                      onChange={(e) => updateEntry('scheduleC', entry.id, 'line31_net_profit_loss', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Depreciation (Line 13)</label>
                    <input
                      type="number"
                      placeholder="e.g., 5000"
                      value={entry.line13_depreciation}
                      onChange={(e) => updateEntry('scheduleC', entry.id, 'line13_depreciation', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Schedule E Entries */}
        {incomeEntries.scheduleE.length > 0 && (
          <div className="income-entry-section">
            <h4>🏠 Schedule E Rental Income</h4>
            {incomeEntries.scheduleE.map(entry => (
              <div key={entry.id} className="income-entry-card">
                <button className="income-entry-remove" onClick={() => removeEntry('scheduleE', entry.id)}>×</button>
                <div className="income-entry-fields">
                  <div className="income-field">
                    <label>Tax Year</label>
                    <select
                      value={entry.tax_year}
                      onChange={(e) => updateEntry('scheduleE', entry.id, 'tax_year', e.target.value)}
                    >
                      {[0, 1, 2, 3].map(offset => {
                        const year = new Date().getFullYear() - offset;
                        return <option key={year} value={year}>{year}</option>;
                      })}
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Property Address</label>
                    <input
                      type="text"
                      placeholder="e.g., 123 Main St, City, ST"
                      value={entry.property_address}
                      onChange={(e) => updateEntry('scheduleE', entry.id, 'property_address', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Gross Rents (Line 3)</label>
                    <input
                      type="number"
                      placeholder="e.g., 24000"
                      value={entry.gross_rents}
                      onChange={(e) => updateEntry('scheduleE', entry.id, 'gross_rents', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Total Expenses</label>
                    <input
                      type="number"
                      placeholder="e.g., 15000"
                      value={entry.total_expenses}
                      onChange={(e) => updateEntry('scheduleE', entry.id, 'total_expenses', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Depreciation</label>
                    <input
                      type="number"
                      placeholder="e.g., 8000"
                      value={entry.depreciation}
                      onChange={(e) => updateEntry('scheduleE', entry.id, 'depreciation', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* K-1 Entries */}
        {incomeEntries.k1.length > 0 && (
          <div className="income-entry-section">
            <h4>🤝 K-1 Partnership/S-Corp Income</h4>
            {incomeEntries.k1.map(entry => (
              <div key={entry.id} className="income-entry-card">
                <button className="income-entry-remove" onClick={() => removeEntry('k1', entry.id)}>×</button>
                <div className="income-entry-fields">
                  <div className="income-field">
                    <label>Tax Year</label>
                    <select
                      value={entry.tax_year}
                      onChange={(e) => updateEntry('k1', entry.id, 'tax_year', e.target.value)}
                    >
                      {[0, 1, 2, 3].map(offset => {
                        const year = new Date().getFullYear() - offset;
                        return <option key={year} value={year}>{year}</option>;
                      })}
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Entity Type</label>
                    <select
                      value={entry.k1_type}
                      onChange={(e) => updateEntry('k1', entry.id, 'k1_type', e.target.value)}
                    >
                      <option value="PARTNERSHIP">Partnership (1065)</option>
                      <option value="SCORP">S-Corporation (1120S)</option>
                      <option value="CCORP">C-Corporation (1120)</option>
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Entity Name</label>
                    <input
                      type="text"
                      placeholder="e.g., ABC Holdings LLC"
                      value={entry.entity_name}
                      onChange={(e) => updateEntry('k1', entry.id, 'entity_name', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Ownership %</label>
                    <input
                      type="number"
                      placeholder="e.g., 50"
                      value={entry.ownership_percentage}
                      onChange={(e) => updateEntry('k1', entry.id, 'ownership_percentage', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Ordinary Income (Box 1)</label>
                    <input
                      type="number"
                      placeholder="e.g., 100000"
                      value={entry.box1_ordinary_income}
                      onChange={(e) => updateEntry('k1', entry.id, 'box1_ordinary_income', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Guaranteed Payments (Box 4)</label>
                    <input
                      type="number"
                      placeholder="e.g., 25000"
                      value={entry.box4_guaranteed_payments}
                      onChange={(e) => updateEntry('k1', entry.id, 'box4_guaranteed_payments', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Bank Statement Entries */}
        {incomeEntries.bankStatement.length > 0 && (
          <div className="income-entry-section">
            <h4>🏦 Bank Statement Income (Non-QM)</h4>
            {incomeEntries.bankStatement.map(entry => (
              <div key={entry.id} className="income-entry-card">
                <button className="income-entry-remove" onClick={() => removeEntry('bankStatement', entry.id)}>×</button>
                <div className="income-entry-fields">
                  <div className="income-field">
                    <label>Bank Name</label>
                    <input
                      type="text"
                      placeholder="e.g., Chase Bank"
                      value={entry.bank_name}
                      onChange={(e) => updateEntry('bankStatement', entry.id, 'bank_name', e.target.value)}
                    />
                  </div>
                  <div className="income-field">
                    <label>Account Type</label>
                    <select
                      value={entry.account_type}
                      onChange={(e) => updateEntry('bankStatement', entry.id, 'account_type', e.target.value)}
                    >
                      <option value="checking">Business Checking</option>
                      <option value="savings">Business Savings</option>
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Months of Data</label>
                    <select
                      value={entry.months_of_data}
                      onChange={(e) => updateEntry('bankStatement', entry.id, 'months_of_data', e.target.value)}
                    >
                      <option value={12}>12 Months</option>
                      <option value={24}>24 Months</option>
                    </select>
                  </div>
                  <div className="income-field">
                    <label>Business Type</label>
                    <select
                      value={entry.business_type}
                      onChange={(e) => updateEntry('bankStatement', entry.id, 'business_type', e.target.value)}
                    >
                      <option value="service">Service (50% expense ratio)</option>
                      <option value="retail">Retail (65% expense ratio)</option>
                      <option value="restaurant">Restaurant (70% expense ratio)</option>
                      <option value="construction">Construction (60% expense ratio)</option>
                    </select>
                  </div>
                  <div className="income-field income-field-full">
                    <label>Average Monthly Deposits</label>
                    <input
                      type="number"
                      placeholder="e.g., 25000"
                      value={entry.total_deposits}
                      onChange={(e) => updateEntry('bankStatement', entry.id, 'total_deposits', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="income-error-message">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="income-actions">
          <button
            className="income-btn income-btn-secondary"
            onClick={() => setActiveView('summary')}
          >
            Cancel
          </button>
          <button
            className="income-btn income-btn-primary"
            onClick={calculateIncome}
            disabled={loading || (
              incomeEntries.w2.length === 0 &&
              incomeEntries.scheduleC.length === 0 &&
              incomeEntries.scheduleE.length === 0 &&
              incomeEntries.k1.length === 0 &&
              incomeEntries.bankStatement.length === 0
            )}
          >
            {loading ? 'Calculating...' : 'Calculate Income'}
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="income-calculator">
      <div className="income-calculator-header">
        <h3>📊 Income Calculator</h3>
        <div className="income-view-toggle">
          <button
            className={`income-view-btn ${activeView === 'summary' ? 'active' : ''}`}
            onClick={() => setActiveView('summary')}
          >
            Summary
          </button>
          <button
            className={`income-view-btn ${activeView === 'input' ? 'active' : ''}`}
            onClick={() => setActiveView('input')}
          >
            Input
          </button>
        </div>
      </div>

      <div className="income-calculator-content">
        {loading && activeView === 'summary' && !calculationResult ? (
          <div className="income-loading">
            <div className="income-loading-spinner"></div>
            <span>Loading income data...</span>
          </div>
        ) : (
          activeView === 'summary' ? renderSummaryView() : renderInputView()
        )}
      </div>
    </div>
  );
}

export default IncomeCalculator;
