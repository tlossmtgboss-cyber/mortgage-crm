import React from 'react';
import './BankAnalysisPanel.css';

/**
 * BankAnalysisPanel
 *
 * Displays a full bank statement analysis result including:
 * - Summary metrics (avg balance, income, expenses)
 * - Large deposits table with sourcing actions
 * - NSF / overdraft flags
 * - Undisclosed debt indicators
 *
 * Props:
 *   analysis       {object}   — bank analysis data object
 *   onSourceDeposit {function} — called with the deposit object when "Source" is clicked
 */
function BankAnalysisPanel({ analysis, onSourceDeposit }) {
  if (!analysis) return null;

  const summary = analysis.summary || {};
  const largeDeposits = analysis.large_deposits || [];
  const nsfOverdrafts = analysis.nsf_overdrafts || [];
  const undisclosedDebts = analysis.undisclosed_debts || [];
  const riskLevel = (analysis.risk_level || 'LOW').toUpperCase();

  // Derive badge modifier from risk level
  function getRiskBadgeModifier(level) {
    if (level === 'HIGH') return 'error';
    if (level === 'MEDIUM') return 'warning';
    return 'success';
  }

  const riskModifier = getRiskBadgeModifier(riskLevel);

  function formatCurrency(amount) {
    if (amount == null) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(amount);
  }

  function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  }

  return (
    <div className="bap">
      {/* Header */}
      <div className="bap__header">
        <h2 className="bap__title">Bank Statement Analysis</h2>
        <span className={`bap__risk-badge bap__risk-badge--${riskModifier}`}>
          {riskLevel} RISK
        </span>
      </div>

      {/* Summary */}
      <div className="bap__summary">
        <div className="bap__summary-item">
          <span className="bap__summary-label">Avg Monthly Balance</span>
          <span className="bap__summary-value">
            {formatCurrency(summary.avg_monthly_balance)}
          </span>
        </div>
        <div className="bap__summary-item">
          <span className="bap__summary-label">Avg Monthly Income</span>
          <span className="bap__summary-value">
            {formatCurrency(summary.avg_monthly_income)}
          </span>
        </div>
        <div className="bap__summary-item">
          <span className="bap__summary-label">Avg Monthly Expenses</span>
          <span className="bap__summary-value">
            {formatCurrency(summary.avg_monthly_expenses)}
          </span>
        </div>
      </div>

      {/* Large Deposits */}
      <div className="bap__section">
        <h3 className="bap__section-title">
          Large Deposits ({largeDeposits.length})
        </h3>
        {largeDeposits.length === 0 ? (
          <p className="bap__empty">No large deposits found.</p>
        ) : (
          <div className="bap__table-container">
            <table className="bap__table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Amount</th>
                  <th>Description</th>
                  <th>Sourced</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {largeDeposits.map((deposit, idx) => {
                  const isSourced = Boolean(deposit.sourced || deposit.is_sourced);
                  return (
                    <tr key={deposit.id || idx}>
                      <td>{formatDate(deposit.date || deposit.transaction_date)}</td>
                      <td>{formatCurrency(deposit.amount)}</td>
                      <td>{deposit.description || deposit.memo || '—'}</td>
                      <td>
                        {isSourced ? (
                          <span className="bap__sourced-yes">Yes</span>
                        ) : (
                          <span className="bap__sourced-no">No</span>
                        )}
                      </td>
                      <td>
                        {!isSourced && typeof onSourceDeposit === 'function' && (
                          <button
                            className="bap__source-btn"
                            onClick={() => onSourceDeposit(deposit)}
                            type="button"
                          >
                            Source
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* NSF / Overdrafts */}
      <div className="bap__section">
        <h3 className="bap__section-title">
          NSF / Overdrafts ({nsfOverdrafts.length})
        </h3>
        {nsfOverdrafts.length === 0 ? (
          <p className="bap__empty">No NSF or overdraft events found.</p>
        ) : (
          <div className="bap__flag-list">
            {nsfOverdrafts.map((item, idx) => (
              <div key={item.id || idx} className="bap__flag bap__flag--error">
                <div className="bap__flag-header">
                  <span className="bap__flag-label">
                    {item.type || item.event_type || 'NSF / Overdraft'}
                  </span>
                  <span className="bap__flag-date">
                    {formatDate(item.date || item.transaction_date)}
                  </span>
                </div>
                {item.amount != null && (
                  <div className="bap__flag-amount">{formatCurrency(item.amount)}</div>
                )}
                {(item.description || item.memo) && (
                  <div className="bap__flag-desc">
                    {item.description || item.memo}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Undisclosed Debts */}
      <div className="bap__section">
        <h3 className="bap__section-title">
          Undisclosed Debts ({undisclosedDebts.length})
        </h3>
        {undisclosedDebts.length === 0 ? (
          <p className="bap__empty">No undisclosed debts detected.</p>
        ) : (
          <div className="bap__debt-list">
            {undisclosedDebts.map((debt, idx) => (
              <div key={debt.id || idx} className="bap__flag bap__flag--warning">
                <div className="bap__debt-info">
                  <span className="bap__debt-payee">
                    {debt.payee || debt.creditor || debt.description || 'Unknown Payee'}
                  </span>
                  {(debt.category || debt.debt_type) && (
                    <span className="bap__debt-category">
                      {debt.category || debt.debt_type}
                    </span>
                  )}
                </div>
                {debt.monthly_amount != null && (
                  <span className="bap__debt-amount">
                    {formatCurrency(debt.monthly_amount)}/mo
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default BankAnalysisPanel;
