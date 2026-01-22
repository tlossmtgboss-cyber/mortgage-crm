/**
 * Five C Card Component
 *
 * Individual expandable card for each of the 5 C's of Credit:
 * - Credit, Collateral, Capacity, Characteristics, Cash
 *
 * Features:
 * - Collapsed: Shows category name + assessment badge
 * - Expanded: Shows full analysis, issues, notes
 * - Color-coded by assessment (Strong/Adequate/Weak/Unknown)
 */

import React, { useState } from 'react';

const ASSESSMENT_COLORS = {
  Strong: { bg: '#dcfce7', border: '#22c55e', text: '#166534', icon: 'check' },
  Adequate: { bg: '#fef9c3', border: '#eab308', text: '#854d0e', icon: 'minus' },
  Weak: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b', icon: 'alert' },
  Unknown: { bg: '#f3f4f6', border: '#9ca3af', text: '#4b5563', icon: 'question' },
};

const CATEGORY_ICONS = {
  credit: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <line x1="2" y1="10" x2="22" y2="10" />
    </svg>
  ),
  collateral: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  capacity: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="1" x2="12" y2="23" />
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  ),
  characteristics: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  ),
  cash: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
      <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
    </svg>
  ),
};

const CATEGORY_LABELS = {
  credit: 'Credit',
  collateral: 'Collateral',
  capacity: 'Capacity',
  characteristics: 'Characteristics',
  cash: 'Cash / Reserves',
};

const FiveCCard = ({ category, data, onCreateTask }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!data) return null;

  const assessment = data.assessment || 'Unknown';
  const colors = ASSESSMENT_COLORS[assessment] || ASSESSMENT_COLORS.Unknown;
  const icon = CATEGORY_ICONS[category];
  const label = CATEGORY_LABELS[category] || category;

  const renderDetails = () => {
    switch (category) {
      case 'credit':
        return (
          <>
            {data.score && (
              <div className="detail-row">
                <span className="detail-label">Credit Score:</span>
                <span className="detail-value">{data.score}</span>
              </div>
            )}
            {data.tier && (
              <div className="detail-row">
                <span className="detail-label">Tier:</span>
                <span className="detail-value">{data.tier}</span>
              </div>
            )}
            {data.issues && data.issues.length > 0 && (
              <div className="detail-issues">
                <span className="detail-label">Issues:</span>
                <ul>
                  {data.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        );

      case 'collateral':
        return (
          <>
            {data.property_type && (
              <div className="detail-row">
                <span className="detail-label">Property Type:</span>
                <span className="detail-value">{data.property_type}</span>
              </div>
            )}
            {data.property_value && (
              <div className="detail-row">
                <span className="detail-label">Value:</span>
                <span className="detail-value">${data.property_value.toLocaleString()}</span>
              </div>
            )}
            {data.ltv && (
              <div className="detail-row">
                <span className="detail-label">LTV:</span>
                <span className="detail-value">{data.ltv}%</span>
              </div>
            )}
          </>
        );

      case 'capacity':
        return (
          <>
            {data.dti && (
              <div className="detail-row">
                <span className="detail-label">DTI:</span>
                <span className="detail-value">{data.dti}%</span>
              </div>
            )}
            {data.income_stability && (
              <div className="detail-row">
                <span className="detail-label">Income Stability:</span>
                <span className="detail-value">{data.income_stability}</span>
              </div>
            )}
            {data.employment_tenure && (
              <div className="detail-row">
                <span className="detail-label">Employment Tenure:</span>
                <span className="detail-value">{data.employment_tenure}</span>
              </div>
            )}
          </>
        );

      case 'characteristics':
        return (
          <>
            {data.employment_years && (
              <div className="detail-row">
                <span className="detail-label">Years Employed:</span>
                <span className="detail-value">{data.employment_years}</span>
              </div>
            )}
            {data.residence_years && (
              <div className="detail-row">
                <span className="detail-label">Years at Residence:</span>
                <span className="detail-value">{data.residence_years}</span>
              </div>
            )}
            {data.financial_stability && (
              <div className="detail-row">
                <span className="detail-label">Financial Stability:</span>
                <span className="detail-value">{data.financial_stability}</span>
              </div>
            )}
          </>
        );

      case 'cash':
        return (
          <>
            {data.down_payment_pct && (
              <div className="detail-row">
                <span className="detail-label">Down Payment:</span>
                <span className="detail-value">{data.down_payment_pct}%</span>
              </div>
            )}
            {data.reserves_months && (
              <div className="detail-row">
                <span className="detail-label">Reserves:</span>
                <span className="detail-value">{data.reserves_months} months</span>
              </div>
            )}
            {data.down_payment_source && (
              <div className="detail-row">
                <span className="detail-label">Source:</span>
                <span className="detail-value">{data.down_payment_source}</span>
              </div>
            )}
            {data.assets_discussed && data.assets_discussed.length > 0 && (
              <div className="detail-issues">
                <span className="detail-label">Assets Discussed:</span>
                <ul>
                  {data.assets_discussed.map((asset, i) => (
                    <li key={i}>{asset}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        );

      default:
        return null;
    }
  };

  return (
    <div
      className={`five-c-card ${isExpanded ? 'expanded' : ''}`}
      style={{
        backgroundColor: colors.bg,
        borderColor: colors.border,
      }}
    >
      <div
        className="five-c-card-header"
        onClick={() => setIsExpanded(!isExpanded)}
        style={{ cursor: 'pointer' }}
      >
        <div className="five-c-icon" style={{ color: colors.text }}>
          {icon}
        </div>
        <div className="five-c-title">
          <span className="category-name">{label}</span>
          <span
            className={`assessment-badge assessment-${assessment.toLowerCase()}`}
            style={{
              backgroundColor: colors.border,
              color: '#fff',
            }}
          >
            {assessment}
          </span>
        </div>
        <div className="expand-icon" style={{ color: colors.text }}>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            style={{
              transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s ease',
            }}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>

      {isExpanded && (
        <div className="five-c-card-body" style={{ borderTopColor: colors.border }}>
          {renderDetails()}

          {data.notes && (
            <div className="detail-notes">
              <span className="detail-label">Notes:</span>
              <p>{data.notes}</p>
            </div>
          )}

          {assessment === 'Weak' && onCreateTask && (
            <button
              className="create-task-btn"
              onClick={(e) => {
                e.stopPropagation();
                onCreateTask({
                  task_type: `jrlo_5c_review`,
                  title: `Review ${label} - Weak Assessment`,
                  description: data.notes || `The ${label} assessment is weak. Please review and address.`,
                  priority: 'high',
                  assigned_role: 'lo',
                });
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              Create Review Task
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default FiveCCard;
