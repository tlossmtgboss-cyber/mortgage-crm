/**
 * SharedCalculator Page
 *
 * Public page for viewing shared calculator results (no auth required).
 * Accessed via share links generated from Call Intelligence.
 */

import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { callMonitoringAPI } from '../services/api';
import './SharedCalculator.css';

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

// Calculator type configuration
const CALCULATOR_CONFIG = {
  piti: {
    title: 'Monthly Payment Calculator',
    icon: '🏠',
    color: '#3b82f6',
  },
  dti: {
    title: 'Debt-to-Income Calculator',
    icon: '📊',
    color: '#B8924A',
  },
  ltv: {
    title: 'Loan-to-Value Calculator',
    icon: '📈',
    color: '#2D7A52',
  },
  affordability: {
    title: 'Affordability Calculator',
    icon: '💰',
    color: '#f59e0b',
  },
  closing_costs: {
    title: 'Closing Costs Estimate',
    icon: '📋',
    color: '#ec4899',
  },
  amortization: {
    title: 'Amortization Schedule',
    icon: '📅',
    color: '#06b6d4',
  },
};

// PITI Visualization
const PITIVisualization = ({ outputs }) => {
  const components = [
    { key: 'principal_interest', label: 'Principal & Interest', color: '#3b82f6' },
    { key: 'property_taxes', label: 'Property Taxes', color: '#2D7A52' },
    { key: 'homeowners_insurance', label: 'Homeowners Insurance', color: '#f59e0b' },
    { key: 'mortgage_insurance', label: 'Mortgage Insurance (PMI)', color: '#ef4444' },
    { key: 'hoa', label: 'HOA Dues', color: '#B8924A' },
  ].filter((c) => outputs[c.key] > 0);

  const total = outputs.total_payment || 0;

  return (
    <div className="shared-piti">
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
      <div className="piti-breakdown">
        {components.map((comp) => (
          <div key={comp.key} className="breakdown-item">
            <span className="item-dot" style={{ backgroundColor: comp.color }} />
            <span className="item-label">{comp.label}</span>
            <span className="item-value">{formatCurrency(outputs[comp.key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// DTI Visualization
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
    <div className="shared-dti">
      <div className="dti-main">
        <div className="dti-value" style={{ color: getColor(backEnd) }}>
          {formatPercent(backEnd)}
        </div>
        <div className="dti-label">Back-End DTI</div>
      </div>
      <div className="dti-gauge">
        <div
          className="gauge-fill"
          style={{
            width: `${Math.min((backEnd / 50) * 100, 100)}%`,
            backgroundColor: getColor(backEnd),
          }}
        />
        <div className="gauge-threshold" style={{ left: `${(threshold / 50) * 100}%` }}>
          <span className="threshold-line" />
          <span className="threshold-label">43% QM Limit</span>
        </div>
      </div>
      <div className="dti-details">
        <div className="detail-row">
          <span>Front-End (Housing Only)</span>
          <span>{formatPercent(frontEnd)}</span>
        </div>
        <div className="detail-row">
          <span>Back-End (Total Debt)</span>
          <span style={{ fontWeight: 600 }}>{formatPercent(backEnd)}</span>
        </div>
        <div className="dti-status">
          {backEnd <= 43 ? (
            <span className="status-pass">Within QM Guidelines</span>
          ) : (
            <span className="status-warn">Above QM Threshold</span>
          )}
        </div>
      </div>
    </div>
  );
};

// LTV Visualization
const LTVVisualization = ({ outputs }) => {
  const ltv = outputs.ltv || 0;
  const requiresPMI = outputs.requires_pmi || ltv > 80;

  const getColor = (value) => {
    if (value <= 80) return '#22c55e';
    if (value <= 95) return '#eab308';
    return '#ef4444';
  };

  return (
    <div className="shared-ltv">
      <div className="ltv-main">
        <div className="ltv-value" style={{ color: getColor(ltv) }}>
          {formatPercent(ltv)}
        </div>
        <div className="ltv-label">Loan-to-Value Ratio</div>
      </div>
      <div className="ltv-bar">
        <div
          className="bar-fill"
          style={{
            width: `${Math.min(ltv, 100)}%`,
            backgroundColor: getColor(ltv),
          }}
        />
        <div className="bar-threshold" style={{ left: '80%' }}>
          <span className="threshold-line" />
          <span className="threshold-label">80% PMI Threshold</span>
        </div>
      </div>
      <div className="ltv-status">
        {requiresPMI ? (
          <div className="pmi-alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Private Mortgage Insurance (PMI) Required
          </div>
        ) : (
          <div className="no-pmi">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            No PMI Required
          </div>
        )}
      </div>
      {outputs.cltv && outputs.cltv !== ltv && (
        <div className="cltv-note">Combined LTV (CLTV): {formatPercent(outputs.cltv)}</div>
      )}
    </div>
  );
};

// Affordability Visualization
const AffordabilityVisualization = ({ outputs }) => (
  <div className="shared-affordability">
    <div className="affordability-main">
      <div className="main-label">Maximum Home Price You Can Afford</div>
      <div className="main-value">{formatCurrency(outputs.max_purchase_price)}</div>
    </div>
    <div className="affordability-breakdown">
      <div className="breakdown-item">
        <span className="item-label">Maximum Loan Amount</span>
        <span className="item-value">{formatCurrency(outputs.max_loan_amount)}</span>
      </div>
      <div className="breakdown-item">
        <span className="item-label">Maximum Monthly Payment</span>
        <span className="item-value">{formatCurrency(outputs.max_monthly_payment)}</span>
      </div>
      {outputs.down_payment && (
        <div className="breakdown-item">
          <span className="item-label">Required Down Payment</span>
          <span className="item-value">{formatCurrency(outputs.down_payment)}</span>
        </div>
      )}
    </div>
  </div>
);

// Closing Costs Visualization
const ClosingCostsVisualization = ({ outputs }) => {
  const costs = outputs.itemized_costs || [];

  return (
    <div className="shared-closing-costs">
      <div className="costs-total">
        <span className="total-label">Estimated Closing Costs</span>
        <span className="total-value">{formatCurrency(outputs.total_estimated)}</span>
      </div>
      {costs.length > 0 && (
        <div className="costs-breakdown">
          {costs.map((cost, index) => (
            <div key={index} className="cost-item">
              <span className="cost-name">{cost.name}</span>
              <span className="cost-amount">{formatCurrency(cost.amount)}</span>
            </div>
          ))}
        </div>
      )}
      {outputs.total_cash_to_close && (
        <div className="cash-to-close">
          <span className="label">Total Cash to Close</span>
          <span className="value">{formatCurrency(outputs.total_cash_to_close)}</span>
        </div>
      )}
    </div>
  );
};

// Amortization Visualization
const AmortizationVisualization = ({ outputs }) => {
  const schedule = outputs.schedule || [];
  const displaySchedule = schedule.slice(0, 12);

  return (
    <div className="shared-amortization">
      <div className="amortization-summary">
        <div className="summary-item">
          <span className="item-label">Total Principal</span>
          <span className="item-value">{formatCurrency(outputs.total_principal)}</span>
        </div>
        <div className="summary-item">
          <span className="item-label">Total Interest</span>
          <span className="item-value">{formatCurrency(outputs.total_interest)}</span>
        </div>
        <div className="summary-item">
          <span className="item-label">Total Payments</span>
          <span className="item-value">{formatCurrency(outputs.total_payments)}</span>
        </div>
      </div>
      {displaySchedule.length > 0 && (
        <div className="amortization-schedule">
          <div className="schedule-header">
            <span>Month</span>
            <span>Payment</span>
            <span>Principal</span>
            <span>Interest</span>
            <span>Balance</span>
          </div>
          {displaySchedule.map((row, index) => (
            <div key={index} className="schedule-row">
              <span>{row.month || index + 1}</span>
              <span>{formatCurrency(row.payment)}</span>
              <span>{formatCurrency(row.principal)}</span>
              <span>{formatCurrency(row.interest)}</span>
              <span>{formatCurrency(row.balance)}</span>
            </div>
          ))}
          {schedule.length > 12 && (
            <div className="schedule-more">
              Showing first 12 months of {schedule.length} total payments
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Inputs Display
const InputsDisplay = ({ inputs, calculatorType }) => {
  const formatInputValue = (key, value) => {
    if (value === null || value === undefined) return '-';
    if (key.includes('rate') || key.includes('percent')) return formatPercent(value);
    if (key.includes('amount') || key.includes('price') || key.includes('income') || key.includes('payment')) {
      return formatCurrency(value);
    }
    if (key.includes('term') || key.includes('months')) return `${value} months`;
    return String(value);
  };

  const formatLabel = (key) => {
    return key
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const inputEntries = Object.entries(inputs || {}).filter(
    ([key]) => !key.startsWith('_') && key !== 'calculator_type'
  );

  if (inputEntries.length === 0) return null;

  return (
    <div className="inputs-section">
      <h4>Calculation Inputs</h4>
      <div className="inputs-grid">
        {inputEntries.map(([key, value]) => (
          <div key={key} className="input-item">
            <span className="input-label">{formatLabel(key)}</span>
            <span className="input-value">{formatInputValue(key, value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// Get visualization component for calculator type
const getVisualization = (calculatorType, outputs) => {
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

// Generic visualization for unknown types
const GenericVisualization = ({ outputs }) => (
  <div className="generic-visualization">
    {Object.entries(outputs || {}).map(([key, value]) => (
      <div key={key} className="generic-item">
        <span className="item-label">
          {key
            .split('_')
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
            .join(' ')}
        </span>
        <span className="item-value">
          {typeof value === 'number' ? formatCurrency(value) : String(value)}
        </span>
      </div>
    ))}
  </div>
);

// Main SharedCalculator Component
const SharedCalculator = () => {
  const { shareToken } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSharedArtifact = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await callMonitoringAPI.getSharedArtifact(shareToken);
        setData(response);
      } catch (err) {
        console.error('Error fetching shared artifact:', err);
        if (err.response?.status === 404) {
          setError('expired');
        } else if (err.response?.status === 410) {
          setError('expired');
        } else {
          setError('error');
        }
      } finally {
        setLoading(false);
      }
    };

    if (shareToken) {
      fetchSharedArtifact();
    }
  }, [shareToken]);

  // Loading state
  if (loading) {
    return (
      <div className="shared-calculator-page">
        <div className="loading-container">
          <div className="spinner" />
          <p>Loading calculator results...</p>
        </div>
      </div>
    );
  }

  // Error states
  if (error === 'expired') {
    return (
      <div className="shared-calculator-page">
        <div className="error-container">
          <div className="error-icon">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h2>Link Expired</h2>
          <p>This calculator result link has expired or is no longer available.</p>
          <p className="subtext">Please contact your loan officer for updated information.</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="shared-calculator-page">
        <div className="error-container">
          <div className="error-icon">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <h2>Unable to Load Results</h2>
          <p>We couldn't load the calculator results. Please try again later.</p>
        </div>
      </div>
    );
  }

  const artifact = data.artifact;
  const content = artifact?.content || artifact?.structured_data || {};
  const calculatorType = content.calculator_type || 'calculator';
  const outputs = content.outputs || content;
  const inputs = content.inputs || {};
  const config = CALCULATOR_CONFIG[calculatorType] || {
    title: 'Calculator Result',
    icon: '📱',
    color: '#6b7280',
  };

  return (
    <div className="shared-calculator-page">
      <div className="shared-calculator-container">
        {/* Header */}
        <div className="calculator-header" style={{ borderColor: config.color }}>
          <div className="header-icon" style={{ backgroundColor: `${config.color}15` }}>
            <span>{config.icon}</span>
          </div>
          <div className="header-content">
            <h1>{data.title || config.title}</h1>
            {data.description && <p className="description">{data.description}</p>}
          </div>
        </div>

        {/* Visualization */}
        <div className="calculator-visualization">{getVisualization(calculatorType, outputs)}</div>

        {/* Inputs */}
        <InputsDisplay inputs={inputs} calculatorType={calculatorType} />

        {/* Footer */}
        <div className="calculator-footer">
          <p className="disclaimer">
            This is an estimate for informational purposes only. Actual rates, payments, and fees may
            vary based on credit, property, and other factors. Contact your loan officer for
            personalized information.
          </p>
          {data.expires_at && (
            <p className="expiration">
              This link expires on {new Date(data.expires_at).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default SharedCalculator;
