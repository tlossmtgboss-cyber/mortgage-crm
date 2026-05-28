import React from 'react';

function ReconciliationSidebar({
  showReconciliationSidebar,
  setShowReconciliationSidebar,
  reconciliationItems,
  selectedReconciliationItem,
  setSelectedReconciliationItem,
  reconciliationLoading,
  reconciliationTab,
  setReconciliationTab,
  reconciliationCounts,
  autoProcessEnabled,
  setAutoProcessEnabled,
  onFetchItems,
  onApprove,
  onReject
}) {
  if (!showReconciliationSidebar) return null;

  return (
    <div className="email-intelligence-sidebar">
      <div className="ei-sidebar-header">
        <h2>Email Reconciliation</h2>
        <button
          className="close-sidebar-btn"
          onClick={() => setShowReconciliationSidebar(false)}
        >
          ×
        </button>
      </div>

      {/* Status Tabs */}
      <div className="ei-tabs">
        <button
          className={`ei-tab ${reconciliationTab === 'new' ? 'active' : ''}`}
          onClick={() => { setReconciliationTab('new'); onFetchItems('new'); }}
        >
          New ({reconciliationCounts.new || reconciliationItems.length})
        </button>
        <button
          className={`ei-tab ${reconciliationTab === 'auto' ? 'active' : ''}`}
          onClick={() => { setReconciliationTab('auto'); onFetchItems('auto'); }}
        >
          Auto-Processing ({reconciliationCounts.auto || 0})
        </button>
        <button
          className={`ei-tab ${reconciliationTab === 'pending' ? 'active' : ''}`}
          onClick={() => { setReconciliationTab('pending'); onFetchItems('pending'); }}
        >
          Pending Review ({reconciliationCounts.pending || 0})
        </button>
        <button
          className={`ei-tab ${reconciliationTab === 'completed' ? 'active' : ''}`}
          onClick={() => { setReconciliationTab('completed'); onFetchItems('completed'); }}
        >
          Completed ({reconciliationCounts.completed || 0})
        </button>
      </div>

      <div className="ei-main-content">
        {/* Left Column - Item List */}
        <div className="ei-item-list">
          {reconciliationLoading ? (
            <div className="ei-loading">
              <div className="loading-spinner"></div>
              <p>Loading items...</p>
            </div>
          ) : reconciliationItems.length === 0 ? (
            <div className="ei-empty">
              <p>No items in this category</p>
              <button className="ei-refresh-btn" onClick={() => onFetchItems()}>
                Refresh
              </button>
            </div>
          ) : (
            reconciliationItems.map((item) => {
              // Extract loan number and name from fields
              const loanNumber = item.fields?.loan_number?.value || item.fields?.loan_number || '';
              const firstName = item.fields?.first_name?.value || item.fields?.first_name || '';
              const lastName = item.fields?.last_name?.value || item.fields?.last_name || '';
              const displayName = firstName || lastName
                ? `${firstName} ${lastName}`.trim()
                : (item.match_entity_name || item.borrower_name || '');
              // Use email_subject (API field name) or fallback to nested email.subject
              const subject = item.email_subject || item.email?.subject || item.subject || 'Loan Update';

              // Build display title like "CMG-0154304 [Stewart-RCA00000008590]: Inspection Scheduled"
              const displayTitle = loanNumber
                ? `${loanNumber}${displayName ? ` [${displayName}]` : ''}: ${subject}`
                : (displayName ? `${displayName}: ${subject}` : subject);

              const isSelected = selectedReconciliationItem?.id === item.id;
              const matchType = item.match_entity_type?.toUpperCase() || 'ACTIVE_LOAN';
              // Use email_from (API field name) or fallback to nested email.sender
              const fromEmail = item.email_from || item.email?.sender || item.from_email || '';
              const receivedDate = item.email_received_at || item.email?.received_at || item.created_at;

              return (
                <div
                  key={item.id}
                  className={`ei-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedReconciliationItem(item)}
                >
                  <div className="ei-item-header">
                    <span className="ei-item-type">{matchType}</span>
                    <span className="ei-item-badge new">NEW</span>
                  </div>
                  <div className="ei-item-title">{displayTitle}</div>
                  <div className="ei-item-from">
                    <span className="ei-from-label">From:</span> {fromEmail}
                  </div>
                  {receivedDate && (
                    <div className="ei-item-date">
                      {new Date(receivedDate).toLocaleDateString()}
                    </div>
                  )}
                  <div className="ei-item-warning">
                    This message originated from outside CML. Please use caution when opening links and attachments.
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right Column - Detail Panel */}
        <div className="ei-detail-panel">
          {selectedReconciliationItem ? (
            <ReconciliationDetailPanel
              item={selectedReconciliationItem}
              autoProcessEnabled={autoProcessEnabled}
              setAutoProcessEnabled={setAutoProcessEnabled}
              onApprove={onApprove}
              onReject={onReject}
            />
          ) : (
            <div className="ei-no-selection">
              <p>Select an item from the list to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ReconciliationDetailPanel({ item, autoProcessEnabled, setAutoProcessEnabled, onApprove, onReject }) {
  const firstName = item.fields?.first_name?.value || item.fields?.first_name || '';
  const lastName = item.fields?.last_name?.value || item.fields?.last_name || '';
  const displayName = firstName || lastName
    ? `${firstName} ${lastName}`.trim()
    : (item.match_entity_name || item.borrower_name || 'Unknown');
  // Use correct API field names
  const subject = item.email_subject || item.email?.subject || item.subject || 'Loan Update';
  const fromEmail = item.email_from || item.email?.sender || item.from_email || '';
  const receivedDate = item.email_received_at || item.email?.received_at || item.created_at;
  const emailBody = item.email_body || item.email?.body || '';

  // Organize fields into a grid
  const fieldPairs = item.fields ? Object.entries(item.fields).map(([key, val]) => ({
    label: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
    value: typeof val === 'object' && val !== null ? (val.value || '') : String(val || ''),
    confidence: typeof val === 'object' && val?.confidence ? Math.round(val.confidence * 100) : 100
  })) : [];

  return (
    <>
      <div className="ei-detail-header">
        <span className="ei-new-message">NEW MESSAGE</span>
        <h3 className="ei-detail-title">{subject}</h3>
      </div>

      <div className="ei-detail-meta">
        <div className="ei-meta-row">
          <span className="ei-meta-label">FROM</span>
          <span className="ei-meta-value">{fromEmail}</span>
        </div>
        <div className="ei-meta-row">
          <span className="ei-meta-label">SUBJECT</span>
          <span className="ei-meta-value">{subject}</span>
        </div>
        <div className="ei-meta-row">
          <span className="ei-meta-label">RECEIVED</span>
          <span className="ei-meta-value">
            {receivedDate ? new Date(receivedDate).toLocaleString() : '-'}
          </span>
        </div>
        <div className="ei-meta-row">
          <span className="ei-meta-label">STATUS</span>
          <span className="ei-meta-value">Awaiting Processing</span>
        </div>
      </div>

      {/* Where should this data go? */}
      <div className="ei-match-section">
        <h4>Where should this data go?</h4>
        <div className="ei-match-options">
          <div className={`ei-match-option ${item.match_entity_type === 'lead' ? 'selected' : ''}`}>
            <span className="ei-match-icon">👤</span>
            <span className="ei-match-label">Lead</span>
            <span className="ei-match-status">{item.match_entity_type === 'lead' ? `#${item.match_entity_id}` : 'No match found'}</span>
          </div>
          <div className={`ei-match-option ${item.match_entity_type === 'loan' ? 'selected' : ''}`}>
            <span className="ei-match-icon">📋</span>
            <span className="ei-match-label">Active Loan</span>
            <span className="ei-match-status">{item.match_entity_type === 'loan' ? `#${item.match_entity_id}` : 'No match found'}</span>
          </div>
          <div className="ei-match-option">
            <span className="ei-match-icon">📁</span>
            <span className="ei-match-label">Portfolio</span>
            <span className="ei-match-status">No match found</span>
          </div>
          <div className="ei-match-option create-new">
            <span className="ei-match-icon">➕</span>
            <span className="ei-match-label">Create New Loan</span>
            <span className="ei-match-status">{item.fields?.loan_number?.value || ''}</span>
          </div>
        </div>
      </div>

      {/* Extracted Fields */}
      <div className="ei-fields-section">
        <div className="ei-fields-header">
          <h4>Extracted Fields</h4>
          <button className="ei-add-field-btn">+ Add Field</button>
        </div>
        <div className="ei-fields-grid">
          {fieldPairs.map((field, idx) => (
            <div key={idx} className="ei-field-item">
              <div className="ei-field-header">
                <span className="ei-field-label">{field.label}</span>
                <span className={`ei-field-confidence ${field.confidence >= 90 ? 'high' : field.confidence >= 70 ? 'medium' : 'low'}`}>
                  {field.confidence}%
                </span>
              </div>
              <div className="ei-field-value-row">
                <input
                  type="text"
                  className="ei-field-input"
                  value={field.value}
                  readOnly
                />
                <button className="ei-field-delete">Delete</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Email Content */}
      {emailBody && (
        <div className="ei-email-content">
          <h4>EMAIL CONTENT</h4>
          <div className="ei-email-body">
            {emailBody}
          </div>
        </div>
      )}

      {/* Auto-process option */}
      <div className="ei-auto-process">
        <label className="ei-checkbox-label">
          <input
            type="checkbox"
            checked={autoProcessEnabled}
            onChange={(e) => setAutoProcessEnabled(e.target.checked)}
          />
          Let AI auto-process similar messages
        </label>
        <p className="ei-auto-hint">
          When approved, AI will automatically handle similar "Loan Update" messages in the future without requiring your review.
        </p>
      </div>

      {/* Action Buttons */}
      <div className="ei-actions">
        <button
          className="ei-action-btn process"
          onClick={() => onApprove(item, item.ai_suggested_status)}
        >
          Process & Apply
        </button>
        <button
          className="ei-action-btn reject"
          onClick={() => onReject(item)}
        >
          Reject
        </button>
        <button
          className="ei-action-btn delete"
          onClick={() => onReject(item, 'Deleted by user')}
        >
          Delete
        </button>
      </div>
    </>
  );
}

export default ReconciliationSidebar;
