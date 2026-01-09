import React, { useState, useEffect } from 'react';
import { decisionLabAPI } from '../../services/decisionLabApi';
import './ScenarioBuilder.css';

const PROPERTY_TYPES = [
  { value: 'single_family', label: 'Single Family Home' },
  { value: 'condo', label: 'Condominium' },
  { value: 'townhouse', label: 'Townhouse' },
  { value: 'multi_family', label: 'Multi-Family (2-4 units)' },
];

const OCCUPANCY_TYPES = [
  { value: 'primary', label: 'Primary Residence' },
  { value: 'second_home', label: 'Second Home' },
  { value: 'investment', label: 'Investment Property' },
];

const LOAN_PURPOSES = [
  { value: 'purchase', label: 'Purchase' },
  { value: 'refinance', label: 'Refinance' },
  { value: 'cash_out', label: 'Cash-Out Refinance' },
];

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

function ScenarioBuilder({
  sessionId,
  onScenarioCreated,
  onBack,
  existingScenarios = [],
  selectedScenarios = [],
  onSelectScenario,
  onCompare,
}) {
  const [scenarios, setScenarios] = useState(existingScenarios);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(existingScenarios.length === 0);
  const [activeScenario, setActiveScenario] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    purchase_price: '',
    down_payment: '',
    credit_score: '720',
    property_type: 'single_family',
    occupancy: 'primary',
    loan_purpose: 'purchase',
    state: 'CA',
    is_veteran: false,
    is_first_time_buyer: true,
  });

  // Calculated values
  const [calculations, setCalculations] = useState({
    loan_amount: 0,
    down_payment_percent: 0,
    ltv: 0,
  });

  // Fetch existing scenarios
  useEffect(() => {
    if (sessionId && existingScenarios.length === 0) {
      fetchScenarios();
    }
  }, [sessionId]);

  const fetchScenarios = async () => {
    try {
      const data = await decisionLabAPI.getScenarios(sessionId);
      setScenarios(data.scenarios || []);
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
    }
  };

  // Update calculations when form changes
  useEffect(() => {
    const purchasePrice = parseFloat(formData.purchase_price) || 0;
    const downPayment = parseFloat(formData.down_payment) || 0;

    if (purchasePrice > 0) {
      const loanAmount = purchasePrice - downPayment;
      const downPaymentPercent = (downPayment / purchasePrice) * 100;
      const ltv = ((purchasePrice - downPayment) / purchasePrice) * 100;

      setCalculations({
        loan_amount: loanAmount,
        down_payment_percent: downPaymentPercent,
        ltv: ltv,
      });
    }
  }, [formData.purchase_price, formData.down_payment]);

  // Handle form changes
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  // Handle numeric input with formatting
  const handleCurrencyChange = (e) => {
    const { name, value } = e.target;
    // Remove non-numeric characters except decimal
    const numericValue = value.replace(/[^0-9.]/g, '');
    setFormData(prev => ({
      ...prev,
      [name]: numericValue,
    }));
  };

  // Quick down payment presets
  const setDownPaymentPercent = (percent) => {
    const purchasePrice = parseFloat(formData.purchase_price) || 0;
    if (purchasePrice > 0) {
      setFormData(prev => ({
        ...prev,
        down_payment: String(Math.round(purchasePrice * (percent / 100))),
      }));
    }
  };

  // Create scenario
  const handleCreateScenario = async (e) => {
    e.preventDefault();

    if (!formData.purchase_price || parseFloat(formData.purchase_price) <= 0) {
      setError('Please enter a purchase price');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const scenarioData = {
        name: formData.name || `Scenario ${scenarios.length + 1}`,
        purchase_price: parseFloat(formData.purchase_price),
        down_payment: parseFloat(formData.down_payment) || 0,
        loan_amount: calculations.loan_amount,
        credit_score: parseInt(formData.credit_score),
        property_type: formData.property_type,
        occupancy: formData.occupancy,
        loan_purpose: formData.loan_purpose,
        state: formData.state,
        is_veteran: formData.is_veteran,
        is_first_time_buyer: formData.is_first_time_buyer,
      };

      const result = await decisionLabAPI.createScenario(sessionId, scenarioData);
      const scenarioId = result.scenario?.scenario_id || result.scenario_id;

      // Calculate loan options
      setCalculating(true);
      const options = await decisionLabAPI.calculateLoanOptions(scenarioId);

      const newScenario = {
        ...result.scenario,
        ...scenarioData,
        id: scenarioId,
        scenario_id: scenarioId,
        loan_options: options.options || options.loan_options || [],
      };

      setScenarios(prev => [...prev, newScenario]);
      setActiveScenario(newScenario);
      setShowForm(false);
      onScenarioCreated(newScenario);

      // Reset form
      setFormData({
        name: '',
        purchase_price: '',
        down_payment: '',
        credit_score: '720',
        property_type: 'single_family',
        occupancy: 'primary',
        loan_purpose: 'purchase',
        state: 'CA',
        is_veteran: false,
        is_first_time_buyer: true,
      });
    } catch (err) {
      setError('Failed to create scenario. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
      setCalculating(false);
    }
  };

  // View scenario details
  const handleViewScenario = (scenario) => {
    setActiveScenario(scenario);
    setShowForm(false);
  };

  // Render loan option card
  const renderLoanOption = (option, index) => {
    const isRecommended = index === 0;

    return (
      <div key={option.id || index} className={`loan-option-card ${isRecommended ? 'recommended' : ''}`}>
        {isRecommended && <div className="recommended-badge">Recommended</div>}
        <div className="option-header">
          <h4 className="option-type">{option.product_type}</h4>
          <span className="option-term">{option.term_years || 30} Years</span>
        </div>
        <div className="option-rate">
          <span className="rate-value">{option.interest_rate?.toFixed(3)}%</span>
          <span className="rate-label">Interest Rate</span>
        </div>
        <div className="option-payment">
          <span className="payment-value">{formatCurrency(option.monthly_payment)}</span>
          <span className="payment-label">Monthly Payment</span>
        </div>
        <div className="option-breakdown">
          <div className="breakdown-item">
            <span>Principal & Interest</span>
            <span>{formatCurrency(option.principal_interest)}</span>
          </div>
          <div className="breakdown-item">
            <span>Property Tax</span>
            <span>{formatCurrency(option.property_tax)}</span>
          </div>
          <div className="breakdown-item">
            <span>Insurance</span>
            <span>{formatCurrency(option.insurance)}</span>
          </div>
          {option.pmi > 0 && (
            <div className="breakdown-item">
              <span>PMI/MIP</span>
              <span>{formatCurrency(option.pmi)}</span>
            </div>
          )}
        </div>
        <div className="option-details">
          <div className="detail-item">
            <span className="detail-label">APR</span>
            <span className="detail-value">{option.apr?.toFixed(3)}%</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Closing Costs</span>
            <span className="detail-value">{formatCurrency(option.closing_costs)}</span>
          </div>
        </div>
        {option.pros && option.pros.length > 0 && (
          <div className="option-pros">
            <span className="pros-label">Pros:</span>
            <ul>
              {option.pros.map((pro, i) => (
                <li key={i}>{pro}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="scenario-builder">
      <div className="builder-header">
        <button className="back-link" onClick={onBack}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back to Results
        </button>
        <h2>Loan Scenario Builder</h2>
        <p>Create and compare different loan scenarios to find your best option</p>
      </div>

      {error && (
        <div className="error-message">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {error}
        </div>
      )}

      <div className="builder-content">
        {/* Scenarios List */}
        {scenarios.length > 0 && (
          <div className="scenarios-sidebar">
            <div className="sidebar-header">
              <h3>Your Scenarios</h3>
              <button className="add-scenario-btn" onClick={() => { setShowForm(true); setActiveScenario(null); }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 4v16m8-8H4" />
                </svg>
              </button>
            </div>
            <div className="scenarios-list">
              {scenarios.map((scenario, index) => (
                <div
                  key={scenario.scenario_id || index}
                  className={`scenario-item ${activeScenario?.scenario_id === scenario.scenario_id ? 'active' : ''} ${selectedScenarios.includes(scenario.scenario_id) ? 'selected' : ''}`}
                >
                  <div className="scenario-item-content" onClick={() => handleViewScenario(scenario)}>
                    <h4>{scenario.name || `Scenario ${index + 1}`}</h4>
                    <p>{formatCurrency(scenario.purchase_price)}</p>
                    <span className="scenario-ltv">{(100 - (scenario.down_payment / scenario.purchase_price * 100)).toFixed(0)}% LTV</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={selectedScenarios.includes(scenario.scenario_id)}
                    onChange={() => onSelectScenario(scenario.scenario_id)}
                    title="Select for comparison"
                  />
                </div>
              ))}
            </div>
            {selectedScenarios.length >= 2 && (
              <button className="compare-button" onClick={onCompare}>
                Compare {selectedScenarios.length} Scenarios
              </button>
            )}
          </div>
        )}

        {/* Main Content */}
        <div className="main-content">
          {showForm ? (
            <form className="scenario-form" onSubmit={handleCreateScenario}>
              <h3>Create New Scenario</h3>

              <div className="form-section">
                <div className="form-group">
                  <label htmlFor="name">Scenario Name (optional)</label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    placeholder="e.g., Dream Home, Starter Condo"
                  />
                </div>
              </div>

              <div className="form-section">
                <h4>Property Details</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="purchase_price">Purchase Price *</label>
                    <div className="currency-input">
                      <span className="currency-symbol">$</span>
                      <input
                        type="text"
                        id="purchase_price"
                        name="purchase_price"
                        value={formData.purchase_price}
                        onChange={handleCurrencyChange}
                        placeholder="450,000"
                      />
                    </div>
                  </div>
                  <div className="form-group">
                    <label htmlFor="down_payment">Down Payment</label>
                    <div className="currency-input">
                      <span className="currency-symbol">$</span>
                      <input
                        type="text"
                        id="down_payment"
                        name="down_payment"
                        value={formData.down_payment}
                        onChange={handleCurrencyChange}
                        placeholder="90,000"
                      />
                    </div>
                    <div className="quick-presets">
                      <button type="button" onClick={() => setDownPaymentPercent(3)}>3%</button>
                      <button type="button" onClick={() => setDownPaymentPercent(5)}>5%</button>
                      <button type="button" onClick={() => setDownPaymentPercent(10)}>10%</button>
                      <button type="button" onClick={() => setDownPaymentPercent(20)}>20%</button>
                    </div>
                  </div>
                </div>

                {calculations.loan_amount > 0 && (
                  <div className="calculated-values">
                    <div className="calc-item">
                      <span className="calc-label">Loan Amount</span>
                      <span className="calc-value">{formatCurrency(calculations.loan_amount)}</span>
                    </div>
                    <div className="calc-item">
                      <span className="calc-label">Down Payment</span>
                      <span className="calc-value">{calculations.down_payment_percent.toFixed(1)}%</span>
                    </div>
                    <div className="calc-item">
                      <span className="calc-label">LTV</span>
                      <span className={`calc-value ${calculations.ltv > 80 ? 'warning' : ''}`}>
                        {calculations.ltv.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                )}

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="property_type">Property Type</label>
                    <select
                      id="property_type"
                      name="property_type"
                      value={formData.property_type}
                      onChange={handleChange}
                    >
                      {PROPERTY_TYPES.map(type => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="occupancy">Occupancy</label>
                    <select
                      id="occupancy"
                      name="occupancy"
                      value={formData.occupancy}
                      onChange={handleChange}
                    >
                      {OCCUPANCY_TYPES.map(type => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="loan_purpose">Loan Purpose</label>
                    <select
                      id="loan_purpose"
                      name="loan_purpose"
                      value={formData.loan_purpose}
                      onChange={handleChange}
                    >
                      {LOAN_PURPOSES.map(type => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="state">State</label>
                    <select
                      id="state"
                      name="state"
                      value={formData.state}
                      onChange={handleChange}
                    >
                      {US_STATES.map(state => (
                        <option key={state} value={state}>{state}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="form-section">
                <h4>Borrower Profile</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="credit_score">Credit Score</label>
                    <select
                      id="credit_score"
                      name="credit_score"
                      value={formData.credit_score}
                      onChange={handleChange}
                    >
                      <option value="580">580-619 (Fair)</option>
                      <option value="620">620-659 (Good)</option>
                      <option value="660">660-699 (Good)</option>
                      <option value="700">700-739 (Very Good)</option>
                      <option value="720">720-759 (Very Good)</option>
                      <option value="760">760-799 (Excellent)</option>
                      <option value="800">800+ (Exceptional)</option>
                    </select>
                  </div>
                </div>
                <div className="checkbox-row">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      name="is_veteran"
                      checked={formData.is_veteran}
                      onChange={handleChange}
                    />
                    <span>Veteran or Active Military</span>
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      name="is_first_time_buyer"
                      checked={formData.is_first_time_buyer}
                      onChange={handleChange}
                    />
                    <span>First-time Homebuyer</span>
                  </label>
                </div>
              </div>

              <div className="form-actions">
                {scenarios.length > 0 && (
                  <button type="button" className="cancel-btn" onClick={() => setShowForm(false)}>
                    Cancel
                  </button>
                )}
                <button type="submit" className="submit-btn" disabled={loading || calculating}>
                  {loading ? 'Creating...' : calculating ? 'Calculating Options...' : 'Calculate Loan Options'}
                </button>
              </div>
            </form>
          ) : activeScenario ? (
            <div className="scenario-details">
              <div className="details-header">
                <h3>{activeScenario.name || 'Scenario Details'}</h3>
                <div className="scenario-summary">
                  <span>{formatCurrency(activeScenario.purchase_price)} Purchase</span>
                  <span>{formatCurrency(activeScenario.down_payment)} Down ({(activeScenario.down_payment / activeScenario.purchase_price * 100).toFixed(0)}%)</span>
                  <span>{activeScenario.credit_score} Credit</span>
                </div>
              </div>

              <div className="loan-options-grid">
                {activeScenario.loan_options?.map((option, index) => renderLoanOption(option, index))}
              </div>

              {(!activeScenario.loan_options || activeScenario.loan_options.length === 0) && (
                <div className="no-options">
                  <p>No loan options available for this scenario.</p>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                </svg>
              </div>
              <h3>Select a Scenario</h3>
              <p>Choose a scenario from the list to view its loan options, or create a new one.</p>
              <button className="create-btn" onClick={() => setShowForm(true)}>
                Create New Scenario
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ScenarioBuilder;
