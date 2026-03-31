/**
 * IncomeWorksheet
 *
 * Displays income sources for a loan with maker-checker approval controls.
 *
 * Props:
 *   income          {object}   — income object with status, sources[], etc.
 *   onApprove       {function} — called when Approve button is clicked
 *   onReject        {function} — called when Reject button is clicked
 *   onOverrideSource {function} — called with (sourceId) when Override is clicked
 */
import React from 'react';
import './IncomeWorksheet.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(amount) {
  if (amount == null || amount === '') return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(amount));
}

function getConfidenceClass(confidence) {
  const pct = Number(confidence);
  if (pct >= 90) return 'iw__confidence--high';
  if (pct >= 70) return 'iw__confidence--medium';
  return 'iw__confidence--low';
}

function getStatusBadgeClass(status) {
  const s = (status || '').toUpperCase();
  if (s === 'APPROVED') return 'iw__status-badge iw__status-badge--success';
  if (s === 'REJECTED') return 'iw__status-badge iw__status-badge--error';
  return 'iw__status-badge iw__status-badge--warning';
}

function calcTotalMonthly(sources) {
  if (!Array.isArray(sources)) return 0;
  return sources.reduce((sum, src) => sum + Number(src.monthly_amount || src.amount || 0), 0);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function IncomeWorksheet({ income, onApprove, onReject, onOverrideSource }) {
  if (!income) {
    return (
      <div className="iw iw--empty">
        <p>No income data loaded.</p>
      </div>
    );
  }

  const status = (income.status || 'PENDING').toUpperCase();
  const sources = income.sources || [];
  const totalMonthly = calcTotalMonthly(sources);
  const isTerminal = status === 'APPROVED' || status === 'REJECTED';

  return (
    <div className="iw">
      {/* Header */}
      <div className="iw__header">
        <div className="iw__header-left">
          <h2 className="iw__title">Income Calculation</h2>
          <span
            className={getStatusBadgeClass(status)}
            aria-label={`Income worksheet status: ${status}`}
          >
            {status}
          </span>
        </div>
        <div
          className="iw__header-right"
          aria-label={`Total monthly income: ${formatCurrency(totalMonthly)}`}
        >
          <span className="iw__total-label">Total Monthly Income</span>
          <span className="iw__total-value">{formatCurrency(totalMonthly)}</span>
        </div>
      </div>

      {/* Table */}
      <div className="iw__table-wrapper">
        {sources.length === 0 ? (
          <div className="iw__empty-table">No income sources found.</div>
        ) : (
          <table className="iw__table" aria-label="Income sources breakdown">
            <thead>
              <tr>
                <th scope="col">Source Name</th>
                <th scope="col">Type</th>
                <th scope="col">Monthly Amount</th>
                <th scope="col">Confidence</th>
                <th scope="col">Verified</th>
                <th scope="col">Override</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src, idx) => {
                const sourceId = src.id || src.source_id || idx;
                const confidence = src.confidence != null ? Number(src.confidence) : null;
                const isVerified = src.verified === true || src.verified === 'true';
                const monthlyAmount = src.monthly_amount != null ? src.monthly_amount : src.amount;

                return (
                  <tr key={sourceId}>
                    <td className="iw__cell-name">{src.name || src.source_name || '—'}</td>
                    <td>{src.type || src.income_type || '—'}</td>
                    <td className="iw__cell-amount">{formatCurrency(monthlyAmount)}</td>
                    <td>
                      {confidence != null ? (
                        <span className={`iw__confidence ${getConfidenceClass(confidence)}`}>
                          {confidence}%
                        </span>
                      ) : (
                        <span className="iw__confidence iw__confidence--low">N/A</span>
                      )}
                    </td>
                    <td>
                      <span className={`iw__verified-badge ${isVerified ? 'iw__verified-badge--yes' : 'iw__verified-badge--no'}`}>
                        {isVerified ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="iw__override-btn"
                        onClick={() => onOverrideSource && onOverrideSource(sourceId)}
                        type="button"
                        aria-label={`Override income source: ${src.name || src.source_name || sourceId}`}
                      >
                        Override
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Actions footer — only shown when not yet approved/rejected */}
      {!isTerminal && (
        <div className="iw__actions">
          <button
            className="iw__btn iw__btn--primary"
            onClick={onApprove}
            type="button"
            aria-label="Approve income calculation"
          >
            Approve Income
          </button>
          <button
            className="iw__btn iw__btn--secondary"
            onClick={onReject}
            type="button"
            aria-label="Reject income calculation"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

export default IncomeWorksheet;
