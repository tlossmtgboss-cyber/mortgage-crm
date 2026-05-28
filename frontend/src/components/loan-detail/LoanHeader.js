import React from 'react';
import SalesforceConnectionBadge from '../SalesforceConnectionBadge';

/**
 * Loan header — navigation buttons, save/cancel, borrower name banner, and tab navigation.
 */

const TAB_CONFIG = [
  { key: 'loan-details', label: 'Loan Details' },
  { key: 'personal', label: 'Personal' },
  { key: 'loan', label: 'Property' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'conversation', label: 'Conversation Log' },
  { key: 'circle', label: 'Circle' },
  { key: 'smart-docs', label: 'Smart Docs' },
  { key: 'credit', label: 'Credit' },
  { key: 'income', label: 'Income' },
  { key: 'documents', label: 'Conditions' },
  { key: 'important-dates', label: 'SLA Dates' },
  { key: 'team', label: 'Team Members' },
  { key: 'ai-activity', label: 'AI Activity' },
];

function LoanHeader({
  id,
  loan,
  formData,
  editing,
  setEditing,
  handleSave,
  handleCancel,
  handleViewNextLoan,
  loansList,
  activeTab,
  setActiveTab,
  navigate,
}) {
  return (
    <>
      {/* Header */}
      <div className="detail-header">
        <div className="nav-buttons">
          <button className="btn-back" onClick={() => navigate('/loans')}>
            ← Back to Loans
          </button>
          <button className="btn-next" onClick={handleViewNextLoan} disabled={loansList.length === 0}>
            View Next Loan →
          </button>
        </div>

        <div className="header-actions">
          {editing ? (
            <>
              <button className="btn-save" onClick={handleSave}>Save</button>
              <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
            </>
          ) : (
            <button className="btn-edit-header" onClick={() => setEditing(true)}>
              ✏️ Edit
            </button>
          )}
        </div>
      </div>

      {/* Client Name Banner */}
      <div className="client-name-banner" style={{
        padding: '12px 24px',
        backgroundColor: '#f8fafc',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <h2 style={{
          margin: 0,
          fontSize: '20px',
          fontWeight: '600',
          color: '#1a1a2e'
        }}>
          {formData.borrower_first_name || formData.borrower_last_name
            ? `${formData.borrower_first_name || ''} ${formData.borrower_last_name || ''}`.trim()
            : loan?.borrower_name || loan?.borrower || 'Unknown Borrower'}
        </h2>
        {/* Salesforce Connection Indicator */}
        <SalesforceConnectionBadge
          entityType="loan"
          entityId={id}
          salesforceId={loan?.salesforce_id}
          lastSyncedAt={loan?.salesforce_last_synced_at}
        />
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
        {TAB_CONFIG.map(({ key, label }) => (
          <button
            key={key}
            className={`tab-btn ${activeTab === key ? 'active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
    </>
  );
}

export default LoanHeader;
