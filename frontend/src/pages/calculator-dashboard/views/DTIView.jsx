import React from 'react';
import { formatCurrencyFull } from '../../../services/calculator/CalculatorService';

const DTIView = ({ data, profile }) => {
  const { dti, monthlyIncome, housingPayment, otherDebts, remaining } = data;
  const totalDebt = housingPayment + otherDebts;

  const getStatusColor = (value) => {
    if (value <= 36) return '#22c55e';
    if (value <= 43) return '#f59e0b';
    return '#ef4444';
  };

  const getStatusLabel = (value) => {
    if (value <= 28) return 'Excellent';
    if (value <= 36) return 'Good';
    if (value <= 43) return 'Acceptable';
    return 'High';
  };

  const housingPct = (housingPayment / monthlyIncome) * 100;
  const otherDebtPct = (otherDebts / monthlyIncome) * 100;
  const remainingPct = (remaining / monthlyIncome) * 100;

  return (
    <div className="calculator-detail dti-view">
      <div className="detail-header">
        <h2>Debt-to-Income Analysis</h2>
        <p className="detail-subtitle">How your mortgage fits into your total financial picture</p>
      </div>

      <div className="dti-summary-cards">
        <div className="dti-summary-card">
          <div className="summary-icon">{'\u{1F4B0}'}</div>
          <div className="summary-content">
            <div className="summary-label">Gross Monthly Income</div>
            <div className="summary-value income">{formatCurrencyFull(monthlyIncome)}</div>
          </div>
        </div>
        <div className="dti-summary-card">
          <div className="summary-icon">{'\u{1F3E0}'}</div>
          <div className="summary-content">
            <div className="summary-label">Housing Payment (PITI)</div>
            <div className="summary-value expense">{formatCurrencyFull(housingPayment)}</div>
          </div>
        </div>
        <div className="dti-summary-card">
          <div className="summary-icon">{'\u{1F4B3}'}</div>
          <div className="summary-content">
            <div className="summary-label">Other Monthly Debts</div>
            <div className="summary-value expense">{formatCurrencyFull(otherDebts)}</div>
          </div>
        </div>
        <div className="dti-summary-card highlight">
          <div className="summary-icon">{'\u{2728}'}</div>
          <div className="summary-content">
            <div className="summary-label">Remaining for Living</div>
            <div className="summary-value remaining">{formatCurrencyFull(remaining)}</div>
            <div className="summary-subtext">{formatCurrencyFull(remaining / 4)}/week</div>
          </div>
        </div>
      </div>

      <div className="dti-gauges-section">
        <h3>Your DTI Ratios</h3>
        <div className="dti-gauges-row">
          <div className="dti-gauge-card">
            <div className="gauge-header">
              <span className="gauge-title">Front-End DTI</span>
              <span className="gauge-subtitle">Housing Only</span>
            </div>
            <div className="circular-gauge">
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" className="gauge-track" />
                <circle cx="60" cy="60" r="50" className="gauge-progress" style={{ stroke: getStatusColor(dti.frontEnd), strokeDasharray: `${Math.min(dti.frontEnd / 50 * 314, 314)} 314` }} />
              </svg>
              <div className="gauge-center">
                <span className="gauge-percent" style={{ color: getStatusColor(dti.frontEnd) }}>{dti.frontEnd.toFixed(1)}%</span>
                <span className="gauge-status">{getStatusLabel(dti.frontEnd)}</span>
              </div>
            </div>
            <div className="gauge-legend">
              <div className="legend-item"><span className="legend-marker target"></span><span>Target: &lt;28%</span></div>
              <div className="legend-item"><span className="legend-marker limit"></span><span>Limit: 31%</span></div>
            </div>
          </div>

          <div className="dti-gauge-card">
            <div className="gauge-header">
              <span className="gauge-title">Back-End DTI</span>
              <span className="gauge-subtitle">All Debts</span>
            </div>
            <div className="circular-gauge">
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" className="gauge-track" />
                <circle cx="60" cy="60" r="50" className="gauge-progress" style={{ stroke: getStatusColor(dti.backEnd), strokeDasharray: `${Math.min(dti.backEnd / 50 * 314, 314)} 314` }} />
              </svg>
              <div className="gauge-center">
                <span className="gauge-percent" style={{ color: getStatusColor(dti.backEnd) }}>{dti.backEnd.toFixed(1)}%</span>
                <span className="gauge-status">{getStatusLabel(dti.backEnd)}</span>
              </div>
            </div>
            <div className="gauge-legend">
              <div className="legend-item"><span className="legend-marker target"></span><span>Target: &lt;36%</span></div>
              <div className="legend-item"><span className="legend-marker limit"></span><span>QM Limit: 43%</span></div>
            </div>
          </div>
        </div>
      </div>

      <div className="dti-allocation-section">
        <h3>Monthly Income Allocation</h3>
        <div className="allocation-bar-container">
          <div className="allocation-bar">
            <div className="allocation-segment housing" style={{ width: `${housingPct}%` }} title={`Housing: ${housingPct.toFixed(1)}%`} />
            <div className="allocation-segment debts" style={{ width: `${otherDebtPct}%` }} title={`Other Debts: ${otherDebtPct.toFixed(1)}%`} />
            <div className="allocation-segment remaining" style={{ width: `${remainingPct}%` }} title={`Remaining: ${remainingPct.toFixed(1)}%`} />
          </div>
          <div className="allocation-labels">
            <div className="allocation-label"><span className="label-color housing"></span><span className="label-text">Housing</span><span className="label-value">{housingPct.toFixed(0)}%</span></div>
            <div className="allocation-label"><span className="label-color debts"></span><span className="label-text">Other Debts</span><span className="label-value">{otherDebtPct.toFixed(0)}%</span></div>
            <div className="allocation-label"><span className="label-color remaining"></span><span className="label-text">Remaining</span><span className="label-value">{remainingPct.toFixed(0)}%</span></div>
          </div>
        </div>
      </div>

      <div className="dti-breakdown-section">
        <h3>Monthly Debt Breakdown</h3>
        <div className="breakdown-table">
          <div className="breakdown-row income-row">
            <span className="row-icon">{'\u{1F4B5}'}</span>
            <span className="row-label">Gross Monthly Income</span>
            <span className="row-value positive">+{formatCurrencyFull(monthlyIncome)}</span>
          </div>
          <div className="breakdown-divider"></div>
          <div className="breakdown-row">
            <span className="row-icon">{'\u{1F3E0}'}</span>
            <span className="row-label">Proposed Mortgage (PITI)</span>
            <span className="row-value negative">-{formatCurrencyFull(housingPayment)}</span>
          </div>
          <div className="breakdown-row">
            <span className="row-icon">{'\u{1F393}'}</span>
            <span className="row-label">Student Loans</span>
            <span className="row-value negative">-{formatCurrencyFull(profile?.debts?.studentLoan || 450)}</span>
          </div>
          <div className="breakdown-row">
            <span className="row-icon">{'\u{1F697}'}</span>
            <span className="row-label">Auto Loan</span>
            <span className="row-value negative">-{formatCurrencyFull(profile?.debts?.autoLoan || 220)}</span>
          </div>
          {profile?.debts?.creditCards > 0 && (
            <div className="breakdown-row">
              <span className="row-icon">{'\u{1F4B3}'}</span>
              <span className="row-label">Credit Card Minimums</span>
              <span className="row-value negative">-{formatCurrencyFull(profile.debts.creditCards)}</span>
            </div>
          )}
          <div className="breakdown-divider"></div>
          <div className="breakdown-row total-row">
            <span className="row-icon">{'\u{1F4CA}'}</span>
            <span className="row-label">Total Monthly Debt</span>
            <span className="row-value negative">-{formatCurrencyFull(totalDebt)}</span>
          </div>
          <div className="breakdown-row remaining-row">
            <span className="row-icon">{'\u{2728}'}</span>
            <span className="row-label">Available for Living Expenses</span>
            <span className="row-value highlight">{formatCurrencyFull(remaining)}</span>
          </div>
        </div>
      </div>

      <div className={`dti-status-banner ${dti.status}`}>
        <div className="status-icon">
          {dti.status === 'excellent' && '\u{2705}'}
          {dti.status === 'acceptable' && '\u{26A0}️'}
          {dti.status === 'stretched' && '\u{1F6A8}'}
        </div>
        <div className="status-content">
          <div className="status-title">
            {dti.status === 'excellent' && 'Excellent Position'}
            {dti.status === 'acceptable' && 'Acceptable, But Tight'}
            {dti.status === 'stretched' && 'Stretched Budget'}
          </div>
          <div className="status-message">
            {dti.status === 'excellent' && 'Your debt-to-income ratio is well within guidelines. You have comfortable room in your budget.'}
            {dti.status === 'acceptable' && 'You qualify for this loan, but your budget will be tighter. Consider building emergency savings first.'}
            {dti.status === 'stretched' && 'Your DTI exceeds typical guidelines. Consider a lower price point or paying down existing debt first.'}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DTIView;
