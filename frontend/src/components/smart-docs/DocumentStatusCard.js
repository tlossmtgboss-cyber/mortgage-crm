import React from 'react';
import FreshnessIndicator from './FreshnessIndicator';
import './DocumentStatusCard.css';

function DocumentStatusCard({ document, onView, onReview }) {
  const getStatusInfo = (status) => {
    switch (status) {
      case 'approved':
        return { label: 'Approved', class: 'approved', icon: '✓' };
      case 'rejected':
        return { label: 'Rejected', class: 'rejected', icon: '✗' };
      case 'pending_review':
        return { label: 'Pending Review', class: 'pending', icon: '⏳' };
      case 'needs_correction':
        return { label: 'Needs Correction', class: 'correction', icon: '⚠' };
      default:
        return { label: status || 'Unknown', class: 'unknown', icon: '?' };
    }
  };

  const statusInfo = getStatusInfo(document.status);
  const uploadDate = document.uploaded_at ? new Date(document.uploaded_at) : null;
  const isScreenshot = document.is_screenshot;

  return (
    <div className={`document-status-card status-${statusInfo.class}`}>
      <div className="card-header">
        <div className="doc-icon">📄</div>
        <div className="doc-info">
          <h4>{document.document_category || 'Document'}</h4>
          <span className="doc-type">{document.document_type || 'Unknown Type'}</span>
        </div>
        <div className={`status-indicator ${statusInfo.class}`}>
          <span className="status-icon">{statusInfo.icon}</span>
          <span className="status-label">{statusInfo.label}</span>
        </div>
      </div>

      <div className="card-body">
        {document.original_filename && (
          <p className="filename">{document.original_filename}</p>
        )}

        <div className="card-meta">
          {uploadDate && (
            <span className="meta-item">
              Uploaded: {uploadDate.toLocaleDateString()}
            </span>
          )}
          {document.file_size && (
            <span className="meta-item">
              Size: {(document.file_size / 1024).toFixed(1)} KB
            </span>
          )}
        </div>

        {/* Validation Indicators */}
        <div className="validation-indicators">
          {isScreenshot && (
            <div className="indicator warning">
              <span className="indicator-icon">📱</span>
              <span>Screenshot Detected</span>
            </div>
          )}

          {document.document_date && (
            <FreshnessIndicator
              documentDate={document.document_date}
              documentType={document.document_category}
            />
          )}
        </div>

        {/* Confidence Score if available */}
        {document.confidence_score !== undefined && document.confidence_score !== null && (
          <div className="confidence-meter">
            <span className="confidence-label">Confidence:</span>
            <div className="confidence-bar">
              <div
                className="confidence-fill"
                style={{ width: `${document.confidence_score * 100}%` }}
              />
            </div>
            <span className="confidence-value">
              {Math.round(document.confidence_score * 100)}%
            </span>
          </div>
        )}

        {/* Review Notes */}
        {document.review_notes && (
          <div className="review-notes">
            <strong>Notes:</strong> {document.review_notes}
          </div>
        )}
      </div>

      <div className="card-actions">
        {onView && (
          <button className="btn-view" onClick={onView}>
            View
          </button>
        )}
        {onReview && document.status === 'pending_review' && (
          <button className="btn-review" onClick={onReview}>
            Review
          </button>
        )}
      </div>
    </div>
  );
}

export default DocumentStatusCard;
