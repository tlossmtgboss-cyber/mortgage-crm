/**
 * NeedsListView Component
 *
 * Displays the document needs list for a loan with status tracking,
 * upload capability, and progress indicators.
 */

import React, { useState } from 'react';
import { useSmartDocs } from '../../hooks/useSmartDocs';
import SmartDocumentUpload from './SmartDocumentUpload';
import DocumentStatusCard from './DocumentStatusCard';
import { smartDocsAPI } from '../../services/smartDocsApi';
import './NeedsListView.css';
import { toast } from '../../utils/toast';

const NeedsListView = ({ loanId, borrowerId, onDocumentUploaded }) => {
  const {
    needsList,
    loading,
    error,
    stats,
    uploadDocument,
    waiveRequest,
    refresh,
  } = useSmartDocs(loanId, borrowerId);

  const [selectedRequest, setSelectedRequest] = useState(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [activeTab, setActiveTab] = useState('open');
  const [showDocuSignModal, setShowDocuSignModal] = useState(false);
  const [docuSignLoading, setDocuSignLoading] = useState(false);
  const [docuSignType, setDocuSignType] = useState('signature'); // 'signature' or 'loe'
  const [loeSubject, setLoeSubject] = useState('');
  const [loeInstructions, setLoeInstructions] = useState('');

  if (loading && !needsList) {
    return (
      <div className="needs-list-loading">
        <div className="spinner" />
        <p>Loading document requirements...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="needs-list-error">
        <span className="error-icon">⚠️</span>
        <p>{error}</p>
        <button onClick={refresh}>Retry</button>
      </div>
    );
  }

  if (!needsList) {
    return (
      <div className="needs-list-empty">
        <p>No document requirements found for this loan.</p>
      </div>
    );
  }

  const requestsByStatus = needsList.requests_by_status || {};

  const tabs = [
    { key: 'open', label: 'Outstanding', count: requestsByStatus.open?.length || 0 },
    { key: 'pending_review', label: 'Pending Review', count: requestsByStatus.pending_review?.length || 0 },
    { key: 'accepted', label: 'Accepted', count: requestsByStatus.accepted?.length || 0 },
    { key: 'waived', label: 'Waived', count: requestsByStatus.waived?.length || 0 },
  ];

  const handleUploadClick = (request) => {
    setSelectedRequest(request);
    setShowUploadModal(true);
  };

  const handleUploadComplete = async (result) => {
    setShowUploadModal(false);
    setSelectedRequest(null);
    if (onDocumentUploaded) {
      onDocumentUploaded(result);
    }
    refresh();
  };

  const handleWaive = async (request, reason) => {
    try {
      await waiveRequest(request.id, reason, 'current_user'); // Replace with actual user
    } catch (err) {
      console.error('Failed to waive request:', err);
    }
  };

  const handleDocuSignClick = (request) => {
    setSelectedRequest(request);
    setDocuSignType('signature');
    setLoeSubject('');
    setLoeInstructions('');
    setShowDocuSignModal(true);
  };

  const handleSendToPortal = async () => {
    if (!selectedRequest) return;

    setDocuSignLoading(true);
    try {
      await smartDocsAPI.sendToPortalForDocuSign(loanId, {
        request_id: selectedRequest.id,
        doc_type: selectedRequest.doc_type,
        title: selectedRequest.title,
        type: docuSignType,
        loe_subject: docuSignType === 'loe' ? loeSubject : null,
        loe_instructions: docuSignType === 'loe' ? loeInstructions : null,
      });
      setShowDocuSignModal(false);
      setSelectedRequest(null);
      refresh();
      toast.success('Document request sent to client portal for signature!');
    } catch (err) {
      console.error('Failed to send to portal:', err);
      toast.error('Failed to send to portal: ' + err.message);
    } finally {
      setDocuSignLoading(false);
    }
  };

  return (
    <div className="needs-list-view">
      {/* Header with Progress */}
      <div className="needs-list-header">
        <div className="header-title">
          <h2>Document Requirements</h2>
          <span className="loan-id">Loan #{loanId}</span>
        </div>

        {stats && (
          <div className="progress-summary">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${stats.completionPercentage}%` }}
              />
            </div>
            <span className="progress-text">
              {stats.acceptedCount} of {stats.totalRequests} complete ({stats.completionPercentage}%)
            </span>
          </div>
        )}
      </div>

      {/* Status Tabs */}
      <div className="status-tabs">
        {tabs.map(tab => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
            {tab.count > 0 && <span className="tab-count">{tab.count}</span>}
          </button>
        ))}
      </div>

      {/* Request Cards */}
      <div className="requests-container">
        {(requestsByStatus[activeTab] || []).length === 0 ? (
          <div className="no-requests">
            <p>No documents in this category</p>
          </div>
        ) : (
          (requestsByStatus[activeTab] || []).map(request => (
            <DocumentRequestCard
              key={request.id}
              request={request}
              onUpload={() => handleUploadClick(request)}
              onWaive={(reason) => handleWaive(request, reason)}
              onDocuSign={() => handleDocuSignClick(request)}
              showActions={activeTab === 'open'}
            />
          ))
        )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && selectedRequest && (
        <div className="upload-modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="upload-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Upload {selectedRequest.title}</h3>
              <button className="close-btn" onClick={() => setShowUploadModal(false)}>×</button>
            </div>
            <div className="modal-body">
              {selectedRequest.instructions && (
                <div className="instructions">
                  <strong>Instructions:</strong>
                  <p>{selectedRequest.instructions}</p>
                </div>
              )}
              <SmartDocumentUpload
                loanId={loanId}
                borrowerId={borrowerId}
                requestId={selectedRequest.id}
                docType={selectedRequest.doc_type}
                onUploadComplete={handleUploadComplete}
              />
            </div>
          </div>
        </div>
      )}

      {/* DocuSign / Send to Portal Modal */}
      {showDocuSignModal && selectedRequest && (
        <div className="upload-modal-overlay" onClick={() => setShowDocuSignModal(false)}>
          <div className="upload-modal docusign-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Send to Client Portal</h3>
              <button className="close-btn" onClick={() => setShowDocuSignModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <p className="docusign-description">
                Send <strong>{selectedRequest.title}</strong> to the client portal for the borrower to complete.
              </p>

              <div className="docusign-type-selector">
                <label className="type-option">
                  <input
                    type="radio"
                    name="docuSignType"
                    value="signature"
                    checked={docuSignType === 'signature'}
                    onChange={() => setDocuSignType('signature')}
                  />
                  <span className="type-label">
                    <span className="type-icon">✍️</span>
                    <span>
                      <strong>Document for Signature</strong>
                      <small>Client will sign via DocuSign</small>
                    </span>
                  </span>
                </label>

                <label className="type-option">
                  <input
                    type="radio"
                    name="docuSignType"
                    value="loe"
                    checked={docuSignType === 'loe'}
                    onChange={() => setDocuSignType('loe')}
                  />
                  <span className="type-label">
                    <span className="type-icon">📝</span>
                    <span>
                      <strong>Letter of Explanation</strong>
                      <small>Client will write and sign an LOE</small>
                    </span>
                  </span>
                </label>
              </div>

              {docuSignType === 'loe' && (
                <div className="loe-fields">
                  <div className="form-group">
                    <label>Subject/Topic</label>
                    <input
                      type="text"
                      value={loeSubject}
                      onChange={(e) => setLoeSubject(e.target.value)}
                      placeholder="e.g., Large deposit explanation, Employment gap"
                    />
                  </div>
                  <div className="form-group">
                    <label>Instructions for Borrower</label>
                    <textarea
                      value={loeInstructions}
                      onChange={(e) => setLoeInstructions(e.target.value)}
                      placeholder="Explain what the borrower needs to address in their letter..."
                      rows={3}
                    />
                  </div>
                </div>
              )}

              <div className="docusign-actions">
                <button
                  className="cancel-btn"
                  onClick={() => setShowDocuSignModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="send-btn"
                  onClick={handleSendToPortal}
                  disabled={docuSignLoading || (docuSignType === 'loe' && !loeSubject.trim())}
                >
                  {docuSignLoading ? 'Sending...' : '📤 Send to Portal'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * Individual document request card
 */
const DocumentRequestCard = ({ request, onUpload, onWaive, onDocuSign, showActions }) => {
  const [showWaiveModal, setShowWaiveModal] = useState(false);
  const [waiveReason, setWaiveReason] = useState('');

  const priorityColors = {
    CRITICAL: '#dc3545',
    HIGH: '#fd7e14',
    NORMAL: '#6c757d',
    LOW: '#28a745',
  };

  const handleWaiveSubmit = () => {
    if (waiveReason.trim()) {
      onWaive(waiveReason);
      setShowWaiveModal(false);
      setWaiveReason('');
    }
  };

  return (
    <div className={`request-card priority-${request.priority?.toLowerCase()}`}>
      <div className="request-header">
        <div className="request-type">
          <span className="doc-icon">{getDocIcon(request.doc_type)}</span>
          <div>
            <h4>{request.title}</h4>
            <span className="doc-type">{request.doc_type}</span>
          </div>
        </div>
        <span
          className="priority-badge"
          style={{ backgroundColor: priorityColors[request.priority] || '#6c757d' }}
        >
          {request.priority}
        </span>
      </div>

      {request.description && (
        <p className="request-description">{request.description}</p>
      )}

      <div className="request-meta">
        {request.required_count > 1 && (
          <span className="meta-item">📄 {request.required_count} required</span>
        )}
        {request.freshness_days && (
          <span className="meta-item">⏱️ {request.freshness_days} day freshness</span>
        )}
        {request.auto_renew && (
          <span className="meta-item auto-renew">🔄 Auto-renewal</span>
        )}
        {request.due_date && (
          <span className="meta-item due-date">📅 Due: {formatDate(request.due_date)}</span>
        )}
      </div>

      {showActions && (
        <div className="request-actions">
          <button className="upload-btn" onClick={onUpload}>
            <span>📤</span> Upload
          </button>
          <button className="docusign-btn" onClick={onDocuSign}>
            <span>✍️</span> Send to Portal
          </button>
          <button className="waive-btn" onClick={() => setShowWaiveModal(true)}>
            Waive
          </button>
        </div>
      )}

      {/* Waive Modal */}
      {showWaiveModal && (
        <div className="waive-modal-overlay" onClick={() => setShowWaiveModal(false)}>
          <div className="waive-modal" onClick={e => e.stopPropagation()}>
            <h4>Waive Requirement</h4>
            <p>Provide a reason for waiving this document requirement:</p>
            <textarea
              value={waiveReason}
              onChange={(e) => setWaiveReason(e.target.value)}
              placeholder="Enter reason..."
              rows={3}
            />
            <div className="waive-actions">
              <button onClick={() => setShowWaiveModal(false)}>Cancel</button>
              <button
                className="confirm-btn"
                onClick={handleWaiveSubmit}
                disabled={!waiveReason.trim()}
              >
                Waive
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Helper to get icon for document type
function getDocIcon(docType) {
  const icons = {
    DRIVERS_LICENSE: '🪪',
    PAYSTUB: '💵',
    W2: '📋',
    TAX_RETURN: '📊',
    BANK_STATEMENT: '🏦',
    INVESTMENT_STATEMENT: '📈',
    GIFT_LETTER: '🎁',
    PURCHASE_CONTRACT: '📝',
    HOMEOWNERS_INSURANCE: '🏠',
    APPRAISAL: '🏡',
    DEFAULT: '📄',
  };
  return icons[docType] || icons.DEFAULT;
}

// Helper to format date
function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default NeedsListView;
