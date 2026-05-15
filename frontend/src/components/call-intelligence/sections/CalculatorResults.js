/**
 * Calculator Results Component
 *
 * Displays calculator results extracted from call transcripts including:
 * - PITI calculations
 * - DTI ratios
 * - LTV calculations
 * - Affordability analysis
 * - Closing costs estimates
 * - Amortization schedules
 *
 * Includes sharing functionality for presenting to borrowers.
 */

import React, { useState } from 'react';
import CalculatorResultCard from './CalculatorResultCard';

// Calculator type icons and labels
const CALCULATOR_CONFIG = {
  piti: {
    label: 'Monthly Payment (PITI)',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
        <line x1="1" y1="10" x2="23" y2="10" />
      </svg>
    ),
    color: '#3b82f6',
  },
  dti: {
    label: 'Debt-to-Income Ratio',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 20V10" />
        <path d="M12 20V4" />
        <path d="M6 20v-6" />
      </svg>
    ),
    color: '#B8924A',
  },
  ltv: {
    label: 'Loan-to-Value Ratio',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4" />
        <path d="M12 8h.01" />
      </svg>
    ),
    color: '#2D7A52',
  },
  pmi: {
    label: 'Mortgage Insurance',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    color: '#f59e0b',
  },
  affordability: {
    label: 'Affordability Analysis',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
    color: '#06b6d4',
  },
  closing_costs: {
    label: 'Closing Costs',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    color: '#ec4899',
  },
  amortization: {
    label: 'Amortization Schedule',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="12" y1="20" x2="12" y2="10" />
        <line x1="18" y1="20" x2="18" y2="4" />
        <line x1="6" y1="20" x2="6" y2="16" />
      </svg>
    ),
    color: '#B8924A',
  },
};

const CalculatorResults = ({
  calculatorResults = [],
  recommendations = [],
  onShare,
  onApprove,
  onReject,
}) => {
  const [expandedCard, setExpandedCard] = useState(null);
  const [filter, setFilter] = useState('all'); // all, pending, approved

  // Filter results based on approval status
  const filteredResults = calculatorResults.filter((result) => {
    if (filter === 'all') return true;
    return result.approval_status === filter;
  });

  // Group by calculator type
  const groupedResults = filteredResults.reduce((acc, result) => {
    const type = result.content?.calculator_type || result.structured_data?.calculator_type || 'other';
    if (!acc[type]) acc[type] = [];
    acc[type].push(result);
    return acc;
  }, {});

  // Empty state
  if (calculatorResults.length === 0) {
    return (
      <div className="calculator-results">
        <div className="calculator-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5">
            <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
            <line x1="8" y1="6" x2="16" y2="6" />
            <line x1="8" y1="10" x2="16" y2="10" />
            <line x1="8" y1="14" x2="12" y2="14" />
          </svg>
          <p>No calculator results found for this call.</p>
          <span>Calculator results are generated when mortgage-related numbers are discussed during the call.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="calculator-results">
      {/* Header with filter */}
      <div className="calculator-results-header">
        <div className="results-count">
          <span className="count-badge">{calculatorResults.length}</span>
          Calculator Result{calculatorResults.length !== 1 ? 's' : ''}
        </div>

        <div className="results-filter">
          <button
            className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All
          </button>
          <button
            className={`filter-btn ${filter === 'pending' ? 'active' : ''}`}
            onClick={() => setFilter('pending')}
          >
            Pending
          </button>
          <button
            className={`filter-btn ${filter === 'approved' ? 'active' : ''}`}
            onClick={() => setFilter('approved')}
          >
            Approved
          </button>
        </div>
      </div>

      {/* Results grouped by type */}
      {Object.entries(groupedResults).map(([type, results]) => {
        const config = CALCULATOR_CONFIG[type] || {
          label: type.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
          icon: (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
              <line x1="8" y1="6" x2="16" y2="6" />
            </svg>
          ),
          color: '#6b7280',
        };

        return (
          <div key={type} className="calculator-type-group">
            <div className="type-header" style={{ borderLeftColor: config.color }}>
              <span className="type-icon" style={{ color: config.color }}>
                {config.icon}
              </span>
              <span className="type-label">{config.label}</span>
              <span className="type-count">{results.length}</span>
            </div>

            <div className="type-results">
              {results.map((result) => (
                <CalculatorResultCard
                  key={result.id}
                  result={result}
                  config={config}
                  isExpanded={expandedCard === result.id}
                  onToggleExpand={() =>
                    setExpandedCard(expandedCard === result.id ? null : result.id)
                  }
                  onShare={onShare}
                  onApprove={onApprove}
                  onReject={onReject}
                />
              ))}
            </div>
          </div>
        );
      })}

      {/* Recommendations section */}
      {recommendations.length > 0 && (
        <div className="calculator-recommendations">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            AI Recommendations
          </h4>
          <ul>
            {recommendations.map((rec, index) => (
              <li key={rec.id || index}>
                {rec.content || rec.structured_data?.recommendation}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default CalculatorResults;
