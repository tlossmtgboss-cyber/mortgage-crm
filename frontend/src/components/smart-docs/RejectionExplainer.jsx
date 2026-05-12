/**
 * RejectionExplainer Component
 *
 * Displays a clear explanation when a document is rejected,
 * with the reason, category, and actionable fix instructions.
 */

import React from 'react';
import './RejectionExplainer.css';

const RejectionExplainer = ({
  category,
  reason,
  fixInstructions,
  onDismiss,
  showDismiss = false,
  onReupload,
}) => {
  const categoryConfig = {
    SCREENSHOT: {
      icon: '📱',
      title: 'Screenshot Detected',
      color: '#dc3545',
      bgColor: '#f8d7da',
      borderColor: '#f5c6cb',
      defaultInstructions: 'Please upload the original PDF document, not a screenshot or photo of it.',
    },
    EXPIRED: {
      icon: '⏱️',
      title: 'Document Expired',
      color: '#dc3545',
      bgColor: '#f8d7da',
      borderColor: '#f5c6cb',
      defaultInstructions: 'Please upload a more recent version of this document.',
    },
    POOR_QUALITY: {
      icon: '🔍',
      title: 'Poor Quality',
      color: '#fd7e14',
      bgColor: '#fff3cd',
      borderColor: '#ffeeba',
      defaultInstructions: 'The document quality is too low to process. Please upload a clearer scan or photo.',
    },
    INCOMPLETE: {
      icon: '📄',
      title: 'Incomplete Document',
      color: '#fd7e14',
      bgColor: '#fff3cd',
      borderColor: '#ffeeba',
      defaultInstructions: 'The document appears to be incomplete. Please upload all pages.',
    },
    WRONG_TYPE: {
      icon: '❌',
      title: 'Wrong Document Type',
      color: '#dc3545',
      bgColor: '#f8d7da',
      borderColor: '#f5c6cb',
      defaultInstructions: 'This is not the requested document type. Please upload the correct document.',
    },
    OTHER: {
      icon: '⚠️',
      title: 'Document Rejected',
      color: '#dc3545',
      bgColor: '#f8d7da',
      borderColor: '#f5c6cb',
      defaultInstructions: 'Please review the rejection reason and upload a corrected document.',
    },
  };

  const config = categoryConfig[category] || categoryConfig.OTHER;
  const instructions = fixInstructions || config.defaultInstructions;

  return (
    <div
      className="rejection-explainer"
      style={{
        backgroundColor: config.bgColor,
        borderColor: config.borderColor,
      }}
      role="alert"
      aria-label={`Document rejected: ${config.title}`}
    >
      {showDismiss && onDismiss && (
        <button className="dismiss-btn" onClick={onDismiss} aria-label="Dismiss rejection explanation">×</button>
      )}

      <div className="explainer-header">
        <span className="category-icon" style={{ color: config.color }}>
          {config.icon}
        </span>
        <h4 className="category-title" style={{ color: config.color }}>
          {config.title}
        </h4>
      </div>

      <div className="explainer-body">
        {reason && (
          <div className="rejection-reason">
            <strong>Reason:</strong>
            <p>{reason}</p>
          </div>
        )}

        <div className="fix-instructions">
          <strong>How to fix:</strong>
          <p>{instructions}</p>
        </div>

        {/* Category-specific tips */}
        {category === 'SCREENSHOT' && (
          <div className="category-tips">
            <h5>Tips to avoid rejection:</h5>
            <ul>
              <li>Download the original PDF from your bank or employer's website</li>
              <li>If you only have a paper copy, use a scanner or a document scanning app</li>
              <li>Do not take a photo of your screen or use the screenshot function</li>
            </ul>
          </div>
        )}

        {category === 'EXPIRED' && (
          <div className="category-tips">
            <h5>Freshness requirements:</h5>
            <ul>
              <li>Pay stubs must be dated within the last 30 days</li>
              <li>Bank statements must be dated within the last 60 days</li>
              <li>Check the date on your document before uploading</li>
            </ul>
          </div>
        )}

        {category === 'POOR_QUALITY' && (
          <div className="category-tips">
            <h5>Tips for better quality:</h5>
            <ul>
              <li>Use good lighting when scanning or photographing</li>
              <li>Ensure the entire document is in frame</li>
              <li>Make sure the text is sharp and readable</li>
              <li>Use a flat surface to avoid distortion</li>
            </ul>
          </div>
        )}
      </div>

      <div className="explainer-footer">
        {onReupload && (
          <button
            className="reupload-btn"
            onClick={onReupload}
            aria-label={`Re-upload document to resolve: ${config.title}`}
          >
            Re-upload Document
          </button>
        )}
        <p className="help-text">
          Need help? Contact your loan officer for assistance.
        </p>
      </div>
    </div>
  );
};

/**
 * Compact inline version for lists
 */
export const RejectionBadge = ({ category, reason }) => {
  const icons = {
    SCREENSHOT: '📱',
    EXPIRED: '⏱️',
    POOR_QUALITY: '🔍',
    INCOMPLETE: '📄',
    WRONG_TYPE: '❌',
    OTHER: '⚠️',
  };

  return (
    <div className="rejection-badge" title={reason} role="status" aria-label={`Rejected: ${formatCategory(category)}${reason ? '. ' + reason : ''}`}>
      <span className="badge-icon" aria-hidden="true">{icons[category] || '⚠️'}</span>
      <span className="badge-text">{formatCategory(category)}</span>
    </div>
  );
};

/**
 * Alert banner version
 */
export const RejectionAlert = ({
  category,
  reason,
  onRetry,
  onContact,
}) => {
  return (
    <div className="rejection-alert" role="alert" aria-label={`Document rejected: ${formatCategory(category)}`}>
      <div className="alert-icon" aria-hidden="true">⚠️</div>
      <div className="alert-content">
        <strong>Document Rejected: {formatCategory(category)}</strong>
        {reason && <p>{reason}</p>}
      </div>
      <div className="alert-actions">
        {onRetry && (
          <button className="retry-btn" onClick={onRetry} aria-label="Upload the document again">
            Upload Again
          </button>
        )}
        {onContact && (
          <button className="contact-btn" onClick={onContact} aria-label="Contact loan officer for help">
            Get Help
          </button>
        )}
      </div>
    </div>
  );
};

function formatCategory(category) {
  const names = {
    SCREENSHOT: 'Screenshot Detected',
    EXPIRED: 'Document Expired',
    POOR_QUALITY: 'Poor Quality',
    INCOMPLETE: 'Incomplete',
    WRONG_TYPE: 'Wrong Type',
    OTHER: 'Rejected',
  };
  return names[category] || 'Rejected';
}

export default RejectionExplainer;
