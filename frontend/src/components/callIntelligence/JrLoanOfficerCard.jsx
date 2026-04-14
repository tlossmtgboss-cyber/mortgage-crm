// ─────────────────────────────────────────────────────────────
// JR. LOAN OFFICER CARD
// src/components/callIntelligence/JrLoanOfficerCard.jsx
// ─────────────────────────────────────────────────────────────

import React from 'react';
import './JrLoanOfficerCard.css';

function formatCurrency(val) {
  if (val === null || val === undefined) return '\u2014';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(val);
}

const EMPLOYMENT_LABELS = {
  w2: 'W-2',
  self_employed: 'Self-Employed',
  '1099': '1099',
};

function formatField(key, val) {
  if (val === null || val === undefined) return '\u2026';
  switch (key) {
    case 'annual_income':
    case 'purchase_price':
    case 'down_payment_amount':
    case 'monthly_debt':
      return formatCurrency(val);
    case 'down_payment_percent':
      return `${val}%`;
    case 'employment_type':
      return EMPLOYMENT_LABELS[val] ?? String(val);
    case 'loan_type':
      return String(val).toUpperCase();
    case 'loan_purpose':
      return String(val).charAt(0).toUpperCase() + String(val).slice(1);
    case 'bankruptcy_history':
    case 'pre_approval_needed':
      return val ? 'Yes' : 'No';
    default:
      return String(val);
  }
}

// Which fields to display on the card (priority order)
const DISPLAY_FIELDS = [
  { key: 'borrower_name',          label: 'Borrower' },
  { key: 'loan_type',              label: 'Loan Type' },
  { key: 'purchase_price',         label: 'Purchase Price' },
  { key: 'down_payment_percent',   label: 'Down Payment' },
  { key: 'annual_income',          label: 'Annual Income' },
  { key: 'employment_type',        label: 'Employment' },
  { key: 'estimated_credit_score', label: 'Credit Score' },
  { key: 'loan_purpose',           label: 'Purpose' },
];

export default function JrLoanOfficerCard({ state, onViewApplication }) {
  const fields = state.fields;
  const isNew = (key) => key === state.last_field_updated;

  return (
    <div className="jr-lo-card">
      {/* Header */}
      <div className="jr-lo-card__header">
        <div className="jr-lo-card__title-row">
          <div className="jr-lo-card__dot" />
          <span className="jr-lo-card__agent-name">Jr. Loan Officer</span>
        </div>
        <div className="jr-lo-card__tag-filling">
          <span className="jr-lo-card__tag-text">Filling Application</span>
        </div>
      </div>

      {/* Application fields grid */}
      <div className="jr-lo-card__grid">
        {DISPLAY_FIELDS.map(({ key, label }) => {
          const val = fields[key];
          const isEmpty = val === null || val === undefined;
          const isHighlighted = isNew(key);
          return (
            <div
              key={key}
              className={`jr-lo-card__field ${isHighlighted ? 'jr-lo-card__field--highlighted' : ''}`}
            >
              <div className="jr-lo-card__field-label">{label}</div>
              <div className={`jr-lo-card__field-val ${isEmpty ? 'jr-lo-card__field-val--pending' : ''}`}>
                {isEmpty ? 'Pending\u2026' : formatField(key, val)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="jr-lo-card__progress-wrap">
        <div className="jr-lo-card__progress-header">
          <span className="jr-lo-card__progress-label">Application progress</span>
          <span className="jr-lo-card__progress-pct">{state.completion_percent}%</span>
        </div>
        <div className="jr-lo-card__progress-track">
          <div
            className="jr-lo-card__progress-fill"
            style={{ width: `${state.completion_percent}%` }}
          />
        </div>
        <span className="jr-lo-card__progress-sub">
          {state.fields_filled} of {state.fields_total} fields captured
        </span>
      </div>

      {/* View full application button -- shown once application_id exists */}
      {state.application_id && (
        <button className="jr-lo-card__view-btn" onClick={onViewApplication}>
          <span className="jr-lo-card__view-btn-text">View Full Application &rarr;</span>
        </button>
      )}
    </div>
  );
}
