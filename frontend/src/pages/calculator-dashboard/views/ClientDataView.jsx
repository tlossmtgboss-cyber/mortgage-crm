import React, { useState, useMemo } from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const ClientDataView = ({ data, onUpdateProfile, onUpdateMarket, onUpdateProperty, stateData }) => {
  const { profile, market, property, locationRates, effectiveRates, effectiveInterestRate } = data;

  // Local state for tab navigation and debt editing
  const [activeTab, setActiveTab] = useState('borrower');
  const [newDebtName, setNewDebtName] = useState('');
  const [newDebtAmount, setNewDebtAmount] = useState('');

  const handleAddDebt = () => {
    if (newDebtName && newDebtAmount) {
      const currentDebts = profile.debtBreakdown || [];
      const updatedDebts = [...currentDebts, { name: newDebtName, amount: parseFloat(newDebtAmount) }];
      const totalDebts = updatedDebts.reduce((sum, d) => sum + d.amount, 0);
      onUpdateProfile({
        debtBreakdown: updatedDebts,
        monthlyDebts: totalDebts,
      });
      setNewDebtName('');
      setNewDebtAmount('');
    }
  };

  const handleRemoveDebt = (index) => {
    const currentDebts = profile.debtBreakdown || [];
    const updatedDebts = currentDebts.filter((_, i) => i !== index);
    const totalDebts = updatedDebts.reduce((sum, d) => sum + d.amount, 0);
    onUpdateProfile({
      debtBreakdown: updatedDebts,
      monthlyDebts: totalDebts,
    });
  };

  const counties = stateData[property.state]?.counties || {};

  // Calculate some derived values for tab badges
  const loanAmount = property.homePrice * (1 - property.downPaymentPct / 100);
  const monthlyPI = useMemo(() => {
    const r = effectiveInterestRate / 100 / 12;
    const n = market.termYears * 12;
    if (r === 0) return loanAmount / n;
    return loanAmount * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
  }, [loanAmount, effectiveInterestRate, market.termYears]);

  const tabs = [
    { id: 'borrower', label: 'Borrower', icon: 'user', description: 'Profile & Income' },
    { id: 'property', label: 'Property', icon: 'home', description: 'Location & Details' },
    { id: 'loan', label: 'Loan', icon: 'percent', description: 'Rates & Terms' },
    { id: 'budget', label: 'Budget', icon: 'wallet', description: 'Monthly Expenses' },
    { id: 'scenarios', label: 'Scenarios', icon: 'chart', description: 'Price Options' },
  ];

  // Calculate DTI for display
  const estimatedPITI = monthlyPI + (property.homePrice * effectiveRates.taxRate / 12) + (property.homePrice * effectiveRates.insuranceRate / 12);
  const frontEndDTI = ((estimatedPITI / (profile.annualIncome / 12)) * 100).toFixed(1);

  return (
    <div className="calculator-detail client-data-view tabbed-view">
      {/* Tab Navigation */}
      <div className="client-data-tabs-wrapper">
        <div className="client-data-tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`client-data-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <div className="tab-icon">
                {tab.icon === 'user' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                  </svg>
                )}
                {tab.icon === 'home' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                  </svg>
                )}
                {tab.icon === 'percent' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="19" y1="5" x2="5" y2="19"/>
                    <circle cx="6.5" cy="6.5" r="2.5"/>
                    <circle cx="17.5" cy="17.5" r="2.5"/>
                  </svg>
                )}
                {tab.icon === 'wallet' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
                    <line x1="1" y1="10" x2="23" y2="10"/>
                  </svg>
                )}
                {tab.icon === 'chart' && (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="20" x2="18" y2="10"/>
                    <line x1="12" y1="20" x2="12" y2="4"/>
                    <line x1="6" y1="20" x2="6" y2="14"/>
                  </svg>
                )}
              </div>
              <div className="tab-text">
                <span className="tab-label">{tab.label}</span>
                <span className="tab-description">{tab.description}</span>
              </div>
              {activeTab === tab.id && <div className="tab-active-indicator" />}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="client-data-tab-content">
        {/* BORROWER TAB */}
        {activeTab === 'borrower' && (
          <div className="tab-panel borrower-panel">
            <div className="panel-section">
              <h3 className="panel-section-title">Personal Information</h3>
              <div className="data-grid">
                <div className="data-field">
                  <label>Name</label>
                  <input
                    type="text"
                    value={profile.name}
                    onChange={(e) => onUpdateProfile({ name: e.target.value })}
                    placeholder="Client name"
                  />
                </div>
                <div className="data-field">
                  <label>Age</label>
                  <input
                    type="number"
                    value={profile.age}
                    onChange={(e) => onUpdateProfile({ age: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">Income & Assets</h3>
              <div className="data-grid">
                <div className="data-field">
                  <label>Annual Income</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={profile.annualIncome}
                      onChange={(e) => onUpdateProfile({ annualIncome: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <span className="field-note">{formatCurrency(profile.annualIncome / 12)}/month</span>
                </div>
                <div className="data-field">
                  <label>Current Savings</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={profile.savings}
                      onChange={(e) => onUpdateProfile({ savings: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="data-field">
                  <label>Current Rent</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={profile.currentRent}
                      onChange={(e) => onUpdateProfile({ currentRent: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <span className="field-note">per month</span>
                </div>
              </div>
            </div>

            <div className="panel-section credit-section">
              <h3 className="panel-section-title">Credit Score</h3>
              <div className="credit-score-control">
                <div className="credit-score-display">
                  <span className={`credit-score-value ${profile.creditScore >= 740 ? 'excellent' : profile.creditScore >= 700 ? 'good' : profile.creditScore >= 650 ? 'fair' : 'poor'}`}>
                    {profile.creditScore}
                  </span>
                  <span className="credit-score-label">
                    {profile.creditScore >= 740 ? 'Excellent' : profile.creditScore >= 700 ? 'Good' : profile.creditScore >= 650 ? 'Fair' : 'Poor'}
                  </span>
                </div>
                <input
                  type="range"
                  min="500"
                  max="850"
                  value={profile.creditScore}
                  onChange={(e) => onUpdateProfile({ creditScore: parseInt(e.target.value) })}
                  className="credit-slider"
                />
                <div className="credit-scale">
                  <span>500</span>
                  <span>620</span>
                  <span>680</span>
                  <span>740</span>
                  <span>850</span>
                </div>
              </div>
              <div className="credit-impact-note">
                Higher credit scores qualify for better rates and lower PMI
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">
                Monthly Debts
                <span className="section-badge">{formatCurrency(profile.monthlyDebts)}/mo</span>
              </h3>
              <div className="debt-list-modern">
                {(profile.debtBreakdown || []).length === 0 && (
                  <div className="no-debts">No monthly debts added</div>
                )}
                {(profile.debtBreakdown || []).map((debt, index) => (
                  <div key={index} className="debt-item-modern">
                    <div className="debt-info">
                      <span className="debt-name">{debt.name}</span>
                      <span className="debt-amount">{formatCurrency(debt.amount)}/mo</span>
                    </div>
                    <button className="debt-remove-btn" onClick={() => handleRemoveDebt(index)}>
                      &times;
                    </button>
                  </div>
                ))}
              </div>
              <div className="add-debt-row">
                <input
                  type="text"
                  placeholder="Debt name"
                  value={newDebtName}
                  onChange={(e) => setNewDebtName(e.target.value)}
                />
                <div className="input-with-prefix compact">
                  <span className="prefix">$</span>
                  <input
                    type="number"
                    placeholder="0"
                    value={newDebtAmount}
                    onChange={(e) => setNewDebtAmount(e.target.value)}
                  />
                </div>
                <button className="add-debt-btn-modern" onClick={handleAddDebt}>Add</button>
              </div>
            </div>
          </div>
        )}

        {/* PROPERTY TAB */}
        {activeTab === 'property' && (
          <div className="tab-panel property-panel">
            <div className="panel-section">
              <h3 className="panel-section-title">Location</h3>
              <div className="data-grid">
                <div className="data-field">
                  <label>State</label>
                  <select
                    value={property.state}
                    onChange={(e) => onUpdateProperty({ state: e.target.value, county: '' })}
                  >
                    {Object.entries(stateData).map(([code, state]) => (
                      <option key={code} value={code}>{state.name}</option>
                    ))}
                  </select>
                </div>
                <div className="data-field">
                  <label>County</label>
                  <select
                    value={property.county}
                    onChange={(e) => onUpdateProperty({ county: e.target.value })}
                  >
                    <option value="">State Average</option>
                    {Object.keys(counties).map(county => (
                      <option key={county} value={county}>{county}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">Property Type</h3>
              <div className="property-type-selector">
                {[
                  { value: 'single_family', label: 'Single Family' },
                  { value: 'condo', label: 'Condo' },
                  { value: 'townhouse', label: 'Townhouse' },
                  { value: 'multi_family', label: 'Multi-Family' },
                ].map(type => (
                  <button
                    key={type.value}
                    className={`property-type-btn ${property.propertyType === type.value ? 'active' : ''}`}
                    onClick={() => onUpdateProperty({ propertyType: type.value })}
                  >
                    {type.label}
                  </button>
                ))}
              </div>
              <div className="data-field inline-field">
                <label>HOA Fees (if any)</label>
                <div className="input-with-prefix compact">
                  <span className="prefix">$</span>
                  <input
                    type="number"
                    value={property.hoaMonthly}
                    onChange={(e) => onUpdateProperty({ hoaMonthly: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <span className="field-note">/month</span>
              </div>
            </div>

            <div className="panel-section taxes-insurance-section">
              <h3 className="panel-section-title">
                Taxes & Insurance
                <span className="auto-badge">Auto-calculated</span>
              </h3>
              <p className="location-note">
                Based on {property.county || 'state average'} in {stateData[property.state]?.name || property.state}
              </p>

              <div className="tax-insurance-cards">
                <div className="ti-card">
                  <div className="ti-header">
                    <span className="ti-label">Property Tax</span>
                    <label className="override-switch">
                      <input
                        type="checkbox"
                        checked={property.taxRateOverride !== null}
                        onChange={(e) => onUpdateProperty({
                          taxRateOverride: e.target.checked ? effectiveRates.taxRate : null
                        })}
                      />
                      <span className="switch-slider"></span>
                      <span className="switch-label">Override</span>
                    </label>
                  </div>
                  <div className="ti-value">
                    {property.taxRateOverride !== null ? (
                      <div className="input-with-suffix compact">
                        <input
                          type="number"
                          step="0.01"
                          value={(property.taxRateOverride * 100).toFixed(2)}
                          onChange={(e) => onUpdateProperty({ taxRateOverride: parseFloat(e.target.value) / 100 })}
                        />
                        <span className="suffix">%</span>
                      </div>
                    ) : (
                      <span className="auto-value">{(locationRates.taxRate * 100).toFixed(2)}%</span>
                    )}
                  </div>
                  <div className="ti-monthly">
                    {formatCurrency((property.homePrice * effectiveRates.taxRate) / 12)}/mo
                  </div>
                </div>

                <div className="ti-card">
                  <div className="ti-header">
                    <span className="ti-label">Insurance</span>
                    <label className="override-switch">
                      <input
                        type="checkbox"
                        checked={property.insuranceRateOverride !== null}
                        onChange={(e) => onUpdateProperty({
                          insuranceRateOverride: e.target.checked ? effectiveRates.insuranceRate : null
                        })}
                      />
                      <span className="switch-slider"></span>
                      <span className="switch-label">Override</span>
                    </label>
                  </div>
                  <div className="ti-value">
                    {property.insuranceRateOverride !== null ? (
                      <div className="input-with-suffix compact">
                        <input
                          type="number"
                          step="0.01"
                          value={(property.insuranceRateOverride * 100).toFixed(2)}
                          onChange={(e) => onUpdateProperty({ insuranceRateOverride: parseFloat(e.target.value) / 100 })}
                        />
                        <span className="suffix">%</span>
                      </div>
                    ) : (
                      <span className="auto-value">{(locationRates.insuranceRate * 100).toFixed(2)}%</span>
                    )}
                  </div>
                  <div className="ti-monthly">
                    {formatCurrency((property.homePrice * effectiveRates.insuranceRate) / 12)}/mo
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* LOAN TAB */}
        {activeTab === 'loan' && (
          <div className="tab-panel loan-panel">
            {/* Purchase & Down Payment */}
            <div className="panel-section">
              <h3 className="panel-section-title">Purchase Details</h3>
              <div className="data-grid two-col">
                <div className="data-field">
                  <label>Home Price</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      value={property.homePrice}
                      onChange={(e) => onUpdateProperty({ homePrice: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="data-field">
                  <label>Down Payment</label>
                  <div className="down-payment-control">
                    <div className="input-with-suffix">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.5"
                        value={property.downPaymentPct}
                        onChange={(e) => onUpdateProperty({ downPaymentPct: parseFloat(e.target.value) || 0 })}
                      />
                      <span className="suffix">%</span>
                    </div>
                    <span className="down-amount">{formatCurrency(property.homePrice * property.downPaymentPct / 100)}</span>
                  </div>
                </div>
              </div>
              <div className="down-payment-presets">
                {[3, 3.5, 5, 10, 20].map(pct => (
                  <button
                    key={pct}
                    className={`preset-btn ${property.downPaymentPct === pct ? 'active' : ''}`}
                    onClick={() => onUpdateProperty({ downPaymentPct: pct })}
                  >
                    {pct}%
                  </button>
                ))}
              </div>
              <div className="loan-amount-display">
                <span>Loan Amount:</span>
                <strong>{formatCurrency(loanAmount)}</strong>
              </div>
            </div>

            {/* Loan Programs */}
            <div className="panel-section">
              <h3 className="panel-section-title">Loan Program</h3>
              <div className="loan-programs-grid">
                {[
                  { id: 'conventional', name: 'Conventional', desc: '3-20% down, 620+ credit', minDown: 3 },
                  { id: 'fha', name: 'FHA', desc: '3.5% down, 580+ credit', minDown: 3.5 },
                  { id: 'va', name: 'VA', desc: '0% down, veterans only', minDown: 0 },
                  { id: 'usda', name: 'USDA', desc: '0% down, rural areas', minDown: 0 },
                  { id: 'jumbo', name: 'Jumbo', desc: 'Loans over $832,750', minDown: 10 },
                  { id: 'allinone', name: 'All In One', desc: 'First-lien HELOC, 680+ credit', minDown: 20, special: true },
                ].map(program => (
                  <button
                    key={program.id}
                    className={`loan-program-btn ${market.loanProgram === program.id ? 'active' : ''} ${program.special ? 'special' : ''}`}
                    onClick={() => onUpdateMarket({ loanProgram: program.id })}
                  >
                    {program.special && <span className="program-badge">HELOC</span>}
                    <span className="program-name">{program.name}</span>
                    <span className="program-desc">{program.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Interest Rate Options */}
            <div className="panel-section">
              <h3 className="panel-section-title">Interest Rate Options</h3>
              <p className="section-description">
                Select rates to compare. Check multiple to see side-by-side analysis.
              </p>
              <div className="rate-options-grid">
                {[
                  { rate: 6.25, label: 'Excellent Credit', points: 1.5 },
                  { rate: 6.5, label: 'Great Credit', points: 1 },
                  { rate: 6.75, label: 'Good Credit', points: 0.5 },
                  { rate: 6.875, label: 'Market Rate', points: 0 },
                  { rate: 7.0, label: 'Fair Credit', points: 0 },
                  { rate: 7.25, label: 'Lower Credit', points: 0 },
                ].map(option => (
                  <label
                    key={option.rate}
                    className={`rate-option ${market.interestRate === option.rate ? 'selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="interestRate"
                      checked={market.interestRate === option.rate}
                      onChange={() => onUpdateMarket({ interestRate: option.rate, points: option.points })}
                    />
                    <span className="rate-option-rate">{option.rate}%</span>
                    <span className="rate-option-label">{option.label}</span>
                    {option.points > 0 && (
                      <span className="rate-option-points">{option.points} pts</span>
                    )}
                  </label>
                ))}
              </div>
              <div className="custom-rate-input">
                <label>Or enter custom rate:</label>
                <div className="input-with-suffix compact">
                  <input
                    type="number"
                    step="0.125"
                    value={market.interestRate}
                    onChange={(e) => onUpdateMarket({ interestRate: parseFloat(e.target.value) || 0 })}
                  />
                  <span className="suffix">%</span>
                </div>
              </div>
            </div>

            {/* Loan Term */}
            <div className="panel-section">
              <h3 className="panel-section-title">Loan Term</h3>
              <div className="term-selector">
                {[
                  { years: 30, label: '30 Year' },
                  { years: 20, label: '20 Year' },
                  { years: 15, label: '15 Year' },
                  { years: 10, label: '10 Year' },
                ].map(term => (
                  <button
                    key={term.years}
                    className={`term-btn ${market.termYears === term.years ? 'active' : ''}`}
                    onClick={() => onUpdateMarket({ termYears: term.years })}
                  >
                    <span className="term-years">{term.years}</span>
                    <span className="term-label">years</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Discount Points */}
            <div className="panel-section">
              <h3 className="panel-section-title">Discount Points</h3>
              <p className="section-description">
                Pay upfront to reduce your rate. Each point costs 1% of loan amount.
              </p>
              <div className="points-control">
                <div className="points-buttons">
                  {[0, 0.5, 1, 1.5, 2].map(points => (
                    <button
                      key={points}
                      className={`point-btn ${market.points === points ? 'active' : ''}`}
                      onClick={() => onUpdateMarket({ points })}
                    >
                      {points}
                    </button>
                  ))}
                </div>
                {market.points > 0 && (
                  <div className="points-details">
                    <div className="points-detail-row">
                      <span>Upfront Cost</span>
                      <span className="cost">{formatCurrency(loanAmount * market.points / 100)}</span>
                    </div>
                    <div className="points-detail-row">
                      <span>Rate Reduction</span>
                      <span className="savings">-{(market.points * market.pointsDiscount).toFixed(3)}%</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Loan Summary */}
            <div className="loan-summary-card">
              <div className="summary-row">
                <span>Home Price</span>
                <span>{formatCurrency(property.homePrice)}</span>
              </div>
              <div className="summary-row">
                <span>Down Payment ({property.downPaymentPct}%)</span>
                <span>{formatCurrency(property.homePrice * property.downPaymentPct / 100)}</span>
              </div>
              <div className="summary-row">
                <span>Loan Amount</span>
                <span>{formatCurrency(loanAmount)}</span>
              </div>
              <div className="summary-row">
                <span>Loan Program</span>
                <span style={{ textTransform: 'uppercase' }}>{market.loanProgram || 'Conventional'}</span>
              </div>
              <div className="summary-row">
                <span>Interest Rate</span>
                <span>{effectiveInterestRate.toFixed(3)}%</span>
              </div>
              <div className="summary-row">
                <span>Term</span>
                <span>{market.termYears} years</span>
              </div>
              <div className="summary-row highlight">
                <span>Est. Monthly P&I</span>
                <span>{formatCurrency(monthlyPI)}</span>
              </div>
            </div>
          </div>
        )}

        {/* BUDGET TAB */}
        {activeTab === 'budget' && (
          <div className="tab-panel budget-panel">
            <div className="budget-header-card">
              <div className="budget-income">
                <span className="budget-income-label">Monthly Income</span>
                <span className="budget-income-value">{formatCurrency(profile.annualIncome / 12)}</span>
              </div>
              <div className="budget-available">
                <span className="budget-available-label">Available for Housing</span>
                <span className={`budget-available-value ${
                  (profile.annualIncome / 12) -
                  Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) -
                  profile.monthlyDebts > 0 ? 'positive' : 'negative'
                }`}>
                  {formatCurrency(
                    (profile.annualIncome / 12) -
                    Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) -
                    profile.monthlyDebts
                  )}
                </span>
              </div>
            </div>

            <div className="panel-section">
              <h3 className="panel-section-title">Monthly Expenses</h3>
              <div className="budget-items-modern">
                {Object.entries(profile.budget || {}).map(([key, value]) => (
                  <div key={key} className="budget-item-modern">
                    <label>{key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')}</label>
                    <div className="input-with-prefix compact">
                      <span className="prefix">$</span>
                      <input
                        type="number"
                        value={value}
                        onChange={(e) => onUpdateProfile({
                          budget: { ...profile.budget, [key]: parseFloat(e.target.value) || 0 }
                        })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="budget-breakdown-card">
              <div className="breakdown-bar">
                <div
                  className="bar-segment expenses"
                  style={{
                    width: `${Math.min((Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) / (profile.annualIncome / 12)) * 100, 100)}%`
                  }}
                />
                <div
                  className="bar-segment debts"
                  style={{
                    width: `${Math.min((profile.monthlyDebts / (profile.annualIncome / 12)) * 100, 100)}%`
                  }}
                />
              </div>
              <div className="breakdown-legend">
                <div className="legend-item">
                  <span className="legend-color expenses"></span>
                  <span>Expenses: {formatCurrency(Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0))}</span>
                </div>
                <div className="legend-item">
                  <span className="legend-color debts"></span>
                  <span>Debts: {formatCurrency(profile.monthlyDebts)}</span>
                </div>
                <div className="legend-item">
                  <span className="legend-color available"></span>
                  <span>Available: {formatCurrency(
                    (profile.annualIncome / 12) -
                    Object.values(profile.budget || {}).reduce((sum, val) => sum + val, 0) -
                    profile.monthlyDebts
                  )}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SCENARIOS TAB */}
        {activeTab === 'scenarios' && (
          <div className="tab-panel scenarios-panel">
            <div className="panel-section">
              <h3 className="panel-section-title">Price Point Scenarios</h3>
              <p className="section-description">
                Compare different home prices and see how they affect your monthly payment
              </p>
            </div>

            <div className="scenario-cards">
              {Object.entries(property.homePrices || {}).map(([key, value]) => {
                const scenarioLoan = value * (1 - property.downPaymentPct / 100);
                const r = effectiveInterestRate / 100 / 12;
                const n = market.termYears * 12;
                const scenarioPI = r === 0
                  ? scenarioLoan / n
                  : scenarioLoan * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
                const isActive = property.homePrice === value;

                return (
                  <div
                    key={key}
                    className={`scenario-card ${isActive ? 'active' : ''}`}
                    onClick={() => onUpdateProperty({ homePrice: value })}
                  >
                    {isActive && <div className="active-badge">Current</div>}
                    <div className="scenario-label">{key.charAt(0).toUpperCase() + key.slice(1)}</div>
                    <div className="scenario-price">
                      <div className="input-with-prefix" onClick={(e) => e.stopPropagation()}>
                        <span className="prefix">$</span>
                        <input
                          type="number"
                          value={value}
                          onChange={(e) => onUpdateProperty({
                            homePrices: { ...property.homePrices, [key]: parseFloat(e.target.value) || 0 }
                          })}
                        />
                      </div>
                    </div>
                    <div className="scenario-details">
                      <div className="scenario-detail">
                        <span className="detail-label">Down</span>
                        <span className="detail-value">{formatCurrency(value * property.downPaymentPct / 100)}</span>
                      </div>
                      <div className="scenario-detail">
                        <span className="detail-label">Loan</span>
                        <span className="detail-value">{formatCurrency(scenarioLoan)}</span>
                      </div>
                      <div className="scenario-detail highlight">
                        <span className="detail-label">Est. P&I</span>
                        <span className="detail-value">{formatCurrency(scenarioPI)}/mo</span>
                      </div>
                    </div>
                    {!isActive && (
                      <button className="use-scenario-btn">
                        Use This Price
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="client-data-footer">
        <span>Changes apply instantly to all calculator views</span>
      </div>
    </div>
  );
};

export default ClientDataView;
