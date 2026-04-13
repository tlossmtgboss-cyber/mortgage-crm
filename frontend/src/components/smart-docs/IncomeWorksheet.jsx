/**
 * IncomeWorksheet
 *
 * Displays income sources for a loan with maker-checker approval controls.
 * Supports sortable columns, expandable row detail, inline overrides,
 * summary row, status-dependent header styling, and accessibility.
 *
 * Props:
 *   income          {object}   — income object with status, sources[], etc.
 *   onApprove       {function} — called when Approve button is clicked
 *   onReject        {function} — called when Reject button is clicked
 *   onOverrideSource {function} — called with (sourceId, newAmount, reason) when override is saved
 */
import React, { useState, useMemo, useCallback } from 'react';
import IncomeConfidenceBadge from '../income/IncomeConfidenceBadge';
import './IncomeWorksheet.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OVERRIDE_REASONS = [
  { value: '', label: 'Select reason...' },
  { value: 'documentation_review', label: 'Documentation review' },
  { value: 'employer_verification', label: 'Employer verification' },
  { value: 'calculation_correction', label: 'Calculation correction' },
  { value: 'seasonal_adjustment', label: 'Seasonal adjustment' },
  { value: 'bonuses_excluded', label: 'Bonuses excluded' },
  { value: 'overtime_excluded', label: 'Overtime excluded' },
  { value: 'part_time_adjustment', label: 'Part-time adjustment' },
  { value: 'other', label: 'Other' },
];

const SORT_COLUMNS = {
  name: 'name',
  type: 'type',
  amount: 'amount',
  confidence: 'confidence',
};

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

function calcTotalMonthly(sources) {
  if (!Array.isArray(sources)) return 0;
  return sources.reduce((sum, src) => sum + Number(src.monthly_amount || src.amount || 0), 0);
}

function calcWeightedConfidence(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return 0;
  const withConfidence = sources.filter((s) => s.confidence != null);
  if (withConfidence.length === 0) return 0;
  const totalAmount = withConfidence.reduce(
    (sum, s) => sum + Math.abs(Number(s.monthly_amount || s.amount || 0)),
    0
  );
  if (totalAmount === 0) {
    // Equal-weight fallback
    return Math.round(
      withConfidence.reduce((sum, s) => sum + Number(s.confidence), 0) / withConfidence.length
    );
  }
  const weighted = withConfidence.reduce((sum, s) => {
    const amt = Math.abs(Number(s.monthly_amount || s.amount || 0));
    return sum + Number(s.confidence) * amt;
  }, 0);
  return Math.round(weighted / totalAmount);
}

function countVerified(sources) {
  if (!Array.isArray(sources)) return 0;
  return sources.filter((s) => s.verified === true || s.verified === 'true').length;
}

function getSourceName(src) {
  return src.name || src.source_name || '';
}

function getSourceType(src) {
  return src.type || src.income_type || '';
}

function getMonthlyAmount(src) {
  return Number(src.monthly_amount != null ? src.monthly_amount : src.amount || 0);
}

function getConfidence(src) {
  return src.confidence != null ? Number(src.confidence) : -1;
}

function getSourceId(src, idx) {
  return src.id || src.source_id || idx;
}

function getTrendDirection(year1, year2) {
  if (year1 == null || year2 == null) return null;
  const y1 = Number(year1);
  const y2 = Number(year2);
  if (y1 === 0) return y2 > 0 ? 'up' : null;
  const pctChange = ((y2 - y1) / Math.abs(y1)) * 100;
  if (pctChange > 1) return 'up';
  if (pctChange < -1) return 'down';
  return 'flat';
}

function formatPercent(value) {
  if (value == null) return '';
  return `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(1)}%`;
}

function getStatusIcon(status) {
  switch (status) {
    case 'APPROVED':
      return (
        <svg className="iw__status-icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M13.5 4.5L6.5 11.5L2.5 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case 'REJECTED':
      return (
        <svg className="iw__status-icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M12 4L4 12M4 4l8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    default:
      return (
        <svg className="iw__status-icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
          <path d="M8 4.5V8.5L10.5 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
  }
}

function getSortIndicator(column, sortState) {
  if (sortState.column !== column) {
    return <span className="iw__sort-indicator iw__sort-indicator--inactive" aria-hidden="true">&#8597;</span>;
  }
  return (
    <span className="iw__sort-indicator iw__sort-indicator--active" aria-hidden="true">
      {sortState.direction === 'asc' ? '\u2191' : '\u2193'}
    </span>
  );
}

function getAriaSortValue(column, sortState) {
  if (sortState.column !== column) return 'none';
  return sortState.direction === 'asc' ? 'ascending' : 'descending';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ExpandedRowDetail({ source }) {
  const year1 = source.year1_income ?? source.prior_year_income;
  const year2 = source.year2_income ?? source.current_year_income;
  const trendDirection = getTrendDirection(year1, year2);
  const pctChange =
    year1 != null && year2 != null && Number(year1) !== 0
      ? ((Number(year2) - Number(year1)) / Math.abs(Number(year1))) * 100
      : null;

  const verifiedDate = source.verified_date || source.verification_date;
  const docs = source.documents || source.source_documents || [];
  const aiNotes = source.ai_notes || source.notes;

  return (
    <div className="iw__detail">
      <div className="iw__detail-grid">
        {/* Trending */}
        {(year1 != null || year2 != null) && (
          <div className="iw__detail-section">
            <h4 className="iw__detail-heading">Income Trend</h4>
            <div className="iw__trend-row">
              {year1 != null && (
                <div className="iw__trend-item">
                  <span className="iw__trend-label">Prior Year</span>
                  <span className="iw__trend-value">{formatCurrency(year1)}</span>
                </div>
              )}
              {year2 != null && (
                <div className="iw__trend-item">
                  <span className="iw__trend-label">Current Year</span>
                  <span className="iw__trend-value">{formatCurrency(year2)}</span>
                </div>
              )}
              {pctChange != null && (
                <div className="iw__trend-item">
                  <span className="iw__trend-label">Change</span>
                  <span className={`iw__trend-change iw__trend-change--${trendDirection || 'flat'}`}>
                    {trendDirection === 'up' && '\u2191'}
                    {trendDirection === 'down' && '\u2193'}
                    {trendDirection === 'flat' && '\u2194'}
                    {' '}{formatPercent(pctChange)}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Verification */}
        <div className="iw__detail-section">
          <h4 className="iw__detail-heading">Verification</h4>
          <div className="iw__detail-meta">
            <span className={`iw__detail-verified ${source.verified ? 'iw__detail-verified--yes' : 'iw__detail-verified--no'}`}>
              {source.verified ? 'Verified' : 'Unverified'}
            </span>
            {verifiedDate && (
              <span className="iw__detail-date">
                {new Date(verifiedDate).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
            )}
          </div>
        </div>

        {/* Source Documents */}
        {docs.length > 0 && (
          <div className="iw__detail-section">
            <h4 className="iw__detail-heading">Source Documents</h4>
            <ul className="iw__detail-docs">
              {docs.map((doc, i) => (
                <li key={i} className="iw__detail-doc-item">
                  {typeof doc === 'string' ? doc : doc.name || doc.filename || `Document ${i + 1}`}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* AI Notes */}
        {aiNotes && (
          <div className="iw__detail-section iw__detail-section--full">
            <h4 className="iw__detail-heading">AI Notes</h4>
            <p className="iw__detail-notes">{aiNotes}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function InlineOverrideRow({ source, onSave, onCancel }) {
  const currentAmount = getMonthlyAmount(source);
  const [newAmount, setNewAmount] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const parsedAmount = parseFloat(newAmount);
  const isValidAmount = !isNaN(parsedAmount) && parsedAmount > 0;
  const delta = isValidAmount ? parsedAmount - currentAmount : null;

  const handleSave = useCallback(() => {
    if (!isValidAmount) {
      setError('Amount must be greater than 0');
      return;
    }
    if (!reason) {
      setError('Please select a reason');
      return;
    }
    setError('');
    onSave(parsedAmount, reason);
  }, [isValidAmount, reason, parsedAmount, onSave]);

  return (
    <div className="iw__override-form">
      <div className="iw__override-fields">
        <div className="iw__override-field">
          <label className="iw__override-label" htmlFor={`override-amount-${getSourceId(source, 0)}`}>
            New Monthly Amount
          </label>
          <div className="iw__override-input-group">
            <span className="iw__override-currency">$</span>
            <input
              id={`override-amount-${getSourceId(source, 0)}`}
              className="iw__override-input"
              type="number"
              step="0.01"
              min="0.01"
              placeholder={currentAmount.toFixed(2)}
              value={newAmount}
              onChange={(e) => {
                setNewAmount(e.target.value);
                setError('');
              }}
              autoFocus
            />
          </div>
          {delta != null && (
            <span className={`iw__override-delta ${delta >= 0 ? 'iw__override-delta--up' : 'iw__override-delta--down'}`}>
              {delta >= 0 ? '+' : ''}{formatCurrency(delta)} from {formatCurrency(currentAmount)}
            </span>
          )}
        </div>
        <div className="iw__override-field">
          <label className="iw__override-label" htmlFor={`override-reason-${getSourceId(source, 0)}`}>
            Reason
          </label>
          <select
            id={`override-reason-${getSourceId(source, 0)}`}
            className="iw__override-select"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setError('');
            }}
          >
            {OVERRIDE_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && <div className="iw__override-error" role="alert">{error}</div>}
      <div className="iw__override-actions">
        <button className="iw__btn iw__btn--primary iw__btn--sm" type="button" onClick={handleSave}>
          Save Override
        </button>
        <button className="iw__btn iw__btn--secondary iw__btn--sm" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="iw__empty-state">
      <svg className="iw__empty-icon" viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" strokeWidth="2" />
        <path d="M6 18h36M18 18v20" stroke="currentColor" strokeWidth="2" />
        <path d="M24 28h10M24 34h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <p className="iw__empty-title">No income sources found for this loan</p>
      <p className="iw__empty-subtitle">Run an income calculation to get started</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

function IncomeWorksheet({ income, onApprove, onReject, onOverrideSource }) {
  const [sortState, setSortState] = useState({ column: 'amount', direction: 'desc' });
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [overridingRow, setOverridingRow] = useState(null);

  // -- Sorting logic --
  const handleSort = useCallback((column) => {
    setSortState((prev) => {
      if (prev.column === column) {
        return { column, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      // Default direction: desc for amount/confidence, asc for text
      const defaultDir = column === 'amount' || column === 'confidence' ? 'desc' : 'asc';
      return { column, direction: defaultDir };
    });
  }, []);

  // -- Expand/collapse --
  const toggleExpand = useCallback((sourceId) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) {
        next.delete(sourceId);
      } else {
        next.add(sourceId);
      }
      return next;
    });
  }, []);

  const handleRowKeyDown = useCallback((e, sourceId) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleExpand(sourceId);
    }
  }, [toggleExpand]);

  // -- Override --
  const handleOverrideSave = useCallback(
    (sourceId, newAmount, reason) => {
      if (onOverrideSource) {
        onOverrideSource(sourceId, newAmount, reason);
      }
      setOverridingRow(null);
    },
    [onOverrideSource]
  );

  // -- Early return --
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
  const weightedConfidence = calcWeightedConfidence(sources);
  const verifiedCount = countVerified(sources);
  const isTerminal = status === 'APPROVED' || status === 'REJECTED';

  // -- Sorted sources --
  const sortedSources = useMemo(() => {
    if (sources.length === 0) return sources;
    const copy = [...sources];
    const { column, direction } = sortState;
    const multiplier = direction === 'asc' ? 1 : -1;

    copy.sort((a, b) => {
      let cmp = 0;
      switch (column) {
        case 'name':
          cmp = getSourceName(a).localeCompare(getSourceName(b));
          break;
        case 'type':
          cmp = getSourceType(a).localeCompare(getSourceType(b));
          break;
        case 'amount':
          cmp = getMonthlyAmount(a) - getMonthlyAmount(b);
          break;
        case 'confidence':
          cmp = getConfidence(a) - getConfidence(b);
          break;
        default:
          cmp = 0;
      }
      return cmp * multiplier;
    });
    return copy;
  }, [sources, sortState]);

  // -- Status-dependent header class --
  const headerStatusClass =
    status === 'APPROVED'
      ? 'iw__header--approved'
      : status === 'REJECTED'
        ? 'iw__header--rejected'
        : 'iw__header--pending';

  return (
    <div className="iw">
      {/* Header */}
      <div className={`iw__header ${headerStatusClass}`}>
        <div className="iw__header-left">
          <h2 className="iw__title">
            {getStatusIcon(status)}
            Income Calculation
          </h2>
          <span
            className={`iw__status-badge iw__status-badge--${
              status === 'APPROVED' ? 'success' : status === 'REJECTED' ? 'error' : 'warning'
            }`}
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
          <EmptyState />
        ) : (
          <table className="iw__table" aria-label="Income sources breakdown">
            <thead>
              <tr>
                <th scope="col" className="iw__th-expand" aria-label="Expand row">
                  {/* Chevron column — not sortable */}
                </th>
                <th
                  scope="col"
                  className="iw__th-sortable"
                  aria-sort={getAriaSortValue('name', sortState)}
                  onClick={() => handleSort('name')}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleSort('name')}
                  tabIndex={0}
                  role="columnheader"
                >
                  Source Name {getSortIndicator('name', sortState)}
                </th>
                <th
                  scope="col"
                  className="iw__th-sortable"
                  aria-sort={getAriaSortValue('type', sortState)}
                  onClick={() => handleSort('type')}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleSort('type')}
                  tabIndex={0}
                  role="columnheader"
                >
                  Type {getSortIndicator('type', sortState)}
                </th>
                <th
                  scope="col"
                  className="iw__th-sortable"
                  aria-sort={getAriaSortValue('amount', sortState)}
                  onClick={() => handleSort('amount')}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleSort('amount')}
                  tabIndex={0}
                  role="columnheader"
                >
                  Monthly Amount {getSortIndicator('amount', sortState)}
                </th>
                <th
                  scope="col"
                  className="iw__th-sortable"
                  aria-sort={getAriaSortValue('confidence', sortState)}
                  onClick={() => handleSort('confidence')}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleSort('confidence')}
                  tabIndex={0}
                  role="columnheader"
                >
                  Confidence {getSortIndicator('confidence', sortState)}
                </th>
                <th scope="col">Verified</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedSources.map((src, idx) => {
                const sourceId = getSourceId(src, idx);
                const confidence = src.confidence != null ? Number(src.confidence) : null;
                const isVerified = src.verified === true || src.verified === 'true';
                const monthlyAmount = src.monthly_amount != null ? src.monthly_amount : src.amount;
                const isExpanded = expandedRows.has(sourceId);
                const isOverriding = overridingRow === sourceId;

                return (
                  <React.Fragment key={sourceId}>
                    <tr
                      className={`iw__row ${isExpanded ? 'iw__row--expanded' : ''}`}
                      onClick={() => toggleExpand(sourceId)}
                      onKeyDown={(e) => handleRowKeyDown(e, sourceId)}
                      tabIndex={0}
                      role="row"
                      aria-expanded={isExpanded}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="iw__cell-chevron" aria-hidden="true">
                        <span className={`iw__chevron ${isExpanded ? 'iw__chevron--open' : ''}`}>
                          &#9654;
                        </span>
                      </td>
                      <td className="iw__cell-name">{getSourceName(src) || '\u2014'}</td>
                      <td>{getSourceType(src) || '\u2014'}</td>
                      <td className="iw__cell-amount">{formatCurrency(monthlyAmount)}</td>
                      <td>
                        {confidence != null ? (
                          <IncomeConfidenceBadge score={confidence} size="sm" />
                        ) : (
                          <span className="iw__confidence-na">N/A</span>
                        )}
                      </td>
                      <td>
                        <span
                          className={`iw__verified-badge ${
                            isVerified ? 'iw__verified-badge--yes' : 'iw__verified-badge--no'
                          }`}
                        >
                          {isVerified ? 'Yes' : 'No'}
                        </span>
                      </td>
                      <td>
                        <button
                          className="iw__override-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOverridingRow(isOverriding ? null : sourceId);
                          }}
                          type="button"
                          aria-label={`Override income source: ${getSourceName(src) || sourceId}`}
                        >
                          {isOverriding ? 'Cancel' : 'Override'}
                        </button>
                      </td>
                    </tr>

                    {/* Expanded detail row */}
                    {isExpanded && (
                      <tr className="iw__detail-row">
                        <td colSpan={7}>
                          <ExpandedRowDetail source={src} />
                        </td>
                      </tr>
                    )}

                    {/* Inline override row */}
                    {isOverriding && (
                      <tr className="iw__override-row">
                        <td colSpan={7}>
                          <InlineOverrideRow
                            source={src}
                            onSave={(newAmount, reason) => handleOverrideSave(sourceId, newAmount, reason)}
                            onCancel={() => setOverridingRow(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}

              {/* Summary row */}
              <tr className="iw__summary-row">
                <td className="iw__cell-chevron" />
                <td className="iw__summary-label" colSpan={2}>
                  TOTAL
                </td>
                <td className="iw__cell-amount iw__summary-amount">
                  {formatCurrency(totalMonthly)}
                </td>
                <td className="iw__summary-confidence">
                  <IncomeConfidenceBadge score={weightedConfidence} size="sm" />
                  <span className="iw__summary-sublabel">weighted avg</span>
                </td>
                <td className="iw__summary-verified">
                  {verifiedCount}/{sources.length} verified
                </td>
                <td />
              </tr>
            </tbody>
          </table>
        )}
      </div>

      {/* Actions footer -- only shown when not yet approved/rejected */}
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
