import React, { useState, useEffect } from 'react';
import { leadsAPI, loansAPI } from '../services/api';
import './EmailReconciliationModal.css';
import { toast } from '../utils/toast';

/**
 * EmailReconciliationModal - Reconciliation workflow for imported emails
 * Matches the existing reconciliation UI pattern from the screenshot
 */
function EmailReconciliationModal({ emailData, onClose, onComplete }) {
  const [matchedEntity, setMatchedEntity] = useState(null);
  const [searchResults, setSearchResults] = useState({ leads: [], loans: [] });
  const [selectedAction, setSelectedAction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Extract fields from email for display
  const extractedFields = {
    subject: emailData.subject,
    from: emailData.from,
    status: 'Client Extraction',
    priority: 'Manual Priority',
    loanOfficer: 'Loan Officer',
    date: emailData.date,
  };

  // Search for matching entities on mount
  useEffect(() => {
    searchForMatches();
  }, [emailData]);

  const searchForMatches = async () => {
    setLoading(true);
    try {
      // Search by sender email or matched borrower name
      const searchTerm = emailData.matchedBorrower || emailData.from?.split('@')[0] || '';

      // Search leads and loans in parallel
      const [leadsResponse, loansResponse] = await Promise.all([
        leadsAPI.search(searchTerm).catch(() => ({ data: [] })),
        loansAPI.getAll().catch(() => ({ data: [] })),
      ]);

      const leads = leadsResponse.data || leadsResponse || [];
      const loans = loansResponse.data || loansResponse || [];

      // Filter loans by borrower name if we have one
      const filteredLoans = emailData.matchedBorrower
        ? loans.filter(loan =>
            loan.borrower_name?.toLowerCase().includes(emailData.matchedBorrower.toLowerCase())
          )
        : [];

      setSearchResults({ leads: leads.slice(0, 5), loans: filteredLoans.slice(0, 5) });

      // If we have a high confidence match, pre-select it
      if (emailData.confidence > 80 && (leads.length > 0 || filteredLoans.length > 0)) {
        if (filteredLoans.length > 0) {
          setMatchedEntity({ type: 'loan', data: filteredLoans[0] });
        } else if (leads.length > 0) {
          setMatchedEntity({ type: 'lead', data: leads[0] });
        }
      }
    } catch (error) {
      console.error('Search failed:', error);
    }
    setLoading(false);
  };

  const handleActionSelect = (action) => {
    setSelectedAction(action);
  };

  const handleEntitySelect = (type, entity) => {
    setMatchedEntity({ type, data: entity });
  };

  const handleApprove = async () => {
    if (!selectedAction) {
      toast.error('Please select an action');
      return;
    }

    setSubmitting(true);
    try {
      // Process based on selected action
      const result = {
        action: selectedAction,
        emailData,
        matchedEntity,
      };

      onComplete(selectedAction, result);
    } catch (error) {
      console.error('Failed to process:', error);
      toast.error('Failed to process email. Please try again.');
    }
    setSubmitting(false);
  };

  const handleReject = () => {
    onClose();
  };

  return (
    <div className="email-reconciliation-overlay">
      <div className="email-reconciliation-modal">
        {/* Header */}
        <div className="reconciliation-header">
          <div className="header-left">
            <span className="source-badge">EMAIL IMPORT</span>
            <span className="source-name">Imported Email</span>
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {/* Main Content */}
        <div className="reconciliation-content">
          {/* Left Column - Email Details */}
          <div className="reconciliation-left">
            {/* Subject/Title */}
            <div className="field-group">
              <label>SUBJECT</label>
              <div className="field-value">{emailData.subject}</div>
            </div>

            <div className="field-row">
              <div className="field-group">
                <label>STATUS</label>
                <div className="field-value">{extractedFields.status}</div>
              </div>
              <div className="field-group">
                <label>PRIORITY</label>
                <div className="field-value">{extractedFields.priority}</div>
              </div>
            </div>

            <div className="field-row">
              <div className="field-group">
                <label>LOAN OFFICER</label>
                <div className="field-value">{extractedFields.loanOfficer}</div>
              </div>
              <div className="field-group">
                <label>DATE</label>
                <div className="field-value">{emailData.date}</div>
              </div>
            </div>

            {/* Confidence Badge */}
            <div className="confidence-section">
              <div className={`confidence-badge ${emailData.confidence > 70 ? 'high' : emailData.confidence > 40 ? 'medium' : 'low'}`}>
                <span className="flag-icon">🚩</span>
                <span>Flagged for Review</span>
                <span className="confidence-score">Match Confidence: {emailData.confidence}%</span>
              </div>
            </div>

            {/* Action Selection */}
            <div className="action-section">
              <h4>Where should this data go?</h4>
              <div className="action-buttons">
                <button
                  className={`action-btn ${selectedAction === 'archive' ? 'selected' : ''}`}
                  onClick={() => handleActionSelect('archive')}
                >
                  <span className="action-icon">📁</span>
                  <span>Archive Email</span>
                </button>
                <button
                  className={`action-btn ${selectedAction === 'lead' ? 'selected' : ''}`}
                  onClick={() => handleActionSelect('lead')}
                >
                  <span className="action-icon">👤</span>
                  <span>Lead</span>
                </button>
                <button
                  className={`action-btn ${selectedAction === 'loan' ? 'selected' : ''}`}
                  onClick={() => handleActionSelect('loan')}
                >
                  <span className="action-icon">➕</span>
                  <span>Create/Open Loan</span>
                </button>
              </div>
            </div>

            {/* Matched Entity Section */}
            {(selectedAction === 'lead' || selectedAction === 'loan') && (
              <div className="matched-entity-section">
                <h4>Matched Entity</h4>
                {matchedEntity ? (
                  <div className="matched-entity">
                    <span className="entity-type">{matchedEntity.type === 'lead' ? 'Lead' : 'Loan'}</span>
                    <span className="entity-name">
                      {matchedEntity.type === 'lead'
                        ? `${matchedEntity.data.first_name} ${matchedEntity.data.last_name}`
                        : matchedEntity.data.borrower_name}
                    </span>
                    <div className="confidence-meter">
                      <span>Confidence: {emailData.confidence}%</span>
                    </div>
                  </div>
                ) : (
                  <div className="no-match">
                    <span>No automatic match found</span>
                  </div>
                )}

                {/* Search Results */}
                {!loading && (searchResults.leads.length > 0 || searchResults.loans.length > 0) && (
                  <div className="search-results">
                    <h5>Select Existing Record:</h5>
                    {searchResults.leads.map(lead => (
                      <div
                        key={`lead-${lead.id}`}
                        className={`result-item ${matchedEntity?.data?.id === lead.id && matchedEntity?.type === 'lead' ? 'selected' : ''}`}
                        onClick={() => handleEntitySelect('lead', lead)}
                      >
                        <span className="result-type">Lead</span>
                        <span className="result-name">{lead.first_name} {lead.last_name}</span>
                        <span className="result-email">{lead.email}</span>
                      </div>
                    ))}
                    {searchResults.loans.map(loan => (
                      <div
                        key={`loan-${loan.id}`}
                        className={`result-item ${matchedEntity?.data?.id === loan.id && matchedEntity?.type === 'loan' ? 'selected' : ''}`}
                        onClick={() => handleEntitySelect('loan', loan)}
                      >
                        <span className="result-type">Loan</span>
                        <span className="result-name">{loan.borrower_name}</span>
                        <span className="result-number">{loan.loan_number}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Email From/Details */}
            <div className="email-details-section">
              <h4>Email Details</h4>
              <div className="detail-row">
                <label>From:</label>
                <span>{emailData.from}</span>
              </div>
              {emailData.to && (
                <div className="detail-row">
                  <label>To:</label>
                  <span>{emailData.to}</span>
                </div>
              )}
              <div className="detail-row">
                <label>Received:</label>
                <span>{emailData.date}</span>
              </div>
            </div>
          </div>

          {/* Right Column - Email Body */}
          <div className="reconciliation-right">
            <h4>Email Body</h4>
            <div className="email-body-container">
              <pre className="email-body">{emailData.body}</pre>
            </div>

            {/* Link Preview if URL found */}
            {emailData.body && emailData.body.includes('http') && (
              <div className="link-preview">
                <p className="link-note">
                  <span className="info-icon">ℹ️</span>
                  Links detected in email. Click to view externally.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="reconciliation-footer">
          <button
            className="btn-approve"
            onClick={handleApprove}
            disabled={submitting || !selectedAction}
          >
            {submitting ? 'Processing...' : 'APPROVE & CONTINUE'}
          </button>
          <button
            className="btn-reject"
            onClick={handleReject}
            disabled={submitting}
          >
            REJECT
          </button>
        </div>
      </div>
    </div>
  );
}

export default EmailReconciliationModal;
