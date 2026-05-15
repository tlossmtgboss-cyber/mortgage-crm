/**
 * Calculator Result Card Component
 *
 * Displays individual calculator result with:
 * - Type-specific visualization (PITI bar, DTI gauge, etc.)
 * - Confidence indicator
 * - Input/output details
 * - Share and approval actions
 */

import React, { useState } from 'react';

// Format currency
const formatCurrency = (value) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
};

// Format percentage
const formatPercent = (value, decimals = 1) => {
  if (value === null || value === undefined) return '-';
  return `${Number(value).toFixed(decimals)}%`;
};

// Get confidence badge style
const getConfidenceBadge = (confidence) => {
  if (confidence >= 85) return { class: 'high', label: 'High Confidence' };
  if (confidence >= 70) return { class: 'medium', label: 'Medium Confidence' };
  return { class: 'low', label: 'Low Confidence' };
};

// PITI Visualization - Stacked bar chart
const PITIVisualization = ({ outputs }) => {
  const components = [
    { key: 'principal_interest', label: 'P&I', color: '#3b82f6' },
    { key: 'property_taxes', label: 'Taxes', color: '#2D7A52' },
    { key: 'homeowners_insurance', label: 'Insurance', color: '#f59e0b' },
    { key: 'mortgage_insurance', label: 'PMI', color: '#ef4444' },
    { key: 'hoa', label: 'HOA', color: '#B8924A' },
  ].filter((c) => outputs[c.key] > 0);

  const total = outputs.total_payment || 0;

  return (
    <div className="piti-visualization">
      <div className="piti-total">
        <span className="total-label">Total Monthly Payment</span>
        <span className="total-value">{formatCurrency(total)}</span>
      </div>
      <div className="piti-bar">
        {components.map((comp) => {
          const value = outputs[comp.key] || 0;
          const percent = total > 0 ? (value / total) * 100 : 0;
          return (
            <div
              key={comp.key}
              className="piti-segment"
              style={{
                width: `${percent}%`,
                backgroundColor: comp.color,
              }}
              title={`${comp.label}: ${formatCurrency(value)}`}
            />
          );
        })}
      </div>
      <div className="piti-legend">
        {components.map((comp) => (
          <div key={comp.key} className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: comp.color }} />
            <span className="legend-label">{comp.label}</span>
            <span className="legend-value">{formatCurrency(outputs[comp.key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// DTI Visualization - Gauge meter
const DTIVisualization = ({ outputs }) => {
  const backEnd = outputs.back_end_ratio || 0;
  const frontEnd = outputs.front_end_ratio || 0;
  const threshold = 43;

  const getColor = (value) => {
    if (value <= 36) return '#22c55e';
    if (value <= 43) return '#eab308';
    return '#ef4444';
  };

  return (
    <div className="dti-visualization">
      <div className="dti-gauge-container">
        <div className="dti-gauge">
          <div
            className="dti-gauge-fill"
            style={{
              width: `${Math.min((backEnd / 50) * 100, 100)}%`,
              backgroundColor: getColor(backEnd),
            }}
          />
          <div className="dti-threshold-marker" style={{ left: `${(threshold / 50) * 100}%` }} />
        </div>
        <div className="dti-value" style={{ color: getColor(backEnd) }}>
          {formatPercent(backEnd)}
        </div>
      </div>
      <div className="dti-details">
        <div className="dti-row">
          <span>Front-End (Housing)</span>
          <span>{formatPercent(frontEnd)}</span>
        </div>
        <div className="dti-row">
          <span>Back-End (Total)</span>
          <span style={{ color: getColor(backEnd), fontWeight: 600 }}>{formatPercent(backEnd)}</span>
        </div>
        <div className="dti-threshold">
          <span>QM Threshold: 43%</span>
          {backEnd <= 43 ? (
            <span className="status-ok">Within limits</span>
          ) : (
            <span className="status-warning">Over threshold</span>
          )}
        </div>
      </div>
    </div>
  );
};

// LTV Visualization - Progress bar with threshold
const LTVVisualization = ({ outputs }) => {
  const ltv = outputs.ltv || 0;
  const requiresPMI = outputs.requires_pmi || ltv > 80;

  const getColor = (value) => {
    if (value <= 80) return '#22c55e';
    if (value <= 95) return '#eab308';
    return '#ef4444';
  };

  return (
    <div className="ltv-visualization">
      <div className="ltv-value" style={{ color: getColor(ltv) }}>
        {formatPercent(ltv)}
      </div>
      <div className="ltv-bar-container">
        <div
          className="ltv-bar-fill"
          style={{
            width: `${Math.min(ltv, 100)}%`,
            backgroundColor: getColor(ltv),
          }}
        />
        <div className="ltv-threshold-marker" style={{ left: '80%' }}>
          <span className="threshold-label">80%</span>
        </div>
      </div>
      <div className="ltv-status">
        {requiresPMI ? (
          <span className="pmi-required">PMI Required</span>
        ) : (
          <span className="no-pmi">No PMI Required</span>
        )}
      </div>
      {outputs.cltv && outputs.cltv !== ltv && (
        <div className="cltv-note">Combined LTV: {formatPercent(outputs.cltv)}</div>
      )}
    </div>
  );
};

// Affordability Visualization
const AffordabilityVisualization = ({ outputs }) => (
  <div className="affordability-visualization">
    <div className="affordability-main">
      <span className="affordability-label">Maximum Purchase Price</span>
      <span className="affordability-value">{formatCurrency(outputs.max_purchase_price)}</span>
    </div>
    <div className="affordability-details">
      <div className="detail-row">
        <span>Max Monthly Payment</span>
        <span>{formatCurrency(outputs.max_monthly_payment)}</span>
      </div>
      <div className="detail-row">
        <span>Max Loan Amount</span>
        <span>{formatCurrency(outputs.max_loan_amount)}</span>
      </div>
      {outputs.down_payment && (
        <div className="detail-row">
          <span>Required Down Payment</span>
          <span>{formatCurrency(outputs.down_payment)}</span>
        </div>
      )}
    </div>
  </div>
);

// Closing Costs Visualization
const ClosingCostsVisualization = ({ outputs }) => {
  const categories = [
    { key: 'lender_fees', label: 'Lender Fees' },
    { key: 'third_party_fees', label: 'Third Party Fees' },
    { key: 'prepaids', label: 'Prepaids' },
    { key: 'escrow_reserves', label: 'Escrow Reserves' },
    { key: 'title_fees', label: 'Title Fees' },
  ].filter((c) => outputs[c.key]);

  return (
    <div className="closing-costs-visualization">
      <div className="closing-total">
        <span className="total-label">Total Estimated Closing Costs</span>
        <span className="total-value">{formatCurrency(outputs.total_estimated)}</span>
      </div>
      <div className="closing-breakdown">
        {categories.map((cat) => (
          <div key={cat.key} className="closing-row">
            <span>{cat.label}</span>
            <span>{formatCurrency(outputs[cat.key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// Amortization Visualization - First 6 payments table
const AmortizationVisualization = ({ outputs }) => {
  const schedule = (outputs.schedule || []).slice(0, 6);

  return (
    <div className="amortization-visualization">
      <div className="amortization-summary">
        <div className="summary-item">
          <span className="item-label">Total Interest</span>
          <span className="item-value">{formatCurrency(outputs.total_interest)}</span>
        </div>
        <div className="summary-item">
          <span className="item-label">Total Cost</span>
          <span className="item-value">{formatCurrency(outputs.total_cost)}</span>
        </div>
      </div>
      {schedule.length > 0 && (
        <table className="amortization-table">
          <thead>
            <tr>
              <th>Month</th>
              <th>Principal</th>
              <th>Interest</th>
              <th>Balance</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((payment, index) => (
              <tr key={index}>
                <td>{payment.month}</td>
                <td>{formatCurrency(payment.principal)}</td>
                <td>{formatCurrency(payment.interest)}</td>
                <td>{formatCurrency(payment.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

// Generic Key-Value Visualization
const GenericVisualization = ({ outputs }) => (
  <div className="generic-visualization">
    {Object.entries(outputs).map(([key, value]) => (
      <div key={key} className="generic-row">
        <span className="generic-label">
          {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
        </span>
        <span className="generic-value">
          {typeof value === 'number'
            ? value > 100
              ? formatCurrency(value)
              : formatPercent(value)
            : String(value)}
        </span>
      </div>
    ))}
  </div>
);

const CalculatorResultCard = ({
  result,
  config,
  isExpanded,
  onToggleExpand,
  onShare,
  onApprove,
  onReject,
}) => {
  const [showInputs, setShowInputs] = useState(false);

  const content = result.content || result.structured_data || {};
  const calculatorType = content.calculator_type || 'generic';
  const outputs = content.outputs || content;
  const inputs = content.inputs || {};
  const evidence = content.evidence || result.source_text;
  const confidence = result.confidence_score || content.confidence || 80;

  const confidenceBadge = getConfidenceBadge(confidence);
  const isPending = result.approval_status === 'pending';

  // Get visualization component based on calculator type
  const renderVisualization = () => {
    switch (calculatorType) {
      case 'piti':
        return <PITIVisualization outputs={outputs} />;
      case 'dti':
        return <DTIVisualization outputs={outputs} />;
      case 'ltv':
        return <LTVVisualization outputs={outputs} />;
      case 'affordability':
        return <AffordabilityVisualization outputs={outputs} />;
      case 'closing_costs':
        return <ClosingCostsVisualization outputs={outputs} />;
      case 'amortization':
        return <AmortizationVisualization outputs={outputs} />;
      default:
        return <GenericVisualization outputs={outputs} />;
    }
  };

  // Get primary result for card header
  const getPrimaryResult = () => {
    switch (calculatorType) {
      case 'piti':
        return formatCurrency(outputs.total_payment);
      case 'dti':
        return `${formatPercent(outputs.front_end_ratio)} / ${formatPercent(outputs.back_end_ratio)}`;
      case 'ltv':
        return formatPercent(outputs.ltv);
      case 'affordability':
        return formatCurrency(outputs.max_purchase_price);
      case 'closing_costs':
        return formatCurrency(outputs.total_estimated);
      case 'amortization':
        return formatCurrency(outputs.total_interest);
      default:
        return 'View Details';
    }
  };

  return (
    <div className={`calculator-result-card ${isPending ? 'pending' : ''} ${isExpanded ? 'expanded' : ''}`}>
      {/* Card Header */}
      <div className="card-header" onClick={onToggleExpand}>
        <div className="header-left">
          <span className="card-icon" style={{ color: config.color }}>
            {config.icon}
          </span>
          <div className="header-info">
            <span className="card-title">{config.label}</span>
            <span className="card-result">{getPrimaryResult()}</span>
          </div>
        </div>
        <div className="header-right">
          <span className={`confidence-badge ${confidenceBadge.class}`}>
            {confidenceBadge.label}
          </span>
          <button className="expand-btn" aria-label={isExpanded ? 'Collapse' : 'Expand'}>
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              style={{ transform: isExpanded ? 'rotate(180deg)' : 'none' }}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="card-content">
          {/* Visualization */}
          <div className="visualization-container">{renderVisualization()}</div>

          {/* Inputs Section */}
          {Object.keys(inputs).length > 0 && (
            <div className="inputs-section">
              <button
                className="inputs-toggle"
                onClick={() => setShowInputs(!showInputs)}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{ transform: showInputs ? 'rotate(90deg)' : 'none' }}
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
                Calculation Inputs
              </button>
              {showInputs && (
                <div className="inputs-content">
                  {Object.entries(inputs).map(([key, value]) => (
                    <div key={key} className="input-row">
                      <span className="input-label">
                        {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                      </span>
                      <span className="input-value">
                        {typeof value === 'number'
                          ? value > 100
                            ? formatCurrency(value)
                            : value < 1
                            ? formatPercent(value * 100)
                            : String(value)
                          : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Evidence Quote */}
          {evidence && (
            <div className="evidence-section">
              <span className="evidence-label">From Transcript:</span>
              <blockquote className="evidence-quote">"{evidence}"</blockquote>
            </div>
          )}

          {/* Action Buttons */}
          <div className="card-actions">
            {onShare && (
              <button className="action-btn share-btn" onClick={() => onShare(result)}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="18" cy="5" r="3" />
                  <circle cx="6" cy="12" r="3" />
                  <circle cx="18" cy="19" r="3" />
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                </svg>
                Share
              </button>
            )}

            {isPending && (
              <>
                {onApprove && (
                  <button
                    className="action-btn approve-btn"
                    onClick={() => onApprove([result.id])}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Approve
                  </button>
                )}
                {onReject && (
                  <button
                    className="action-btn reject-btn"
                    onClick={() => onReject([result.id])}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                    Reject
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default CalculatorResultCard;
