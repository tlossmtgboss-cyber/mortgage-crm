import React, { useState, useEffect } from 'react';
import { decisionLabAPI } from '../../services/decisionLabApi';
import './LoanComparison.css';

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatPercent = (value, decimals = 2) => {
  return `${value.toFixed(decimals)}%`;
};

function LoanComparison({ scenarioIds, onBack, onCreateNew }) {
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('Conventional');
  const [viewMode, setViewMode] = useState('cards'); // 'cards' or 'table'

  useEffect(() => {
    if (scenarioIds && scenarioIds.length >= 2) {
      fetchComparison();
    }
  }, [scenarioIds]);

  const fetchComparison = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await decisionLabAPI.compareScenarios(scenarioIds);
      setComparison(data);
    } catch (err) {
      setError('Failed to load comparison. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Get available product types from scenarios
  const getProductTypes = () => {
    if (!comparison?.scenarios) return [];
    const products = new Set();
    comparison.scenarios.forEach(scenario => {
      scenario.loan_options?.forEach(option => {
        products.add(option.product_type);
      });
    });
    return Array.from(products);
  };

  // Get loan option for a scenario by product type
  const getLoanOption = (scenario, productType) => {
    return scenario.loan_options?.find(opt => opt.product_type === productType);
  };

  // Calculate difference between scenarios
  const calculateDifference = (values) => {
    if (!values || values.length < 2) return null;
    const min = Math.min(...values.filter(v => v != null));
    const max = Math.max(...values.filter(v => v != null));
    return max - min;
  };

  // Find the best (lowest) value
  const findBestIndex = (values) => {
    if (!values || values.length < 2) return -1;
    const validValues = values.map((v, i) => ({ value: v, index: i })).filter(item => item.value != null);
    if (validValues.length === 0) return -1;
    const minItem = validValues.reduce((min, item) => item.value < min.value ? item : min);
    return minItem.index;
  };

  if (loading) {
    return (
      <div className="comparison-loading">
        <div className="loading-spinner" />
        <p>Comparing scenarios...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="comparison-error">
        <div className="error-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p>{error}</p>
        <button onClick={fetchComparison}>Try Again</button>
      </div>
    );
  }

  if (!comparison) return null;

  const productTypes = getProductTypes();
  const scenarios = comparison.scenarios || [];

  return (
    <div className="loan-comparison">
      <div className="comparison-header">
        <button className="back-link" onClick={onBack}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back to Scenarios
        </button>
        <h2>Scenario Comparison</h2>
        <p>Compare {scenarios.length} scenarios side by side</p>
      </div>

      {/* Product Type Selector */}
      <div className="product-selector">
        <span className="selector-label">Loan Type:</span>
        <div className="product-tabs">
          {productTypes.map(product => (
            <button
              key={product}
              className={`product-tab ${selectedProduct === product ? 'active' : ''}`}
              onClick={() => setSelectedProduct(product)}
            >
              {product}
            </button>
          ))}
        </div>
        <div className="view-toggle">
          <button
            className={viewMode === 'cards' ? 'active' : ''}
            onClick={() => setViewMode('cards')}
            title="Card view"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
            </svg>
          </button>
          <button
            className={viewMode === 'table' ? 'active' : ''}
            onClick={() => setViewMode('table')}
            title="Table view"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Card View */}
      {viewMode === 'cards' && (
        <div className="comparison-cards">
          {scenarios.map((scenario, index) => {
            const option = getLoanOption(scenario, selectedProduct);
            const monthlyPayments = scenarios.map(s => getLoanOption(s, selectedProduct)?.monthly_payment);
            const isBest = findBestIndex(monthlyPayments) === index;

            return (
              <div key={scenario.scenario_id} className={`comparison-card ${isBest ? 'best' : ''}`}>
                {isBest && (
                  <div className="best-badge">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Lowest Payment
                  </div>
                )}
                <div className="card-header">
                  <h3>{scenario.name}</h3>
                  <span className="scenario-badge">Scenario {index + 1}</span>
                </div>

                <div className="property-info">
                  <div className="info-row">
                    <span>Purchase Price</span>
                    <span>{formatCurrency(scenario.purchase_price)}</span>
                  </div>
                  <div className="info-row">
                    <span>Down Payment</span>
                    <span>{formatCurrency(scenario.down_payment)} ({formatPercent((scenario.down_payment / scenario.purchase_price) * 100, 0)})</span>
                  </div>
                  <div className="info-row">
                    <span>Loan Amount</span>
                    <span>{formatCurrency(scenario.loan_amount)}</span>
                  </div>
                  <div className="info-row">
                    <span>Credit Score</span>
                    <span>{scenario.credit_score}</span>
                  </div>
                </div>

                {option ? (
                  <div className="loan-details">
                    <div className="primary-metric">
                      <span className="metric-value">{formatCurrency(option.monthly_payment)}</span>
                      <span className="metric-label">Monthly Payment</span>
                    </div>

                    <div className="metric-grid">
                      <div className="metric-item">
                        <span className="value">{formatPercent(option.interest_rate, 3)}</span>
                        <span className="label">Rate</span>
                      </div>
                      <div className="metric-item">
                        <span className="value">{formatPercent(option.apr, 3)}</span>
                        <span className="label">APR</span>
                      </div>
                      <div className="metric-item">
                        <span className="value">{formatCurrency(option.closing_costs)}</span>
                        <span className="label">Closing Costs</span>
                      </div>
                    </div>

                    <div className="payment-breakdown">
                      <h4>Payment Breakdown</h4>
                      <div className="breakdown-bar">
                        <div
                          className="bar-segment pi"
                          style={{ width: `${(option.principal_interest / option.monthly_payment) * 100}%` }}
                          title={`P&I: ${formatCurrency(option.principal_interest)}`}
                        />
                        <div
                          className="bar-segment tax"
                          style={{ width: `${(option.property_tax / option.monthly_payment) * 100}%` }}
                          title={`Tax: ${formatCurrency(option.property_tax)}`}
                        />
                        <div
                          className="bar-segment insurance"
                          style={{ width: `${(option.insurance / option.monthly_payment) * 100}%` }}
                          title={`Insurance: ${formatCurrency(option.insurance)}`}
                        />
                        {option.pmi > 0 && (
                          <div
                            className="bar-segment pmi"
                            style={{ width: `${(option.pmi / option.monthly_payment) * 100}%` }}
                            title={`PMI: ${formatCurrency(option.pmi)}`}
                          />
                        )}
                      </div>
                      <div className="breakdown-legend">
                        <span className="legend-item"><span className="dot pi" /> P&I</span>
                        <span className="legend-item"><span className="dot tax" /> Tax</span>
                        <span className="legend-item"><span className="dot insurance" /> Ins</span>
                        {option.pmi > 0 && <span className="legend-item"><span className="dot pmi" /> PMI</span>}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="no-option">
                    <p>{selectedProduct} not available for this scenario</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Table View */}
      {viewMode === 'table' && (
        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Metric</th>
                {scenarios.map((scenario, index) => (
                  <th key={scenario.scenario_id}>
                    {scenario.name || `Scenario ${index + 1}`}
                  </th>
                ))}
                <th>Difference</th>
              </tr>
            </thead>
            <tbody>
              <tr className="section-header">
                <td colSpan={scenarios.length + 2}>Property Details</td>
              </tr>
              <tr>
                <td>Purchase Price</td>
                {scenarios.map(s => <td key={s.scenario_id}>{formatCurrency(s.purchase_price)}</td>)}
                <td className="diff">{formatCurrency(calculateDifference(scenarios.map(s => s.purchase_price)))}</td>
              </tr>
              <tr>
                <td>Down Payment</td>
                {scenarios.map(s => <td key={s.scenario_id}>{formatCurrency(s.down_payment)}</td>)}
                <td className="diff">{formatCurrency(calculateDifference(scenarios.map(s => s.down_payment)))}</td>
              </tr>
              <tr>
                <td>Loan Amount</td>
                {scenarios.map(s => <td key={s.scenario_id}>{formatCurrency(s.loan_amount)}</td>)}
                <td className="diff">{formatCurrency(calculateDifference(scenarios.map(s => s.loan_amount)))}</td>
              </tr>

              <tr className="section-header">
                <td colSpan={scenarios.length + 2}>{selectedProduct} Loan Details</td>
              </tr>
              <tr>
                <td>Interest Rate</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt ? formatPercent(opt.interest_rate, 3) : '-'}</td>;
                })}
                <td className="diff">
                  {formatPercent(calculateDifference(scenarios.map(s => getLoanOption(s, selectedProduct)?.interest_rate)) || 0, 3)}
                </td>
              </tr>
              <tr className="highlight">
                <td>Monthly Payment</td>
                {scenarios.map((s, i) => {
                  const opt = getLoanOption(s, selectedProduct);
                  const payments = scenarios.map(sc => getLoanOption(sc, selectedProduct)?.monthly_payment);
                  const isBest = findBestIndex(payments) === i;
                  return (
                    <td key={s.scenario_id} className={isBest ? 'best' : ''}>
                      {opt ? formatCurrency(opt.monthly_payment) : '-'}
                      {isBest && <span className="best-indicator">Lowest</span>}
                    </td>
                  );
                })}
                <td className="diff">
                  {formatCurrency(calculateDifference(scenarios.map(s => getLoanOption(s, selectedProduct)?.monthly_payment)))}
                </td>
              </tr>
              <tr>
                <td>P&I</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt ? formatCurrency(opt.principal_interest) : '-'}</td>;
                })}
                <td className="diff">-</td>
              </tr>
              <tr>
                <td>Property Tax</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt ? formatCurrency(opt.property_tax) : '-'}</td>;
                })}
                <td className="diff">-</td>
              </tr>
              <tr>
                <td>Insurance</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt ? formatCurrency(opt.insurance) : '-'}</td>;
                })}
                <td className="diff">-</td>
              </tr>
              <tr>
                <td>PMI/MIP</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt?.pmi > 0 ? formatCurrency(opt.pmi) : '-'}</td>;
                })}
                <td className="diff">-</td>
              </tr>
              <tr>
                <td>APR</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt ? formatPercent(opt.apr, 3) : '-'}</td>;
                })}
                <td className="diff">
                  {formatPercent(calculateDifference(scenarios.map(s => getLoanOption(s, selectedProduct)?.apr)) || 0, 3)}
                </td>
              </tr>
              <tr>
                <td>Closing Costs</td>
                {scenarios.map(s => {
                  const opt = getLoanOption(s, selectedProduct);
                  return <td key={s.scenario_id}>{opt ? formatCurrency(opt.closing_costs) : '-'}</td>;
                })}
                <td className="diff">
                  {formatCurrency(calculateDifference(scenarios.map(s => getLoanOption(s, selectedProduct)?.closing_costs)))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      <div className="comparison-summary">
        <h3>Summary</h3>
        <div className="summary-content">
          {scenarios.length > 0 && (() => {
            const payments = scenarios.map(s => ({
              scenario: s,
              payment: getLoanOption(s, selectedProduct)?.monthly_payment || Infinity,
            }));
            const best = payments.reduce((min, curr) => curr.payment < min.payment ? curr : min);
            const paymentDiff = calculateDifference(payments.map(p => p.payment));

            return (
              <>
                <p>
                  <strong>{best.scenario.name}</strong> offers the lowest monthly payment
                  for {selectedProduct} loans at <strong>{formatCurrency(best.payment)}</strong>/month.
                </p>
                {paymentDiff > 0 && (
                  <p>
                    Monthly payment difference between scenarios: <strong>{formatCurrency(paymentDiff)}</strong>
                    ({formatCurrency(paymentDiff * 12)}/year, {formatCurrency(paymentDiff * 360)} over 30 years)
                  </p>
                )}
              </>
            );
          })()}
        </div>
      </div>

      {/* Actions */}
      <div className="comparison-actions">
        <button className="secondary-btn" onClick={onCreateNew}>
          Create Another Scenario
        </button>
        <button className="primary-btn" onClick={() => window.print()}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
          </svg>
          Print Comparison
        </button>
      </div>
    </div>
  );
}

export default LoanComparison;
