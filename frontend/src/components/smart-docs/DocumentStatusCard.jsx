/**
 * DocumentStatusCard Component
 *
 * Displays a document's current status with visual indicators
 * for processing state, decision, and freshness.
 */

import React from 'react';
import FreshnessIndicator from './FreshnessIndicator';
import './DocumentStatusCard.css';

const DocumentStatusCard = ({
  document,
  onView,
  onReview,
  onDownload,
  showActions = true,
}) => {
  const {
    id,
    file_name,
    doc_type,
    status,
    decision,
    rejection_category,
    rejection_reason,
    screenshot_detection,
    dates,
    created_at,
    reviewed_at,
    reviewed_by,
  } = document;

  const statusConfig = {
    UPLOADED: { label: 'Uploaded', color: '#6c757d', icon: '📤' },
    SCANNING: { label: 'Scanning', color: '#17a2b8', icon: '🔍' },
    PROCESSING: { label: 'Processing', color: '#ffc107', icon: '⚙️' },
    APPROVED: { label: 'Approved', color: '#28a745', icon: '✓' },
    REJECTED: { label: 'Rejected', color: '#dc3545', icon: '✗' },
    NEEDS_REVIEW: { label: 'Needs Review', color: '#fd7e14', icon: '!' },
    EXPIRED: { label: 'Expired', color: '#6c757d', icon: '⏱️' },
    ERROR: { label: 'Error', color: '#dc3545', icon: '⚠️' },
  };

  const config = statusConfig[status] || statusConfig.UPLOADED;

  return (
    <div className={`document-status-card status-${status?.toLowerCase()}`}>
      {/* Header */}
      <div className="card-header">
        <div className="doc-info">
          <span className="doc-icon">{getDocIcon(doc_type)}</span>
          <div className="doc-details">
            <h4 className="file-name" title={file_name}>
              {truncateFilename(file_name, 30)}
            </h4>
            <span className="doc-type">{formatDocType(doc_type)}</span>
          </div>
        </div>
        <div
          className="status-badge"
          style={{ backgroundColor: config.color }}
        >
          <span className="status-icon">{config.icon}</span>
          {config.label}
        </div>
      </div>

      {/* Screenshot Detection Alert */}
      {screenshot_detection?.is_screenshot && (
        <div className="alert screenshot-alert">
          <span className="alert-icon">📱</span>
          <div>
            <strong>Screenshot Detected</strong>
            <p>
              This appears to be a screenshot
              ({Math.round((screenshot_detection.confidence || 0) * 100)}% confidence)
            </p>
          </div>
        </div>
      )}

      {/* Rejection Reason */}
      {status === 'REJECTED' && rejection_reason && (
        <div className="alert rejection-alert">
          <span className="alert-icon">⚠️</span>
          <div>
            <strong>{formatRejectionCategory(rejection_category)}</strong>
            <p>{rejection_reason}</p>
          </div>
        </div>
      )}

      {/* Document Dates */}
      {dates && (
        <div className="dates-section">
          {dates.doc_date && (
            <div className="date-item">
              <span className="date-label">Document Date:</span>
              <span className="date-value">{formatDate(dates.doc_date)}</span>
            </div>
          )}

          {dates.expires_at && (
            <FreshnessIndicator
              status={dates.is_expired ? 'expired' : dates.days_until_expiration <= 7 ? 'expiring_soon' : 'fresh'}
              daysUntilExpiration={dates.days_until_expiration}
              expiresAt={dates.expires_at}
              compact
            />
          )}
        </div>
      )}

      {/* Metadata */}
      <div className="card-meta">
        <span className="meta-item">
          <span className="meta-icon">📅</span>
          Uploaded {formatRelativeDate(created_at)}
        </span>
        {reviewed_at && (
          <span className="meta-item">
            <span className="meta-icon">👤</span>
            Reviewed by {reviewed_by === 'SYSTEM' ? 'Auto' : reviewed_by}
          </span>
        )}
      </div>

      {/* Actions */}
      {showActions && (
        <div className="card-actions">
          {onView && (
            <button className="action-btn view" onClick={() => onView(document)}>
              <span>👁️</span> View
            </button>
          )}
          {status === 'NEEDS_REVIEW' && onReview && (
            <button className="action-btn review" onClick={() => onReview(document)}>
              <span>✏️</span> Review
            </button>
          )}
          {onDownload && (
            <button className="action-btn download" onClick={() => onDownload(document)}>
              <span>📥</span> Download
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// Helper functions
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
    PROFIT_LOSS: '📉',
    BALANCE_SHEET: '📑',
  };
  return icons[docType] || '📄';
}

function formatDocType(docType) {
  if (!docType) return '';
  return docType
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}

function formatRejectionCategory(category) {
  const categories = {
    SCREENSHOT: 'Screenshot Detected',
    EXPIRED: 'Document Expired',
    POOR_QUALITY: 'Poor Quality',
    INCOMPLETE: 'Incomplete Document',
    WRONG_TYPE: 'Wrong Document Type',
    OTHER: 'Rejected',
  };
  return categories[category] || 'Rejected';
}

function truncateFilename(filename, maxLength) {
  if (!filename || filename.length <= maxLength) return filename;
  const ext = filename.split('.').pop();
  const name = filename.slice(0, -(ext.length + 1));
  const truncated = name.slice(0, maxLength - ext.length - 4);
  return `${truncated}...${ext}`;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatRelativeDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateStr);
}

export default DocumentStatusCard;
