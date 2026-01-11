/**
 * EnhancedPortalHeader Component
 *
 * Enhanced header for BorrowerPortal that mirrors ActiveLoanPortal design.
 * Features:
 * - Loan details bar (address, loan amount, loan type)
 * - Horizontal milestone progress bar
 * - Days until closing counter
 * - Loan officer contact card
 */

import React from 'react';
import './EnhancedPortalHeader.css';

/**
 * Days Counter Widget
 */
export function DaysCounter({ daysRemaining, targetDate, isOverdue = false }) {
  const displayDays = Math.abs(daysRemaining || 0);

  return (
    <div className={`days-counter ${isOverdue ? 'overdue' : ''}`}>
      <div className="days-number">{displayDays}</div>
      <div className="days-label">
        {isOverdue ? 'Days Past Due' : 'Days to Close'}
      </div>
      {targetDate && (
        <div className="target-date">
          Target: {new Date(targetDate).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Milestone Progress Bar (horizontal)
 */
export function MilestoneProgressBar({ milestones = [], completed = 0, total = 0 }) {
  const progressPercent = total > 0 ? Math.round((completed / total) * 100) : 0;

  // If we have milestone details, render individual steps
  if (milestones.length > 0) {
    return (
      <div className="milestone-progress-bar">
        <div className="progress-steps">
          {milestones.map((milestone, index) => (
            <div
              key={milestone.id || index}
              className={`progress-step ${milestone.status?.toLowerCase() || 'pending'}`}
              title={milestone.name}
            >
              <div className="step-dot">
                {milestone.status === 'COMPLETE' ? (
                  <span className="check-icon">✓</span>
                ) : milestone.status === 'ACTIVE' ? (
                  <span className="active-dot" />
                ) : (
                  <span className="number">{index + 1}</span>
                )}
              </div>
              {index < milestones.length - 1 && (
                <div className={`step-line ${
                  milestone.status === 'COMPLETE' ? 'completed' : ''
                }`} />
              )}
            </div>
          ))}
        </div>
        <div className="progress-labels">
          <span className="progress-text">{completed} of {total} milestones complete</span>
          <span className="progress-percent">{progressPercent}%</span>
        </div>
      </div>
    );
  }

  // Fallback to simple progress bar
  return (
    <div className="milestone-progress-bar simple">
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>
      <div className="progress-labels">
        <span className="progress-text">{completed} of {total} milestones complete</span>
        <span className="progress-percent">{progressPercent}%</span>
      </div>
    </div>
  );
}

/**
 * Loan Officer Contact Card
 */
export function LoanOfficerCard({ loanOfficer }) {
  if (!loanOfficer) return null;

  const { name, email, phone, photo_url, title } = loanOfficer;

  const handleCall = () => {
    if (phone) {
      window.location.href = `tel:${phone}`;
    }
  };

  const handleEmail = () => {
    if (email) {
      window.location.href = `mailto:${email}`;
    }
  };

  return (
    <div className="loan-officer-card">
      <div className="lo-photo">
        {photo_url ? (
          <img src={photo_url} alt={name} />
        ) : (
          <div className="lo-initials">
            {name?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
          </div>
        )}
      </div>
      <div className="lo-info">
        <h4 className="lo-name">{name || 'Your Loan Officer'}</h4>
        {title && <span className="lo-title">{title}</span>}
      </div>
      <div className="lo-actions">
        {phone && (
          <button className="lo-action-btn call" onClick={handleCall} title="Call">
            <span>📞</span>
          </button>
        )}
        {email && (
          <button className="lo-action-btn email" onClick={handleEmail} title="Email">
            <span>✉️</span>
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Loan Info Bar
 */
export function LoanInfoBar({ loan }) {
  if (!loan) return null;

  const {
    loan_number,
    property_address,
    loan_amount,
    loan_type,
    interest_rate,
  } = loan;

  // Format property address
  const formatAddress = (addr) => {
    if (!addr) return 'Address not available';
    if (typeof addr === 'string') return addr;
    if (typeof addr === 'object') {
      return `${addr.street || ''}, ${addr.city || ''} ${addr.state || ''} ${addr.zip || ''}`.trim();
    }
    return 'Address not available';
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (!amount) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  return (
    <div className="loan-info-bar">
      <div className="loan-info-item address">
        <span className="info-icon">🏠</span>
        <div className="info-content">
          <span className="info-label">Property</span>
          <span className="info-value">{formatAddress(property_address)}</span>
        </div>
      </div>

      {loan_amount && (
        <div className="loan-info-item amount">
          <span className="info-icon">💰</span>
          <div className="info-content">
            <span className="info-label">Loan Amount</span>
            <span className="info-value">{formatCurrency(loan_amount)}</span>
          </div>
        </div>
      )}

      {loan_type && (
        <div className="loan-info-item type">
          <span className="info-icon">📋</span>
          <div className="info-content">
            <span className="info-label">Loan Type</span>
            <span className="info-value">{loan_type}</span>
          </div>
        </div>
      )}

      {interest_rate && (
        <div className="loan-info-item rate">
          <span className="info-icon">📊</span>
          <div className="info-content">
            <span className="info-label">Rate</span>
            <span className="info-value">{interest_rate}%</span>
          </div>
        </div>
      )}

      {loan_number && (
        <div className="loan-info-item loan-number">
          <span className="info-icon">#</span>
          <div className="info-content">
            <span className="info-label">Loan #</span>
            <span className="info-value">{loan_number}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Enhanced Portal Header
 */
export default function EnhancedPortalHeader({
  borrowerName,
  loan,
  milestoneProgress,
  closeOnTimeData,
  loanOfficer,
  stage,
  showMultiLoanSelector,
  children, // For multi-loan selector
}) {
  // Determine days remaining
  const daysRemaining = closeOnTimeData?.business_days_remaining ||
                        closeOnTimeData?.days_remaining ||
                        null;
  const targetDate = closeOnTimeData?.target_close_date || loan?.target_close_date;
  const isOverdue = daysRemaining !== null && daysRemaining < 0;

  // Get milestones for progress bar
  const milestones = milestoneProgress?.milestones || [];
  const completedCount = milestoneProgress?.completed || milestoneProgress?.completed_milestones || 0;
  const totalCount = milestoneProgress?.total || milestoneProgress?.total_milestones || 0;

  // Format stage name
  const formatStageName = (stage) => {
    const stageNames = {
      PROSPECT: 'Prospect',
      LEAD: 'Lead',
      PREAPPROVAL: 'Pre-Approval',
      UNDER_CONTRACT: 'Under Contract',
      PROCESSING: 'Processing',
      CLEAR_TO_CLOSE: 'Clear to Close',
      FUNDED: 'Funded',
      MUM: 'Member Until Maturity',
      ANNUAL_REFRESH: 'Annual Refresh',
      ACTIVE: 'Active',
    };
    return stageNames[stage] || stage || 'In Progress';
  };

  return (
    <header className="enhanced-portal-header">
      {/* Top bar with welcome and controls */}
      <div className="header-top">
        <div className="header-welcome">
          <h1>Welcome{borrowerName ? `, ${borrowerName}` : ''}!</h1>
          {stage && (
            <span className={`stage-badge ${stage?.toLowerCase()}`}>
              {formatStageName(stage)}
            </span>
          )}
        </div>

        <div className="header-controls">
          {/* Multi-loan selector slot */}
          {showMultiLoanSelector && children}

          {/* Loan officer quick contact */}
          {loanOfficer && (
            <LoanOfficerCard loanOfficer={loanOfficer} />
          )}
        </div>
      </div>

      {/* Loan info bar */}
      {loan && <LoanInfoBar loan={loan} />}

      {/* Progress section */}
      <div className="header-progress-section">
        {/* Milestone progress bar */}
        <div className="progress-bar-container">
          <MilestoneProgressBar
            milestones={milestones}
            completed={completedCount}
            total={totalCount}
          />
        </div>

        {/* Days counter */}
        {daysRemaining !== null && (
          <DaysCounter
            daysRemaining={daysRemaining}
            targetDate={targetDate}
            isOverdue={isOverdue}
          />
        )}
      </div>
    </header>
  );
}
