import React from 'react';
import { useNavigate } from 'react-router-dom';
import './ReconciliationDetailPanel.css';

const ReconciliationDetailPanel = ({
  email,
  onProcess,
  onViewLoan,
  onViewLead,
  onClose,
  processing = false,
  compact = false
}) => {
  const navigate = useNavigate();

  // Format date for display
  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  // Get urgency label and color
  const getUrgencyLabel = (level) => {
    const labels = {
      critical: { label: 'Critical', color: '#dc2626' },
      high: { label: 'High', color: '#ea580c' },
      medium: { label: 'Medium', color: '#ca8a04' },
      low: { label: 'Low', color: '#16a34a' }
    };
    return labels[level] || { label: level || 'Normal', color: '#6b7280' };
  };

  const handleViewLoan = () => {
    if (onViewLoan) {
      onViewLoan(email.matched_loan_id);
    } else if (email.matched_loan_id) {
      navigate(`/loans/${email.matched_loan_id}`);
    }
  };

  const handleViewLead = () => {
    if (onViewLead) {
      onViewLead(email.matched_lead_id);
    } else if (email.matched_lead_id) {
      navigate(`/leads/${email.matched_lead_id}`);
    }
  };

  if (!email) {
    return (
      <div className={`reconciliation-detail-panel ${compact ? 'compact' : ''}`}>
        <div className="detail-empty">
          <span className="empty-icon">📧</span>
          <p>Select an email to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`reconciliation-detail-panel ${compact ? 'compact' : ''}`}>
      {/* Header */}
      <div className="detail-header">
        <div className="detail-title-section">
          <div className="detail-source">
            <span className="source-icon-large">📧</span>
            <span className="source-name">Email</span>
            {email.ai_analysis?.urgency_level && (
              <span
                className="urgency-badge"
                style={{ backgroundColor: getUrgencyLabel(email.ai_analysis.urgency_level).color }}
              >
                {getUrgencyLabel(email.ai_analysis.urgency_level).label}
              </span>
            )}
          </div>
          <h2 className="detail-title">{email.subject || '(No Subject)'}</h2>
        </div>
        {onClose && (
          <button className="close-btn" onClick={onClose}>×</button>
        )}
      </div>

      {/* Body */}
      <div className="detail-body">
        {/* Info Grid */}
        <div className="detail-info-grid">
          <div className="detail-info-item">
            <span className="detail-label">From</span>
            <span className="detail-value">{email.from_name || email.from_email}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Email</span>
            <span className="detail-value">{email.from_email}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Date</span>
            <span className="detail-value">{formatDate(email.sent_date)}</span>
          </div>
          <div className="detail-info-item">
            <span className="detail-label">Status</span>
            <span className={`detail-value status-badge ${email.status}`}>{email.status}</span>
          </div>
          {email.matched_loan_id && (
            <div className="detail-info-item">
              <span className="detail-label">Matched Loan</span>
              <span className="detail-value client-link" onClick={handleViewLoan}>
                Loan #{email.matched_loan_id}
              </span>
            </div>
          )}
          {email.matched_lead_id && (
            <div className="detail-info-item">
              <span className="detail-label">Matched Lead</span>
              <span className="detail-value client-link" onClick={handleViewLead}>
                Lead #{email.matched_lead_id}
              </span>
            </div>
          )}
          {email.has_attachments && (
            <div className="detail-info-item">
              <span className="detail-label">Attachments</span>
              <span className="detail-value attachment-value">
                <span className="attachment-icon">📎</span>
                {email.attachment_count || 1} file{(email.attachment_count || 1) !== 1 ? 's' : ''}
              </span>
            </div>
          )}
        </div>

        {/* AI Analysis */}
        {email.ai_analysis && (
          <div className="ai-analysis-section">
            <div className="section-header">
              <span className="section-icon">🤖</span>
              <span className="section-title">AI Analysis</span>
            </div>
            <div className="section-content">
              {email.ai_analysis.disposition && (
                <div className="analysis-item">
                  <strong>Disposition:</strong> {email.ai_analysis.disposition}
                </div>
              )}
              {email.ai_analysis.summary && (
                <div className="analysis-item">
                  <strong>Summary:</strong> {email.ai_analysis.summary}
                </div>
              )}
              {email.ai_analysis.suggested_action && (
                <div className="analysis-item">
                  <strong>Suggested Action:</strong> {email.ai_analysis.suggested_action}
                </div>
              )}
              {email.ai_analysis.extracted_fields && Object.keys(email.ai_analysis.extracted_fields).length > 0 && (
                <div className="extracted-fields">
                  <strong>Extracted Information:</strong>
                  <ul>
                    {Object.entries(email.ai_analysis.extracted_fields).map(([key, value]) => (
                      <li key={key}>
                        <span className="field-key">{key}:</span>
                        <span className="field-value">{value}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Email Body */}
        <div className="email-content-section">
          <div className="section-header">
            <span className="section-icon">📄</span>
            <span className="section-title">Email Content</span>
          </div>
          <div className="section-content email-body">
            <pre>{email.body_preview || email.body || 'No content'}</pre>
          </div>
        </div>

        {/* Attachment List */}
        {email.attachment_names && email.attachment_names.length > 0 && (
          <div className="attachments-section">
            <div className="section-header">
              <span className="section-icon">📎</span>
              <span className="section-title">Attachments</span>
            </div>
            <div className="section-content">
              <ul className="attachment-list">
                {email.attachment_names.map((name, idx) => (
                  <li key={idx} className="attachment-item">
                    <span className="attachment-name">{name}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Action Bar */}
      <div className="detail-actions">
        {email.status === 'pending' && (
          <button
            className="btn-detail-primary"
            onClick={() => onProcess && onProcess(email)}
            disabled={processing}
          >
            {processing ? '⏳ Processing...' : '⚡ Process Email'}
          </button>
        )}
        {email.matched_loan_id && (
          <button className="btn-detail-secondary" onClick={handleViewLoan}>
            📋 View Loan
          </button>
        )}
        {email.matched_lead_id && (
          <button className="btn-detail-secondary" onClick={handleViewLead}>
            👤 View Lead
          </button>
        )}
      </div>
    </div>
  );
};

export default ReconciliationDetailPanel;
